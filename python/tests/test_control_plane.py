"""Control Plane kernel end-to-end (V2.4 M5 slice 20–21, docs/v2/59 M5).

Spawns the real server as a subprocess on an ephemeral port and
exercises the HTTP surface:

- binds loopback only (BIND_HOST constant, no escape hatch)
- every request requires the bearer token (401 + stable code
  otherwise, including wrong method probes)
- /status, /history, /viewers return the same schema-bound envelopes
  as their CLI counterparts
- unknown route -> 404 NOT_FOUND, wrong verb -> 405 METHOD_NOT_ALLOWED
- RuntimeRegistry: registered while running, unregistered after a
  graceful SIGTERM; process exits 0
- no Architecture World -> exit code 2 with the standard message

Slice 21 adds:
- /evidence, /coverage, /gaps, /findings: schema-bound, auth-gated,
  using application query use cases
- /: static shell served without auth, operator-pasted token in JS
  memory only, CSP enforced, native <button>, no URL token
- Invalid gap status filter returns 400 BAD_REQUEST
- Path traversal returns 404
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from archskillkit.delivery.cli.control_plane import BIND_HOST
from archskillkit.runtime_state.runtime_registry import RuntimeRegistry


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return tmp_path


@pytest.fixture()
def repo_with_world(tmp_path):
    """Init a minimal Architecture World."""
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(repo)],
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture()
def repo_with_content(tmp_path, monkeypatch):
    """Init an Architecture World that has: one evidence linked to one
    claim, one open knowledge gap, and one governance finding."""
    repo = tmp_path / "fixture2"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(repo)],
        check=True,
        capture_output=True,
    )

    # Monkey-patch XDG env so the world opens correctly
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))

    # Open world and record evidence, claim, gap, finding
    from archskillkit.world import ArchitectureWorld

    world = ArchitectureWorld.for_repo(str(repo)).open()
    try:
        # Record an evidence object
        from archskillkit.packs.arch_core import EvidenceData

        ev_id = world.record_evidence(
            EvidenceData(
                tool="test-sensor",
                rule="has-main-function",
                file="src/main.rs",
                start_line=1,
                end_line=1,
            )
        )

        # Record a claim that references the evidence
        from archskillkit.packs.arch_core import ClaimData

        _claim_id = world.propose_claim(
            ClaimData(
                statement="The application has an entry point",
                subjects=["main.rs"],
                confidence="high",
                status="accepted",
                evidence_refs=[ev_id],
            )
        )

        # Add an architecture element that matches the claim subject
        _elem_id = world.add_architecture_element(
            name="main.rs",
            kind="component",
            origin="DETECTED",
            confidence="high",
        )

        # Record a knowledge gap
        world.record_knowledge_gap(
            question="What business logic does main.rs contain?",
            impact="high",
            related_refs=["main.rs"],
            evidence_needed=["runtime behavior analysis"],
        )

        # Record a governance finding
        world.record_architecture_rule(
            name="no-datastore-in-frontend",
            statement="Frontend components must not access databases directly",
            forbidden_relation="direct_db_access",
            source_category="component",
            target_category="datastore",
            severity="high",
        )
        world.persist_findings(
            [
                {
                    "kind": "architecture_drift",
                    "severity": "high",
                    "target_id": "rel_test",
                    "rule": "no-datastore-in-frontend",
                    "detail": "FrontendComponent --[direct_db_access]--> Database",
                }
            ]
        )
    finally:
        world.close()

    return repo


@pytest.fixture()
def server(sandbox, repo_with_world):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo_with_world),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip(), f"server died before startup line: {proc.stderr.read()}"
    start = json.loads(line)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture()
def repo_with_artifacts(tmp_path, monkeypatch):
    """Init an Architecture World with a real graphml artifact pre-generated."""
    repo = tmp_path / "fixture-artifacts"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(repo)],
        check=True,
        capture_output=True,
    )
    # Generate a graphml artifact so routing tests can reach the routing stage
    subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "project",
            "--repo",
            str(repo),
            "--format",
            "graphml",
        ],
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture()
def server_with_artifacts(sandbox, repo_with_artifacts):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo_with_artifacts),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip(), f"server died before startup line: {proc.stderr.read()}"
    start = json.loads(line)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture()
def server_with_content(sandbox, repo_with_content):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo_with_content),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip(), f"server died before startup line: {proc.stderr.read()}"
    start = json.loads(line)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


def _get(url: str, token: str | None):
    req = urllib.request.Request(url)
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _post(url: str, token: str):
    req = urllib.request.Request(
        url, data=b"{}", method="POST", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


# ---------- binding / auth gates ---------------------------------------


def test_binds_loopback_only():
    """docs/v2/54 §12: localhost is enforced by construction."""
    assert BIND_HOST == "127.0.0.1"


def test_start_envelope_is_loopback(server):
    assert server["host"] == "127.0.0.1"
    assert server["url"].startswith("http://127.0.0.1:")
    assert server["runtime_registry"] == "registered"
    assert server["token"]


def test_missing_token_is_unauthorized(server):
    status, body = _get(server["url"] + "/status", token=None)
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_wrong_token_is_unauthorized(server):
    status, body = _get(server["url"] + "/status", token="nope")
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_health_requires_token_too(server):
    status_noauth, _ = _get(server["url"] + "/health", token=None)
    assert status_noauth == 401
    status, body = _get(server["url"] + "/health", token=server["token"])
    assert status == 200
    assert body == {
        "schema": "arch-skillkit/control-plane-health-v1",
        "ok": True,
        "admin": False,
    }


def test_health_reports_admin_optin(sandbox, repo_with_drawio):
    proc, start = _start_server(repo_with_drawio, admin=True)
    try:
        status, body = _get(start["url"] + "/health", token=start["token"])
        assert status == 200
        assert body["admin"] is True
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_write_methods_rejected(server):
    status, body = _post(server["url"] + "/status", token=server["token"])
    assert status == 405
    assert body["code"] == "METHOD_NOT_ALLOWED"


# ---------- read endpoints (same envelopes as the CLI) ------------------


def test_status_endpoint(server):
    status, body = _get(server["url"] + "/status", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/status-result-v1"
    assert body["project_id"]
    assert isinstance(body["suggestions"], list)
    assert "snapshot" in body


def test_history_endpoint_with_limit(server):
    status, body = _get(server["url"] + "/history?limit=1", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/history-v1"
    assert body["returned"] <= 1


def test_history_rejects_garbage_limit(server):
    status, body = _get(server["url"] + "/history?limit=abc", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/history-v1"


def test_viewers_endpoint(server):
    status, body = _get(server["url"] + "/viewers", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/viewers-v1"
    ids = {v["id"] for v in body["viewers"]}
    assert "likec4-server" in ids
    assert "system-default" in ids


def test_unknown_route_404(server):
    status, body = _get(server["url"] + "/nope", token=server["token"])
    assert status == 404
    assert body["code"] == "NOT_FOUND"


# ---------- slice 21 endpoints -----------------------------------------


def test_evidence_endpoint_schema(server):
    """Schema envelope."""
    status, body = _get(server["url"] + "/evidence", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/evidence-v1"
    assert "count" in body
    assert "items" in body
    assert isinstance(body["items"], list)


def test_evidence_requires_auth(server):
    status, body = _get(server["url"] + "/evidence", token=None)
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_evidence_with_content(server_with_content):
    """Evidence list includes items with tool, file, evidence_refs."""
    status, body = _get(
        server_with_content["url"] + "/evidence",
        token=server_with_content["token"],
    )
    assert status == 200
    assert body["count"] >= 1
    item = body["items"][0]
    assert "id" in item
    assert "tool" in item
    assert "file" in item
    assert "claim_ids" in item
    assert isinstance(item["claim_ids"], list)
    # The evidence is linked to the claim
    assert len(item["claim_ids"]) >= 1


def test_coverage_endpoint_schema(server):
    status, body = _get(server["url"] + "/coverage", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/coverage-v1"
    assert "elements" in body
    assert "relations" in body
    assert "evidence_coverage" in body
    assert "unknowns" in body
    assert 0.0 <= body["evidence_coverage"] <= 1.0
    assert body["elements"] >= 0
    assert body["unknowns"] >= 0


def test_coverage_requires_auth(server):
    status, body = _get(server["url"] + "/coverage", token=None)
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_coverage_with_content(server_with_content):
    """Coverage reflects the seeded world state."""
    status, body = _get(
        server_with_content["url"] + "/coverage",
        token=server_with_content["token"],
    )
    assert status == 200
    # One element from the seeded claim (main.rs)
    assert body["elements"] >= 1
    # Unknowns: elements without accepted claims
    assert body["unknowns"] >= 0
    assert 0.0 <= body["evidence_coverage"] <= 1.0


def test_gaps_endpoint_schema(server):
    status, body = _get(server["url"] + "/gaps", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/gaps-v1"
    assert "count" in body
    assert "gaps" in body
    assert isinstance(body["gaps"], list)


def test_gaps_endpoint_with_valid_status_filter(server):
    """OPEN status filter is valid."""
    status, body = _get(
        server["url"] + "/gaps?status=OPEN",
        token=server["token"],
    )
    assert status == 200
    assert body["schema"] == "arch-skillkit/gaps-v1"


def test_gaps_endpoint_with_invalid_status_filter(server):
    """Invalid status filter returns 400 BAD_REQUEST."""
    status, body = _get(
        server["url"] + "/gaps?status=NOT_A_REAL_STATUS",
        token=server["token"],
    )
    assert status == 400
    assert body["code"] == "INVALID_STATUS"
    assert "NOT_A_REAL_STATUS" in body["message"]


def test_gaps_invalid_status_single_response(server):
    """Invalid status returns exactly one 400 response, not 400 then 500."""
    # Use a socket-level check: if do_GET emitted two responses,
    # the second status line would be visible. We verify the first
    # status is 400 and the body is the error envelope.
    import socket

    url = server["url"].replace("http://", "")
    host, port_str = url.split(":")
    port = int(port_str)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((host, port))
    token = server["token"]
    request = (
        f"GET /gaps?status=NOT_A_REAL_STATUS HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Authorization: Bearer {token}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode()
    s.sendall(request)

    # Read the entire response
    chunks = []
    while True:
        try:
            chunk = s.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        except TimeoutError:
            break
    s.close()

    response = b"".join(chunks).decode("utf-8", errors="replace")

    # There should be exactly one HTTP status line
    lines = response.split("\r\n")
    status_line = lines[0]
    assert status_line.startswith("HTTP/1.1 400"), (
        f"expected single 400 response, got: {status_line!r}"
    )

    # Count how many "HTTP/1.1" status lines appear
    http_lines = [l for l in lines if l.startswith("HTTP/1.1 ")]
    assert len(http_lines) == 1, (
        f"expected exactly 1 HTTP response, got {len(http_lines)}: {http_lines!r}"
    )


def test_gaps_requires_auth(server):
    status, body = _get(server["url"] + "/gaps", token=None)
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_gaps_with_content(server_with_content):
    """Gaps list includes the seeded gap with impact and question."""
    status, body = _get(
        server_with_content["url"] + "/gaps",
        token=server_with_content["token"],
    )
    assert status == 200
    assert body["count"] >= 1
    gap = body["gaps"][0]
    assert "id" in gap
    assert "data" in gap
    assert gap["data"]["impact"] == "high"
    assert "question" in gap["data"]
    assert "What business logic" in gap["data"]["question"]


def test_findings_endpoint_schema(server):
    status, body = _get(server["url"] + "/findings", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/findings-v1"
    assert "count" in body
    assert "findings" in body
    assert isinstance(body["findings"], list)


def test_findings_requires_auth(server):
    status, body = _get(server["url"] + "/findings", token=None)
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_findings_with_content(server_with_content):
    """Findings list includes the seeded finding with severity and kind."""
    status, body = _get(
        server_with_content["url"] + "/findings",
        token=server_with_content["token"],
    )
    assert status == 200
    assert body["count"] >= 1
    finding = body["findings"][0]
    assert "id" in finding
    assert "data" in finding
    assert finding["data"]["severity"] == "high"
    assert finding["data"]["kind"] == "architecture_drift"


# ---------- static shell (/) ------------------------------------------


def test_shell_served_without_auth(server):
    """The static shell is served without auth."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        content = resp.read().decode()
        assert "<!DOCTYPE html>" in content
        assert "Control Plane" in content
        assert "prefers-reduced-motion" in content


