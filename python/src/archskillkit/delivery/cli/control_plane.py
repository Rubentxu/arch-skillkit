"""`archskillkit control-plane` — local-only Control Plane kernel
(V2.4 M5 slice 20; docs/v2/54 §7 + §12, docs/v2/66 §1, docs/v2/59 M5).

Scope of this slice: the HTTP backbone only. Properties:

- Binds 127.0.0.1 ONLY. There is no flag, env var or config escape
  hatch to expose it on another interface (docs/v2/54 §12 "localhost
  por defecto" is enforced by construction, not by default value).
- Authenticates EVERY request with a per-process bearer token
  generated at startup and printed once on stdout. The token is never
  persisted to disk (docs/v2/54 §12 "token/session local").
- Registers itself in the RuntimeRegistry (ADR-0033: live PIDs live
  there, never in the world event log) and unregisters on graceful
  shutdown (SIGINT/SIGTERM).
- Read-only by construction: the endpoints are projections over the
  application layer; no write route exists in this slice. Governance
  opt-in arrives with slice 24 and will reuse the admin gate.

Endpoints (deterministic JSON envelopes, same schemas as the CLI):

    GET /health    liveness, token required, inert body
    GET /status    GetStatus projection    (arch-skillkit/status-result-v1)
    GET /history   RunLedger read model    (arch-skillkit/history-v1)
    GET /viewers   ViewerRegistry probes   (arch-skillkit/viewers-v1)

Errors are stable-code envelopes ({"code", "message"}), mirroring the
admin gate convention so consumers can branch without parsing text.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import signal
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from archskillkit.application.queries.get_status import get_status
from archskillkit.codeindex import CodeIndex
from archskillkit.ids import RepoNotFound
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.runtime_state.runtime_registry import RuntimeEntry, RuntimeRegistry
from archskillkit.viewers.registry import ViewerRegistry
from archskillkit.world import ArchitectureWorld

NAME = "control-plane"
NEEDS_WORLD = False

# docs/v2/54 §12: localhost only, no exceptions.
BIND_HOST = "127.0.0.1"

START_SCHEMA = "arch-skillkit/control-plane-start-v1"
HEALTH_SCHEMA = "arch-skillkit/control-plane-health-v1"

RUN_ID = "control-plane"
_MAX_LIMIT = 500


# ---------- HTTP layer -------------------------------------------------


class _ControlPlaneHandler(BaseHTTPRequestHandler):
    """One handler, four GET routes, auth on every request."""

    protocol_version = "HTTP/1.1"
    server_version = "arch-skillkit-control-plane/1"
    sys_version = ""

    # -- plumbing -------------------------------------------------------

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"code": code, "message": message})

    def _authorized(self) -> bool:
        expected = getattr(self.server, "token", "")
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return hmac.compare_digest(header[len("Bearer ") :], expected)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence per-request stderr logging; the process prints one
        startup envelope and stays quiet after that."""

    # -- verbs ----------------------------------------------------------

    def do_GET(self) -> None:
        if not self._authorized():
            self._error(401, "UNAUTHORIZED", "missing or invalid bearer token")
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                self._send_json(200, {"schema": HEALTH_SCHEMA, "ok": True})
                return
            if parsed.path == "/status":
                self._send_json(200, self._status())
                return
            if parsed.path == "/history":
                self._send_json(200, self._history(parse_qs(parsed.query)))
                return
            if parsed.path == "/viewers":
                self._send_json(
                    200,
                    {
                        "schema": "arch-skillkit/viewers-v1",
                        "viewers": ViewerRegistry().status(),
                    },
                )
                return
            self._error(404, "NOT_FOUND", f"unknown route {parsed.path!r}")
        except Exception as exc:  # noqa: BLE001 - envelope, not traceback
            self._error(500, "INTERNAL", str(exc))

    def _reject(self) -> None:
        if self._authorized():
            self._error(405, "METHOD_NOT_ALLOWED", f"{self.command} not supported; use GET")
        else:
            self._error(401, "UNAUTHORIZED", "missing or invalid bearer token")

    do_POST = _reject
    do_PUT = _reject
    do_PATCH = _reject
    do_DELETE = _reject

    # -- application layer (per-request open, like the MCP adapter) -----

    def _world(self) -> tuple[ArchitectureWorld, CodeIndex | None]:
        repo_path: str = getattr(self.server, "repo_path", "")
        world = ArchitectureWorld.for_repo(repo_path).open()
        index_path = world.workspace / "code.sqlite"
        index = CodeIndex(index_path).open() if index_path.exists() else None
        return world, index

    def _status(self) -> dict[str, Any]:
        world, index = self._world()
        try:
            return get_status(world, code_index=index).model_dump()
        finally:
            if index is not None:
                index.close()
            world.close()

    def _history(self, query: dict[str, list[str]]) -> dict[str, Any]:
        raw = query.get("limit", ["50"])[0]
        try:
            limit = int(raw)
        except ValueError:
            limit = 50
        limit = max(1, min(limit, _MAX_LIMIT))
        from archskillkit.application.queries.history import get_history

        return get_history(RunLedger(), limit=limit).model_dump()


# ---------- server lifecycle -------------------------------------------


def serve(repo_path: str, port: int) -> int:
    """Open the world once (fail fast), bind loopback, register in the
    RuntimeRegistry, print the startup envelope and serve until
    SIGINT/SIGTERM. Always unregisters on the way out."""
    world = ArchitectureWorld.for_repo(repo_path).open()
    project_id = world.project_id
    world.close()

    token = secrets.token_urlsafe(24)
    server = HTTPServer((BIND_HOST, port), _ControlPlaneHandler)
    server.token = token
    server.repo_path = repo_path

    registry = RuntimeRegistry()
    registry.register(
        RuntimeEntry(
            pid=os.getpid(),
            run_id=RUN_ID,
            project_id=project_id,
            command=f"archskillkit {NAME} --repo {repo_path} --port {server.server_port}",
        )
    )

    def _graceful(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _graceful)

    # Single compact line: the startup envelope is a machine contract
    # (process managers parse exactly one line), unlike the human-facing
    # endpoint bodies which are indented.
    print(
        json.dumps(
            {
                "schema": START_SCHEMA,
                "url": f"http://{BIND_HOST}:{server.server_port}",
                "host": BIND_HOST,
                "port": server.server_port,
                "pid": os.getpid(),
                "project_id": project_id,
                "token": token,
                "runtime_registry": "registered",
            }
        ),
        flush=True,
    )

    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        registry.unregister(os.getpid())
    return 0


# ---------- CLI adapter ------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME,
        help="local-only Control Plane HTTP server (read-only"
        " JSON API; binds 127.0.0.1, bearer-token auth)",
    )
    p.add_argument("--repo", required=True)
    p.add_argument(
        "--port", type=int, default=0, help="TCP port (default: 0 = ephemeral, printed on startup)"
    )


def handle(args: argparse.Namespace, world=None) -> int:
    repo_path = str(args.repo)
    try:
        probe = ArchitectureWorld.for_repo(repo_path)
    except RepoNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not probe.db_path.exists():
        print(
            f"error: no Architecture World for {probe.project_id} "
            f"(run: archskillkit init --repo {repo_path})",
            file=sys.stderr,
        )
        return 2
    return serve(repo_path, args.port)
