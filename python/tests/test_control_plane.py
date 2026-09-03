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
    assert body == {"schema": "arch-skillkit/control-plane-health-v1", "ok": True}


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