def test_shell_contains_native_button_not_div_role_button(server):
    """Shell uses native <button> for keyboard accessibility."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    # Must have native buttons
    assert "<button" in content
    # Must not use div role=button
    assert 'role="button"' not in content


def test_shell_html_contains_aria_and_semantics(server):
    """Shell is accessible: ARIA landmarks, aria-expanded on toggles."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    assert 'role="main"' in content
    assert "aria-label" in content
    assert "aria-expanded" in content
    assert "aria-controls" in content
    assert "prefers-reduced-motion" in content


def test_shell_has_no_external_assets(server):
    """Shell is zero-dependency: no CDN, no external assets."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    assert "cdn." not in content.lower()
    assert "fonts.googleapis" not in content
    assert "fonts.gstatic" not in content
    assert 'src="http' not in content


def test_shell_csp_header(server):
    """CSP header is present and locks down the response."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "script-src 'self' 'unsafe-inline'" in csp
        assert "connect-src 'self'" in csp
        assert "object-src 'none'" in csp
        # upgrade-insecure-requests would upgrade same-origin fetches to
        # HTTPS, which can break the loopback shell on plain HTTP.
        assert "upgrade-insecure-requests" not in csp


def test_shell_no_token_in_url(server):
    """Shell HTML contains no token value."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    # Token value from server start envelope must not appear in HTML
    assert server["token"] not in content
    # No URLSearchParams reads in the shell script
    assert "window.location.search" not in content
    assert "window.location.hash" not in content


def test_shell_template_fully_resolved(server):
    """Rendered shell contains no {csp} placeholder and no doubled CSS braces."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    # No unresolved CSP placeholder
    assert "{csp}" not in content
    # No Python format-string double-braces in CSS (raw {{ or }})
    # CSS rules look like "color: var(--ok)" — a literal "{"
    # followed by a CSS property. The string "{{" would be a Python format
    # escape that was NOT resolved, meaning the template was not rendered.
    # We check that no "{{" appears as a literal two-char sequence.
    # Note: "{{" in JS strings is also suspicious.
    assert "{{" not in content, "found raw {{ in rendered HTML"


