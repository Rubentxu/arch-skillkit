"""V2.4 CLI: schema and view commands (M1, docs/v2/55 §2/§4).

Key gate: `schema status` output must validate a REAL `status` output —
schemas are generated from the pydantic models so they cannot drift.
"""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from jsonschema import validate as js_validate

from archskillkit.cli import main
from archskillkit.runtime_state.runtime_registry import RuntimeRegistry
from archskillkit.world import ArchitectureWorld


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return tmp_path


@pytest.fixture()
def repo(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin",
         "https://github.com/rubentxu/fixture.git")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


@pytest.fixture()
def initialized(sandbox, repo, capsys):
    assert main(["init", "--repo", str(repo)]) == 0
    capsys.readouterr()
    return repo


def _fake_binary(directory: Path, name: str, body: str = "exit 0\n") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class TestSchemaCommand:
    def test_schema_status_validates_real_status_output(
            self, sandbox, initialized, capsys):
        assert main(["status", "--repo", str(initialized)]) == 0
        status_payload = json.loads(capsys.readouterr().out)

        assert main(["schema", "status"]) == 0
        schema_doc = json.loads(capsys.readouterr().out)
        assert schema_doc["schema"] == "arch-skillkit/schema-output-v1"
        assert schema_doc["name"] == "status"

        # the M1 gate: a real output validates against the served schema
        js_validate(status_payload, schema_doc["json_schema"])

    def test_schema_lists_available_without_name(self, sandbox, capsys):
        assert main(["schema"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert "status" in payload["available"]
        assert "run-record" in payload["available"]
        assert "viewer-descriptor" in payload["available"]

    def test_schema_every_target_yields_object(self, sandbox, capsys):
        for name in ("status", "explain", "snapshot", "run-record",
                     "action-suggestion", "viewer-descriptor"):
            assert main(["schema", name]) == 0
            doc = json.loads(capsys.readouterr().out)
            assert doc["json_schema"]["type"] == "object"

    def test_schema_unknown_name_fails(self, sandbox, capsys):
        assert main(["schema", "nope"]) == 2
        assert "unknown schema" in capsys.readouterr().err


class TestViewCommand:
    def test_view_routes_to_system_default(self, sandbox, initialized,
                                           capsys, monkeypatch, tmp_path):
        _fake_binary(tmp_path / "bin", "xdg-open")
        monkeypatch.setenv("PATH", f"{tmp_path}/bin:/usr/bin:/bin")
        with ArchitectureWorld.for_repo(initialized) as world:
            artifact = world.workspace / "arrows" / "architecture.arrows"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("arrows-json-placeholder")

        assert main(["view", "--repo", str(initialized),
                     "--format", "arrows"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema"] == "arch-skillkit/view-session-v1"
        assert payload["viewer"] == "system-default"
        assert payload["managed"] is False
        assert payload["argv"][0].endswith("xdg-open")
        assert RuntimeRegistry().active() == []

    def test_view_missing_artifact_fails_with_hint(self, sandbox,
                                                   initialized, capsys):
        assert main(["view", "--repo", str(initialized),
                     "--format", "graphml"]) == 1
        err = capsys.readouterr().err
        assert "no graphml artifact" in err
        assert "archskillkit project" in err

    def test_view_explicit_unavailable_viewer(self, sandbox, initialized,
                                              capsys, monkeypatch, tmp_path):
        with ArchitectureWorld.for_repo(initialized) as world:
            artifact = world.workspace / "diagrams" / "architecture.drawio"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<mxfile/>")
        # no drawio anywhere on this PATH, but git still reachable for
        # the world creation the CLI performs before dispatching
        monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")

        assert main(["view", "--repo", str(initialized),
                     "--format", "drawio",
                     "--with", "drawio-desktop"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.out)["code"] == "VIEWER_UNAVAILABLE"

    def test_view_managed_server_registers_session(self, sandbox,
                                                   initialized, capsys,
                                                   monkeypatch, tmp_path):
        _fake_binary(tmp_path / "bin", "likec4", body="sleep 60\n")
        monkeypatch.setenv("PATH", f"{tmp_path}/bin:/usr/bin:/bin")
        with ArchitectureWorld.for_repo(initialized) as world:
            artifact = world.workspace / "likec4" / "model.c4"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("spec version 2")

        assert main(["view", "--repo", str(initialized),
                     "--format", "likec4"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["managed"] is True
        runtime = RuntimeRegistry()
        assert [e.run_id for e in runtime.active()] == \
            ["viewer-likec4-server"]

        # simulate the server dying while the CLI is gone: the registry
        # entry must be reaped, never leaked into the world
        os.kill(payload["pid"], 9)
        os.waitpid(payload["pid"], 0)
        assert [e.run_id for e in runtime.cleanup_orphans()] == \
            ["viewer-likec4-server"]
        assert runtime.active() == []