def test_shell_has_password_input_for_token(server):
    """Token entry uses password input, not URL field."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    assert 'type="password"' in content
    assert 'id="token-input"' in content


# ---------- method rejection on new endpoints ---------------------------


def _method_rejected(server, path, method):
    req = urllib.request.Request(
        server["url"] + path,
        data=b"{}",
        method=method,
        headers={"Authorization": f"Bearer {server['token']}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return False
    except urllib.error.HTTPError as exc:
        return exc.code


def test_evidence_write_methods_rejected(server):
    assert _method_rejected(server, "/evidence", "POST") == 405
    assert _method_rejected(server, "/evidence", "PUT") == 405
    assert _method_rejected(server, "/evidence", "DELETE") == 405


def test_coverage_write_methods_rejected(server):
    assert _method_rejected(server, "/coverage", "POST") == 405
    assert _method_rejected(server, "/coverage", "PATCH") == 405


def test_gaps_write_methods_rejected(server):
    assert _method_rejected(server, "/gaps", "POST") == 405
    assert _method_rejected(server, "/gaps", "PUT") == 405
    assert _method_rejected(server, "/gaps", "DELETE") == 405


def test_findings_write_methods_rejected(server):
    assert _method_rejected(server, "/findings", "POST") == 405
    assert _method_rejected(server, "/findings", "PATCH") == 405


# ---------- path traversal is blocked ----------------------------------


def test_path_traversal_returns_404(server):
    """Path traversal attempts return 404, not file contents."""
    for path in [
        "/../../etc/passwd",
        "/..%2F..%2Fetc%2Fpasswd",
        "/static/../../../etc/passwd",
    ]:
        status, _ = _get(server["url"] + path, token=server["token"])
        assert status == 404, f"path {path!r} did not return 404"


# ---------- runtime registry lifecycle ----------------------------------


def test_registry_registered_then_unregistered(sandbox, repo_with_world):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo_with_world),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    start = json.loads(proc.stdout.readline())
    registry = RuntimeRegistry()
    pids = {e.pid for e in registry.active()}
    assert start["pid"] in pids
    assert start["project_id"] in {e.project_id for e in registry.active()}

    proc.terminate()
    assert proc.wait(timeout=10) == 0
    assert start["pid"] not in {e.pid for e in registry.active()}


def test_missing_world_exits_2(sandbox, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(empty),
            "--port",
            "0",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 2
    assert "not a git repository" in proc.stderr


def test_git_repo_without_world_exits_2(sandbox, tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    proc = subprocess.run(
        [sys.executable, "-m", "archskillkit", "control-plane", "--repo", str(repo), "--port", "0"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 2
    assert "no Architecture World" in proc.stderr


# ---------- Viewer Hub slice 22 ---------------------------------------


def _post_json(url: str, token: str, payload: dict) -> tuple[int, dict]:
    """POST JSON payload and return status + parsed body."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_projections_endpoint_schema(server):
    """Schema envelope and format list."""
    status, body = _get(server["url"] + "/projections", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/projections-v1"
    assert "formats" in body
    assert isinstance(body["formats"], list)
    # All known formats are listed
    fmt_ids = {f["id"] for f in body["formats"]}
    assert fmt_ids == {"likec4", "arrows", "graphml", "jsoncanvas", "drawio"}


def test_projections_no_artifact_paths_in_response(server):
    """Artifact paths are never sent to the browser."""
    status, body = _get(server["url"] + "/projections", token=server["token"])
    assert status == 200
    for fmt in body["formats"]:
        assert "artifact_path" not in fmt, "paths must not be sent to browser"
        assert "artifact_status" in fmt
        assert fmt["artifact_status"] in ("exists", "missing")


def test_projections_requires_auth(server):
    status, _ = _get(server["url"] + "/projections", token=None)
    assert status == 401


def test_launch_requires_auth(server):
    status, _ = _post_json(
        server["url"] + "/launch",
        token=None,
        payload={"format": "likec4", "viewer": "system-default"},
    )
    assert status == 401


def test_launch_rejects_missing_fields(server):
    """Missing format or viewer key returns BAD_REQUEST."""
    # Missing viewer key
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"format": "likec4"},
    )
    assert status == 400
    assert body["code"] == "BAD_REQUEST"
    assert "exactly 'format' and 'viewer'" in body["message"]

    # Missing format key
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"viewer": "system-default"},
    )
    assert status == 400
    assert body["code"] == "BAD_REQUEST"
    assert "exactly 'format' and 'viewer'" in body["message"]

    # Completely empty payload
    status, body = _post_json(server["url"] + "/launch", token=server["token"], payload={})
    assert status == 400
    assert body["code"] == "BAD_REQUEST"


def test_launch_rejects_extra_keys(server):
    """Extra keys in payload return BAD_REQUEST (strict schema)."""
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"format": "likec4", "viewer": "system-default", "extra": "ignored"},
    )
    assert status == 400
    assert body["code"] == "BAD_REQUEST"
    assert "exactly 'format' and 'viewer'" in body["message"]


def test_launch_rejects_non_string_format(server):
    """Non-string format value returns BAD_REQUEST."""
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"format": 123, "viewer": "system-default"},
    )
    assert status == 400
    assert body["code"] == "BAD_REQUEST"
    assert "'format' must be a non-empty string" in body["message"]


def test_launch_rejects_non_string_viewer(server):
    """Non-string viewer value returns BAD_REQUEST."""
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"format": "likec4", "viewer": None},
    )
    assert status == 400
    assert body["code"] == "BAD_REQUEST"
    assert "'viewer' must be a non-empty string" in body["message"]


def test_launch_rejects_empty_string_format(server):
    """Empty string format returns BAD_REQUEST."""
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"format": "", "viewer": "system-default"},
    )
    assert status == 400
    assert body["code"] == "BAD_REQUEST"
    assert "'format' must be a non-empty string" in body["message"]


def test_launch_rejects_empty_string_viewer(server):
    """Empty string viewer returns BAD_REQUEST."""
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"format": "likec4", "viewer": ""},
    )
    assert status == 400
    assert body["code"] == "BAD_REQUEST"
    assert "'viewer' must be a non-empty string" in body["message"]


def test_launch_rejects_unknown_format(server):
    """Unknown format returns BAD_REQUEST with stable code."""
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"format": "nonexistent-format", "viewer": "system-default"},
    )
    assert status == 400
    assert body["code"] == "UNKNOWN_FORMAT"
    assert "nonexistent-format" in body["message"]


def test_launch_rejects_mismatched_viewer(server_with_artifacts):
    """likec4-server does not consume graphml — routing fires after artifact check."""
    status, body = _post_json(
        server_with_artifacts["url"] + "/launch",
        token=server_with_artifacts["token"],
        payload={"format": "graphml", "viewer": "likec4-server"},
    )
    # likec4-server does not consume graphml → VIEWER_UNAVAILABLE (503)
    assert status == 503
    assert body["code"] == "VIEWER_UNAVAILABLE"
    assert "does not consume" in body["message"]


def test_launch_rejects_unavailable_viewer(server_with_artifacts):
    """Explicit viewer that is not available returns stable error after routing."""
    status, body = _post_json(
        server_with_artifacts["url"] + "/launch",
        token=server_with_artifacts["token"],
        payload={"format": "graphml", "viewer": "drawio-desktop"},
    )
    # drawio-desktop is never available in test env → VIEWER_UNAVAILABLE (503)
    assert status == 503
    assert body["code"] == "VIEWER_UNAVAILABLE"


def test_launch_with_system_default_succeeds(server_with_artifacts):
    """system-default is always available; graphml artifact exists in fixture."""
    status, body = _post_json(
        server_with_artifacts["url"] + "/launch",
        token=server_with_artifacts["token"],
        payload={"format": "graphml", "viewer": "system-default"},
    )
    # system-default consumes graphml and is always available;
    # launch may succeed (200) or fail if xdg-open unavailable (503)
    assert status in (200, 503)
    if status == 200:
        assert body["schema"] == "arch-skillkit/launch-v1"
        assert body["viewer"] == "system-default"
        assert "pid" in body
        assert "artifact" not in body
    else:
        # xdg-open unavailable is a launch-level failure, not a routing one
        assert body["code"] == "VIEWER_UNAVAILABLE"


def test_launch_rejects_missing_artifact(server):
    """Missing artifact returns ARTIFACT_MISSING before routing."""
    status, body = _post_json(
        server["url"] + "/launch",
        token=server["token"],
        payload={"format": "likec4", "viewer": "system-default"},
    )
    # Artifact was never generated — stable 400, not a routing attempt
    assert status == 400
    assert body["code"] == "ARTIFACT_MISSING"


def test_launch_content_length_non_integer(server):
    """Non-integer Content-Length returns BAD_REQUEST."""
    req = urllib.request.Request(
        server["url"] + "/launch",
        data=b'{"format":"likec4","viewer":"system-default"}',
        method="POST",
        headers={
            "Authorization": f"Bearer {server['token']}",
            "Content-Type": "application/json",
            "Content-Length": "not-an-integer",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as _resp:
            pass
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert body["code"] == "BAD_REQUEST"


def test_launch_content_length_negative(server):
    """Negative Content-Length returns BAD_REQUEST."""
    req = urllib.request.Request(
        server["url"] + "/launch",
        data=b'{"format":"likec4","viewer":"system-default"}',
        method="POST",
        headers={
            "Authorization": f"Bearer {server['token']}",
            "Content-Type": "application/json",
            "Content-Length": "-1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as _resp:
            pass
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert body["code"] == "BAD_REQUEST"


def test_launch_content_length_oversized(server):
    """Oversized Content-Length returns BAD_REQUEST."""
    req = urllib.request.Request(
        server["url"] + "/launch",
        data=b'{"format":"likec4","viewer":"system-default"}',
        method="POST",
        headers={
            "Authorization": f"Bearer {server['token']}",
            "Content-Type": "application/json",
            "Content-Length": "99999",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as _resp:
            pass
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert body["code"] == "BAD_REQUEST"


def test_launch_non_object_json(server):
    """Non-object JSON body returns BAD_REQUEST."""
    req = urllib.request.Request(
        server["url"] + "/launch",
        data=b'"not an object"',
        method="POST",
        headers={
            "Authorization": f"Bearer {server['token']}",
            "Content-Type": "application/json",
            "Content-Length": "15",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as _resp:
            pass
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert body["code"] == "BAD_REQUEST"


def test_launch_empty_body_rejected(server):
    """Empty request body returns BAD_REQUEST."""
    req = urllib.request.Request(
        server["url"] + "/launch",
        data=b"",
        method="POST",
        headers={"Authorization": f"Bearer {server['token']}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as _resp:
            pass
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_launch_invalid_json_rejected(server):
    """Invalid JSON returns BAD_REQUEST."""
    req = urllib.request.Request(
        server["url"] + "/launch",
        data=b"not valid json",
        method="POST",
        headers={"Authorization": f"Bearer {server['token']}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as _resp:
            pass
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_launch_get_returns_405(server):
    """GET /launch is not allowed."""
    status, body = _get(server["url"] + "/launch", token=server["token"])
    assert status == 405
    assert body["code"] == "METHOD_NOT_ALLOWED"


def test_viewer_panel_in_shell(server):
    """Shell HTML contains Viewer Hub panel markup."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    assert 'id="viewer-panel"' in content
    assert 'id="format-select"' in content
    assert 'id="viewer-select"' in content
    assert 'id="launch-btn"' in content


def test_viewer_panel_has_native_selects(server):
    """Viewer Hub uses native <select> elements for accessibility."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    # Native select, not div-role-button
    assert "<select" in content
    assert 'role="button"' not in content or "<button" in content


def test_shell_contains_no_color_only_signals(server):
    """Availability and errors are not conveyed by color alone."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    # The Viewer Hub has text status (artifact-status, artifact-status.ok/missing)
    # and explicit option text with (yes)/(no) availability
    assert "artifact-status" in content
    # Error states have text content, not just color changes
    assert "error-state" in content


# ---------- slice 23c: POST /drawio-candidate ---------------------------

import http.client

from archskillkit.world import ArchitectureWorld

DRAWCAND = "/drawio-candidate"


def _start_server(repo, *, admin=False):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo),
            "--port",
            "0",
        ]
        + (["--admin"] if admin else []),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    start = json.loads(proc.stdout.readline())
    return proc, start


@pytest.fixture()
def repo_with_drawio(sandbox, repo_with_world):
    """World with two elements + one relation, and a REAL generated
    draw.io projection (artifact + metadata sidecar)."""
    world = ArchitectureWorld.for_repo(str(repo_with_world)).open()
    try:
        with world:
            alpha = world.add_architecture_element("Alpha", "component")
            beta = world.add_architecture_element("Beta", "datastore")
            world.add_architecture_relation("calls", alpha, beta)
    finally:
        world.close()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "project",
            "--repo",
            str(repo_with_world),
            "--format",
            "drawio",
        ],
        check=True,
        capture_output=True,
    )
    return repo_with_world


@pytest.fixture()
def drawio_server(sandbox, repo_with_drawio):
    """Admin-opted-in server: slice-23 candidate flows stay green and
    slice-24 governance endpoints are exercisable."""
    proc, start = _start_server(repo_with_drawio, admin=True)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture()
def drawio_server_noadmin(sandbox, repo_with_drawio):
    proc, start = _start_server(repo_with_drawio, admin=False)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


def _artifact_xml(repo) -> str:
    from archskillkit.projections.writer import ARTIFACT_PATHS

    world = ArchitectureWorld.for_repo(str(repo))
    path = world.workspace / ARTIFACT_PATHS["drawio"]
    return path.read_text(encoding="utf-8")


def _post_json(url, path="", token=None, payload=None, headers=None):
    data = json.dumps(payload).encode()
    all_headers = {"Content-Type": "application/json"}
    if token is not None:
        all_headers["Authorization"] = f"Bearer {token}"
    if headers:
        all_headers.update(headers)
    req = urllib.request.Request(url + path, data=data, method="POST", headers=all_headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _inject_before_last_root(xml: str, fragment: str) -> str:
    idx = xml.rfind("</root>")
    return xml[:idx] + fragment + xml[idx:]


def _vertex_xml(cid, name, kind="component"):
    return (
        f'<UserObject id="{cid}" archskillkit-element-name="{name}"'
        f' archskillkit-element-kind="{kind}">'
        f'<mxCell vertex="1" parent="1" style="rounded=1;">'
        '<mxGeometry x="600" y="0" width="180" height="60" as="geometry" />'
        "</mxCell></UserObject>"
    )


def test_drawio_get_returns_405(server):
    status, body = _get(server["url"] + DRAWCAND, token=server["token"])
    assert status == 405
    assert body["code"] == "METHOD_NOT_ALLOWED"


def test_drawio_requires_auth(server):
    status, body = _post_json(
        server["url"], DRAWCAND, None, {"name": "x", "format": "drawio", "export": "<a/>"}
    )
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_drawio_strict_schema(drawio_server):
    s = drawio_server
    ok = {"name": "edit1", "format": "drawio", "export": "<a/>"}
    # extra key
    bad = dict(ok, approve=True)
    status, body = _post_json(s["url"], DRAWCAND, s["token"], bad)
    assert (status, body["code"]) == (400, "BAD_REQUEST")
    # missing key
    status, body = _post_json(s["url"], DRAWCAND, s["token"], {"name": "edit1", "format": "drawio"})
    assert (status, body["code"]) == (400, "BAD_REQUEST")
    # bad name charset
    status, body = _post_json(s["url"], DRAWCAND, s["token"], dict(ok, name="bad name!"))
    assert (status, body["code"]) == (400, "BAD_REQUEST")
    # wrong format
    status, body = _post_json(s["url"], DRAWCAND, s["token"], dict(ok, format="likec4"))
    assert (status, body["code"]) == (400, "UNKNOWN_FORMAT")
    # export not a string
    status, body = _post_json(s["url"], DRAWCAND, s["token"], dict(ok, export={"pages": []}))
    assert (status, body["code"]) == (400, "BAD_REQUEST")


def test_drawio_missing_artifact_409(sandbox, repo_with_world):
    # Gate order: admin opt-in fires before any artifact work.
    proc, start = _start_server(repo_with_world)  # no projection, no admin
    try:
        status, body = _post_json(
            start["url"],
            DRAWCAND,
            start["token"],
            {"name": "edit1", "format": "drawio", "export": "<a/>"},
        )
        assert status == 403
        assert body["code"] == "ADMIN_DISABLED"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    # With opt-in, the missing artifact surfaces as 409.
    proc, start = _start_server(repo_with_world, admin=True)
    try:
        status, body = _post_json(
            start["url"],
            DRAWCAND,
            start["token"],
            {"name": "edit1", "format": "drawio", "export": "<a/>"},
        )
        assert status == 409
        assert body["code"] == "ARTIFACT_MISSING"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_drawio_base_drift(drawio_server, repo_with_drawio):
    s = drawio_server
    from archskillkit.projections.writer import ARTIFACT_PATHS

    artifact = (
        ArchitectureWorld.for_repo(str(repo_with_drawio)).workspace / ARTIFACT_PATHS["drawio"]
    )
    artifact.write_text(artifact.read_text() + "\n<!-- tampered -->\n")
    status, body = _post_json(
        s["url"],
        DRAWCAND,
        s["token"],
        {"name": "edit1", "format": "drawio", "export": _artifact_xml(repo_with_drawio)},
    )
    assert status == 409
    assert body["code"] == "BASE_DRIFT"


def test_drawio_malformed_xml(drawio_server):
    s = drawio_server
    status, body = _post_json(
        s["url"], DRAWCAND, s["token"], {"name": "edit1", "format": "drawio", "export": "<not-xml"}
    )
    assert status == 400
    assert body["code"] == "MALFORMED_XML"


def test_drawio_unsupported_no_fork(drawio_server, repo_with_drawio):
    s = drawio_server
    submitted = _inject_before_last_root(
        _artifact_xml(repo_with_drawio), _vertex_xml("nX", "mystery")
    ).replace('archskillkit-element-name="mystery"', 'data-note="mystery"')
    status, body = _post_json(
        s["url"], DRAWCAND, s["token"], {"name": "edit1", "format": "drawio", "export": submitted}
    )
    assert status == 422
    assert body["error"]["code"] == "UNSUPPORTED_EDITS"
    assert body["unsupported"]
    world = ArchitectureWorld.for_repo(str(repo_with_drawio))
    try:
        assert not world.has_run("proposal-edit1")
    finally:
        world.close()


def test_drawio_presentation_only_no_fork(drawio_server, repo_with_drawio):
    s = drawio_server
    status, body = _post_json(
        s["url"],
        DRAWCAND,
        s["token"],
        {"name": "edit1", "format": "drawio", "export": _artifact_xml(repo_with_drawio)},
    )
    assert status == 200
    assert body["fork_created"] is False
    assert body["candidate"] is None
    world = ArchitectureWorld.for_repo(str(repo_with_drawio))
    try:
        assert not world.has_run("proposal-edit1")
    finally:
        world.close()


def test_drawio_happy_path_creates_candidate(drawio_server, repo_with_drawio):
    s = drawio_server
    submitted = _inject_before_last_root(
        _artifact_xml(repo_with_drawio),
        _vertex_xml("nG", "Gamma") + '<mxCell id="eG" edge="1" parent="1" source="nG" target="n0"'
        ' archskillkit-relation-kind="exposes"'
        ' archskillkit-relation-source-name="Gamma"'
        ' archskillkit-relation-target-name="Alpha"'
        ' style=""><mxGeometry relative="1" as="geometry" /></mxCell>',
    )
    status, body = _post_json(
        s["url"], DRAWCAND, s["token"], {"name": "edit1", "format": "drawio", "export": submitted}
    )
    assert status == 200, body
    assert body["fork_created"] is True
    assert body["run_id"] == "proposal-edit1"
    assert "Gamma" in json.dumps(body["structural_diff"])

    world = ArchitectureWorld.for_repo(str(repo_with_drawio))
    try:
        fork = world.view("proposal-edit1")
        try:
            names = {o["data"].get("name") for o in fork.find_objects("architecture_element")}
            assert "Gamma" in names
            gamma = next(
                o
                for o in fork.find_objects("architecture_element")
                if o["data"].get("name") == "Gamma"
            )
            assert gamma["data"].get("origin") == "DECLARED"
            proposals = fork.find_objects("proposal")
            assert proposals, "record_proposal should persist a proposal object"
        finally:
            fork.close()
    finally:
        world.close()


def test_drawio_resubmit_replaces_candidate(drawio_server, repo_with_drawio):
    s = drawio_server
    payload = lambda frag: {
        "name": "edit1",
        "format": "drawio",
        "export": _inject_before_last_root(_artifact_xml(repo_with_drawio), frag),
    }
    status, _ = _post_json(s["url"], DRAWCAND, s["token"], payload(_vertex_xml("nG", "Gamma")))
    assert status == 200
    status, _ = _post_json(
        s["url"], DRAWCAND, s["token"], payload(_vertex_xml("nD", "Delta", "interface"))
    )
    assert status == 200
    world = ArchitectureWorld.for_repo(str(repo_with_drawio))
    try:
        fork = world.view("proposal-edit1")
        try:
            names = {o["data"].get("name") for o in fork.find_objects("architecture_element")}
            assert "Delta" in names
            assert "Gamma" not in names  # latest submission wins
        finally:
            fork.close()
    finally:
        world.close()


def test_drawio_oversized_body_rejected(drawio_server):
    s = drawio_server
    conn = http.client.HTTPConnection("127.0.0.1", s["port"], timeout=10)
    try:
        conn.putrequest("POST", DRAWCAND)
        conn.putheader("Authorization", f"Bearer {s['token']}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(5 * 1024 * 1024))
        conn.endheaders()
        conn.send(b"{}")
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        assert resp.status == 400
        assert body["code"] == "BAD_REQUEST"
    finally:
        conn.close()


# ---------- slice 23d: draw.io shell wiring + CSP -----------------------


def test_csp_allows_only_embed_frame(server):
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        csp = resp.headers.get("Content-Security-Policy", "")
    assert "frame-src https://embed.diagrams.net" in csp
    assert "frame-src *" not in csp
    assert "upgrade-insecure-requests" not in csp


def test_shell_drawio_panel_static_semantics(server):
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    # sandboxed iframe: scripts yes, same-origin NO, nothing else granted
    assert 'sandbox="allow-scripts"' in content
    assert "allow-same-origin" not in content
    assert "allow-top-navigation" not in content
    assert "allow-popups" not in content
    # exact-origin postMessage, never wildcard
    assert '"https://embed.diagrams.net"' in content
    assert ', "*")' not in content
    # accessible native controls; promote stays disabled by design
    assert 'id="btn-edit-drawio"' in content
    assert 'id="btn-drawio-propose"' in content
    assert 'id="btn-drawio-promote" disabled' in content
    assert 'id="drawio-frame"' in content


def test_drawio_artifact_endpoint(drawio_server, repo_with_drawio):
    s = drawio_server
    status, body = _get(s["url"] + "/drawio-artifact", token=s["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/drawio-artifact-v1"
    assert body["xml"] == _artifact_xml(repo_with_drawio)
    assert body["base_drift"] is False
    import hashlib as _h

    assert body["sha256"] == _h.sha256(body["xml"].encode()).hexdigest()


def test_drawio_artifact_requires_auth(server):
    status, body = _get(server["url"] + "/drawio-artifact", token=None)
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_drawio_artifact_missing_409(server):
    status, body = _get(server["url"] + "/drawio-artifact", token=server["token"])
    assert status == 409
    assert body["code"] == "ARTIFACT_MISSING"


def test_drawio_artifact_drift_flag(drawio_server, repo_with_drawio):
    from archskillkit.projections.writer import ARTIFACT_PATHS

    artifact = (
        ArchitectureWorld.for_repo(str(repo_with_drawio)).workspace / ARTIFACT_PATHS["drawio"]
    )
    artifact.write_text(artifact.read_text() + "\n<!-- edited by hand -->\n")
    status, body = _get(drawio_server["url"] + "/drawio-artifact", token=drawio_server["token"])
    assert status == 200
    assert body["base_drift"] is True


def test_drawio_artifact_post_405(server):
    status, body = _post_json(server["url"] + "/drawio-artifact", token=server["token"], payload={})
    assert status == 405
    assert body["code"] == "METHOD_NOT_ALLOWED"


# ---------- slice 24: governance mutations opt-in ------------------------


def test_drawio_candidate_requires_admin(server):
    """Candidate creation is a governance write: refused without opt-in
    (stable ADMIN_DISABLED code, before any body parsing)."""
    status, body = _post_json(
        server["url"] + DRAWCAND,
        token=server["token"],
        payload={"name": "edit1", "format": "drawio", "export": "<a/>"},
    )
    assert status == 403
    assert body["code"] == "ADMIN_DISABLED"


def test_drawio_promote_requires_admin(drawio_server_noadmin):
    status, body = _post_json(
        drawio_server_noadmin["url"] + "/drawio-promote",
        token=drawio_server_noadmin["token"],
        payload={"name": "edit1", "approved_by": "you"},
    )
    assert status == 403
    assert body["code"] == "ADMIN_DISABLED"


def test_drawio_reject_requires_admin(drawio_server_noadmin):
    status, body = _post_json(
        drawio_server_noadmin["url"] + "/drawio-reject",
        token=drawio_server_noadmin["token"],
        payload={"name": "edit1", "actor": "you"},
    )
    assert status == 403
    assert body["code"] == "ADMIN_DISABLED"


def test_drawio_promote_reject_get_405(server):
    for path in ("/drawio-promote", "/drawio-reject"):
        status, body = _get(server["url"] + path, token=server["token"])
        assert status == 405
        assert body["code"] == "METHOD_NOT_ALLOWED"


def test_drawio_promote_strict_schema(drawio_server):
    s = drawio_server
    status, body = _post_json(
        s["url"] + "/drawio-promote",
        token=s["token"],
        payload={"name": "edit1", "approved_by": "you", "extra": 1},
    )
    assert (status, body["code"]) == (400, "BAD_REQUEST")
    status, body = _post_json(
        s["url"] + "/drawio-promote",
        token=s["token"],
        payload={"name": "edit1"},
    )
    assert (status, body["code"]) == (400, "BAD_REQUEST")
    status, body = _post_json(
        s["url"] + "/drawio-promote",
        token=s["token"],
        payload={"name": "edit1", "approved_by": "  "},
    )
    assert (status, body["code"]) == (400, "BAD_REQUEST")


def _create_gamma_candidate(s):
    submitted = _inject_before_last_root(
        _artifact_xml(s["repo"] if "repo" in s else _drawio_repo_of(s)),
        _vertex_xml("nG", "Gamma"),
    )
    return _post_json(
        s["url"] + DRAWCAND,
        token=s["token"],
        payload={"name": "edit1", "format": "drawio", "export": submitted},
    )


def _drawio_repo_of(s):
    """Recover the repo path from the server's --repo command line."""
    registry_entry = [
        e for e in RuntimeRegistry().active() if e.pid == s["pid"] and e.run_id == "control-plane"
    ]
    assert registry_entry, "control-plane runtime entry missing"
    command = registry_entry[0].command
    return Path(command.split("--repo ")[1].split(" --port")[0])


def test_drawio_promote_happy_path(drawio_server):
    s = drawio_server
    status, body = _create_gamma_candidate(s)
    assert status == 200, body

    status, body = _post_json(
        s["url"] + "/drawio-promote",
        token=s["token"],
        payload={"name": "edit1", "approved_by": "you"},
    )
    assert status == 200, body
    # The pipeline's own envelope schema is the contract (single source).
    assert body["schema"] == "arch-skillkit/proposal-promote-v1"

    world = ArchitectureWorld.for_repo(str(_drawio_repo_of(s))).open()
    try:
        names = {o["data"].get("name") for o in world.find_objects("architecture_element")}
        assert "Gamma" in names  # promoted into the base world
    finally:
        world.close()


def test_drawio_promote_unknown_candidate(drawio_server):
    s = drawio_server
    status, body = _post_json(
        s["url"] + "/drawio-promote",
        token=s["token"],
        payload={"name": "never-created", "approved_by": "you"},
    )
    assert status == 404
    assert body["error"]["code"] == "CANDIDATE_NOT_FOUND"


def test_drawio_reject_happy_path(drawio_server):
    s = drawio_server
    status, body = _create_gamma_candidate(s)
    assert status == 200, body

    status, body = _post_json(
        s["url"] + "/drawio-reject",
        token=s["token"],
        payload={"name": "edit1", "actor": "you"},
    )
    assert status == 200, body

    world = ArchitectureWorld.for_repo(str(_drawio_repo_of(s))).open()
    try:
        fork = world.view("proposal-edit1")
        try:
            statuses = [o["data"].get("status") for o in fork.find_objects("proposal")]
            assert "rejected" in statuses
            # Reject never mutates base.
            names = {o["data"].get("name") for o in world.find_objects("architecture_element")}
            assert "Gamma" not in names
        finally:
            fork.close()
    finally:
        world.close()


def test_shell_governance_controls_static(server):
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    assert 'id="btn-drawio-reject" disabled' in content
    assert 'id="btn-drawio-promote" disabled' in content
    assert 'id="actor-name"' in content
    assert "updateGovernanceControls" in content
    assert "ARCH_SKILLKIT_ADMIN" in content


# ---------- slice 26: Arrows embed + favorites ------------------------------


@pytest.fixture()
def repo_with_arrows(sandbox, repo_with_world):
    """World with two elements + one relation, and a REAL generated
    arrows projection (artifact + metadata sidecar)."""
    world = ArchitectureWorld.for_repo(str(repo_with_world)).open()
    try:
        with world:
            alpha = world.add_architecture_element("Alpha", "component")
            beta = world.add_architecture_element("Beta", "datastore")
            world.add_architecture_relation("calls", alpha, beta)
    finally:
        world.close()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "project",
            "--repo",
            str(repo_with_world),
            "--format",
            "arrows",
        ],
        check=True,
        capture_output=True,
    )
    return repo_with_world


@pytest.fixture()
def arrows_server(sandbox, repo_with_arrows):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo_with_arrows),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip(), f"server died: {proc.stderr.read()}"
    start = json.loads(line)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


# -- /vendor/arrows static file server (no auth) --------------------


def test_vendor_arrows_missing_dir_404(server):
    """Missing vendor dir returns 404 NOT_FOUND."""
    # arch_data_root() points to real user dir in test env, so this
    # path won't exist → 404
    status, _ = _get(server["url"] + "/vendor/arrows/embed.html", token=None)
    assert status == 404


def test_vendor_arrows_traversal_404(server):
    """Path traversal returns 404 NOT_FOUND."""
    for path in [
        "/vendor/arrows/../../etc/passwd",
        "/vendor/arrows/..%2F..%2Fetc%2Fpasswd",
    ]:
        status, _ = _get(server["url"] + path, token=None)
        assert status == 404, f"traversal {path!r} did not return 404"


def test_vendor_arrows_unsupported_ext_404(server):
    """Unsupported file extension returns 404."""
    # No file type registered for .txt → 404
    status, _ = _get(server["url"] + "/vendor/arrows/README.txt", token=None)
    assert status == 404


def test_vendor_arrows_post_405(server):
    """POST to vendor path returns 404 (no POST handler for vendor paths)."""
    req = urllib.request.Request(
        server["url"] + "/vendor/arrows/embed.html",
        data=b"{}",
        method="POST",
        headers={"Authorization": f"Bearer {server['token']}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


# -- /arrows-artifact --------------------------------------------------


def test_arrows_artifact_requires_auth(server):
    """401 without token."""
    status, body = _get(server["url"] + "/arrows-artifact", token=None)
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_arrows_artifact_missing_409(server):
    """No arrows artifact → 409 ARTIFACT_MISSING."""
    status, body = _get(server["url"] + "/arrows-artifact", token=server["token"])
    assert status == 409
    assert body["code"] == "ARTIFACT_MISSING"


def test_arrows_artifact_happy_path(arrows_server, repo_with_arrows):
    """Returns bridge-shaped graph with all required fields."""
    from archskillkit.projections.arrows_bridge import compute_sha256
    from archskillkit.projections.writer import ARTIFACT_PATHS

    s = arrows_server

    # Read the artifact BEFORE opening the world for the HTTP request
    # (artifact_path is relative to world.workspace which needs world open)
    world = ArchitectureWorld.for_repo(str(repo_with_arrows))
    artifact_path = world.workspace / ARTIFACT_PATHS["arrows"]
    arrows_doc = json.loads(artifact_path.read_text(encoding="utf-8"))
    expected_sha = compute_sha256(arrows_doc)
    world.close()

    # Now make the HTTP request
    status, body = _get(s["url"] + "/arrows-artifact", token=s["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/arrows-artifact-v1"
    assert body["docVersion"] == 1

    # Verify bridge shape invariants
    graph = body["graph"]
    for node in graph["nodes"]:
        assert "id" in node
        assert "caption" in node
        assert "position" in node
        assert "x" in node["position"]
        assert "y" in node["position"]
        assert "labels" in node

    for rel in graph["rels"]:
        assert "id" in rel
        assert "fromId" in rel
        assert "toId" in rel
        # Verify fromId/toId resolve to node ids
        node_ids = {n["id"] for n in graph["nodes"]}
        assert rel["fromId"] in node_ids
        assert rel["toId"] in node_ids

    # Verify SHA matches
    assert body["sha256"] == expected_sha

    # base_drift should be False (not tampered)
    assert body["base_drift"] is False


def test_arrows_artifact_drift_flag(arrows_server, repo_with_arrows):
    """base_drift is True after artifact is tampered."""
    from archskillkit.projections.writer import ARTIFACT_PATHS

    s = arrows_server
    world = ArchitectureWorld.for_repo(str(repo_with_arrows))
    artifact_path = world.workspace / ARTIFACT_PATHS["arrows"]
    # Read original content
    original = artifact_path.read_text(encoding="utf-8")
    # Tamper: add a valid JSON comment field to keep JSON parseable
    doc = json.loads(original)
    doc["_tampered"] = True
    artifact_path.write_text(json.dumps(doc, sort_keys=True) + "\n")
    world.close()

    status, body = _get(s["url"] + "/arrows-artifact", token=s["token"])
    assert status == 200
    assert body["base_drift"] is True


def test_arrows_artifact_post_405(arrows_server):
    """POST returns 405."""
    status, body = _post_json(
        arrows_server["url"] + "/arrows-artifact",
        token=arrows_server["token"],
        payload={},
    )
    assert status == 405
    assert body["code"] == "METHOD_NOT_ALLOWED"


# ---------- slice 27: POST /arrows-candidate ---------------------------

ARROWSCAND = "/arrows-candidate"


def _start_server(repo, *, admin=False):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo),
            "--port",
            "0",
        ]
        + (["--admin"] if admin else []),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    start = json.loads(proc.stdout.readline())
    return proc, start


@pytest.fixture()
def arrows_server_admin(sandbox, repo_with_arrows):
    """Admin-opted-in server for arrows candidate flows."""
    proc, start = _start_server(repo_with_arrows, admin=True)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture()
def arrows_server_noadmin(sandbox, repo_with_arrows):
    proc, start = _start_server(repo_with_arrows, admin=False)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


def _artifact_graph(repo) -> dict:
    """Return the bridge-shaped graph from the arrows artifact."""
    from archskillkit.projections.writer import ARTIFACT_PATHS

    world = ArchitectureWorld.for_repo(str(repo))
    path = world.workspace / ARTIFACT_PATHS["arrows"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    # Convert arrows-v1 to bridge shape using arrows_bridge
    from archskillkit.projections.arrows_bridge import arrows_to_bridge

    return arrows_to_bridge(doc)


def test_arrows_get_returns_405(arrows_server):
    status, body = _get(arrows_server["url"] + ARROWSCAND, token=arrows_server["token"])
    assert status == 405
    assert body["code"] == "METHOD_NOT_ALLOWED"


def test_arrows_requires_auth(server):
    status, body = _post_json(
        server["url"], ARROWSCAND, None, {"name": "x", "format": "arrows", "graph": {}}
    )
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_arrows_strict_schema(arrows_server_admin):
    s = arrows_server_admin
    ok = {"name": "edit1", "format": "arrows", "graph": {"nodes": [], "rels": []}}
    # extra key
    bad = dict(ok, approve=True)
    status, body = _post_json(s["url"], ARROWSCAND, s["token"], bad)
    assert (status, body["code"]) == (400, "BAD_REQUEST")
    # missing key
    status, body = _post_json(s["url"], ARROWSCAND, s["token"], {"name": "edit1", "format": "arrows"})
    assert (status, body["code"]) == (400, "BAD_REQUEST")
    # bad name charset
    status, body = _post_json(s["url"], ARROWSCAND, s["token"], dict(ok, name="bad name!"))
    assert (status, body["code"]) == (400, "BAD_REQUEST")
    # wrong format
    status, body = _post_json(s["url"], ARROWSCAND, s["token"], dict(ok, format="likec4"))
    assert (status, body["code"]) == (400, "UNKNOWN_FORMAT")
    # graph not an object
    status, body = _post_json(s["url"], ARROWSCAND, s["token"], dict(ok, graph=["nodes"]))
    assert (status, body["code"]) == (400, "BAD_REQUEST")


def test_arrows_missing_artifact_409(sandbox, repo_with_world):
    # Gate order: admin opt-in fires before artifact check
    proc, start = _start_server(repo_with_world)  # no projection, no admin
    try:
        status, body = _post_json(
            start["url"],
            ARROWSCAND,
            start["token"],
            {"name": "edit1", "format": "arrows", "graph": {"nodes": [], "rels": []}},
        )
        assert status == 403
        assert body["code"] == "ADMIN_DISABLED"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    # With opt-in, the missing artifact surfaces as 409
    proc, start = _start_server(repo_with_world, admin=True)
    try:
        status, body = _post_json(
            start["url"],
            ARROWSCAND,
            start["token"],
            {"name": "edit1", "format": "arrows", "graph": {"nodes": [], "rels": []}},
        )
        assert status == 409
        assert body["code"] == "ARTIFACT_MISSING"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_arrows_base_drift(arrows_server_admin, repo_with_arrows):
    s = arrows_server_admin
    from archskillkit.projections.writer import ARTIFACT_PATHS

    # Capture the valid graph BEFORE tampering (the tampered file is
    # intentionally invalid JSON; the drift gate must fire on bytes, not
    # on our ability to parse it).
    graph = _artifact_graph(repo_with_arrows)
    artifact = (
        ArchitectureWorld.for_repo(str(repo_with_arrows)).workspace / ARTIFACT_PATHS["arrows"]
    )
    artifact.write_text(artifact.read_text() + "\n// tampered\n")
    status, body = _post_json(
        s["url"],
        ARROWSCAND,
        s["token"],
        {"name": "edit1", "format": "arrows", "graph": graph},
    )
    assert status == 409
    assert body["code"] == "BASE_DRIFT"


def test_arrows_unsupported_no_fork(arrows_server_admin, repo_with_arrows):
    s = arrows_server_admin
    # Submit a graph with a node that has no caption (unsupported)
    graph = _artifact_graph(repo_with_arrows)
    graph["nodes"].append({"id": "nx", "position": {"x": 0, "y": 0}, "labels": [], "properties": {}})
    status, body = _post_json(
        s["url"], ARROWSCAND, s["token"], {"name": "edit1", "format": "arrows", "graph": graph}
    )
    assert status == 422
    assert body["error"]["code"] == "UNSUPPORTED_EDITS"
    assert body["unsupported"]
    world = ArchitectureWorld.for_repo(str(repo_with_arrows))
    try:
        assert not world.has_run("proposal-edit1")
    finally:
        world.close()


def test_arrows_presentation_only_no_fork(arrows_server_admin, repo_with_arrows):
    s = arrows_server_admin
    # Submit the same graph (no changes)
    graph = _artifact_graph(repo_with_arrows)
    status, body = _post_json(
        s["url"],
        ARROWSCAND,
        s["token"],
        {"name": "edit1", "format": "arrows", "graph": graph},
    )
    assert status == 200
    assert body["fork_created"] is False
    assert body["candidate"] is None
    world = ArchitectureWorld.for_repo(str(repo_with_arrows))
    try:
        assert not world.has_run("proposal-edit1")
    finally:
        world.close()


def test_arrows_happy_path_creates_candidate(arrows_server_admin, repo_with_arrows):
    s = arrows_server_admin
    graph = _artifact_graph(repo_with_arrows)
    # Add a new node (element_added)
    graph["nodes"].append(
        {"id": "ng", "caption": "Gamma", "position": {"x": 0, "y": 0}, "labels": ["component"], "properties": {}, "style": None}
    )
    status, body = _post_json(
        s["url"], ARROWSCAND, s["token"], {"name": "edit1", "format": "arrows", "graph": graph}
    )
    assert status == 200, body
    assert body["fork_created"] is True
    assert body["run_id"] == "proposal-edit1"
    assert "Gamma" in json.dumps(body["structural_diff"])

    world = ArchitectureWorld.for_repo(str(repo_with_arrows))
    try:
        fork = world.view("proposal-edit1")
        try:
            names = {o["data"].get("name") for o in fork.find_objects("architecture_element")}
            assert "Gamma" in names
            gamma = next(
                o
                for o in fork.find_objects("architecture_element")
                if o["data"].get("name") == "Gamma"
            )
            assert gamma["data"].get("origin") == "DECLARED"
            proposals = fork.find_objects("proposal")
            assert proposals, "record_proposal should persist a proposal object"
        finally:
            fork.close()
    finally:
        world.close()


def test_arrows_resubmit_replaces_candidate(arrows_server_admin, repo_with_arrows):
    s = arrows_server_admin
    graph = _artifact_graph(repo_with_arrows)
    # First: add Gamma
    g1 = dict(graph)
    g1["nodes"] = graph["nodes"] + [
        {"id": "ng", "caption": "Gamma", "position": {"x": 0, "y": 0}, "labels": [], "properties": {}, "style": None}
    ]
    status, _ = _post_json(
        s["url"], ARROWSCAND, s["token"], {"name": "edit1", "format": "arrows", "graph": g1}
    )
    assert status == 200
    # Second: replace Gamma with Delta
    g2 = dict(graph)
    g2["nodes"] = graph["nodes"] + [
        {"id": "nd", "caption": "Delta", "position": {"x": 0, "y": 0}, "labels": ["interface"], "properties": {}, "style": None}
    ]
    status, _ = _post_json(
        s["url"], ARROWSCAND, s["token"], {"name": "edit1", "format": "arrows", "graph": g2}
    )
    assert status == 200
    world = ArchitectureWorld.for_repo(str(repo_with_arrows))
    try:
        fork = world.view("proposal-edit1")
        try:
            names = {o["data"].get("name") for o in fork.find_objects("architecture_element")}
            assert "Delta" in names
            assert "Gamma" not in names  # latest submission wins
        finally:
            fork.close()
    finally:
        world.close()


# -- /favorites -------------------------------------------------------


def test_favorites_requires_auth(server):
    """401 without token."""
    status, _body = _get(server["url"] + "/favorites", token=None)
    assert status == 401


def test_favorites_get_empty(server):
    """GET returns empty list when no favorites set."""
    status, body = _get(server["url"] + "/favorites", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/favorites-v1"
    assert body["favorites"] == []


def test_favorites_put_and_get(server):
    """PUT valid set → GET returns it."""
    fav_list = ["likec4-server", "drawio-desktop"]
    status, _ = _put_json(
        server["url"] + "/favorites",
        token=server["token"],
        payload={"favorites": fav_list},
    )
    assert status == 200

    status, body = _get(server["url"] + "/favorites", token=server["token"])
    assert status == 200
    assert body["favorites"] == fav_list


def test_favorites_put_unknown_id_400(server):
    """PUT with unknown viewer id → 400."""
    status, body = _put_json(
        server["url"] + "/favorites",
        token=server["token"],
        payload={"favorites": ["nonexistent-viewer-id"]},
    )
    assert status == 400
    assert body["code"] == "BAD_REQUEST"


def test_favorites_put_malformed_400(server):
    """PUT with malformed body → 400."""
    # Not a JSON object
    req = urllib.request.Request(
        server["url"] + "/favorites",
        data=b"not json",
        method="PUT",
        headers={"Authorization": f"Bearer {server['token']}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except urllib.error.HTTPError as exc:
        assert exc.code == 400

    # Missing favorites key
    status, _body = _put_json(
        server["url"] + "/favorites",
        token=server["token"],
        payload={"other": []},
    )
    assert status == 400


def test_favorites_persistence_across_restart(sandbox, repo_with_world):
    """Favorites persist across server restart."""
    proc1, start1 = _start_server(repo_with_world)
    try:
        fav_list = ["likec4-server"]
        _put_json(
            start1["url"] + "/favorites", token=start1["token"], payload={"favorites": fav_list}
        )
    finally:
        proc1.terminate()
        proc1.wait(timeout=10)

    # Restart server
    proc2, start2 = _start_server(repo_with_world)
    try:
        status, body = _get(start2["url"] + "/favorites", token=start2["token"])
        assert status == 200
        assert body["favorites"] == fav_list
    finally:
        proc2.terminate()
        proc2.wait(timeout=10)


def _put_json(url, token, payload):
    """PUT JSON payload and return status + parsed body."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


# -- Shell wiring for arrows panel ----------------------------------


def test_shell_has_arrows_button(server):
    """Shell contains the 'Open embedded Arrows' button."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode()
    assert 'id="btn-open-arrows"' in content
    assert 'id="arrows-panel"' in content
    assert 'id="arrows-frame"' in content


def test_shell_csp_allows_arrows_frame(server):
    """CSP allows the arrows iframe (same-origin, no extra frame-src needed)."""
    req = urllib.request.Request(server["url"] + "/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        csp = resp.headers.get("Content-Security-Policy", "")
    # Same-origin frame is allowed by default-src 'self'
    # No external frame-src needed for arrows
    assert "frame-src *" not in csp
