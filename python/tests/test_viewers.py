"""Viewer layer (V2.4 M1, docs/v2/54, 67 slice 5).

Gates under test: registry discovers availability without host
dependencies (fake PATH), managed-server lifecycle integrates the
RuntimeRegistry (register on launch, unregister on stop, reaped when
orphaned), routing falls back to the system default, and viewer
operations never touch the world event log.
"""

import json
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from jsonschema import validate as js_validate

from archskillkit.cli import main
from archskillkit.runtime_state.runtime_registry import RuntimeRegistry
from archskillkit.viewers.contract import (
    ViewerAdapter,
    ViewerCapabilities,
    ViewerDescriptor,
    ViewerUnavailable,
)
from archskillkit.viewers.likec4 import LikeC4Viewer, find_likec4_binary
from archskillkit.viewers.registry import ViewerRegistry, launch, stop
from archskillkit.viewers.system_default import SystemDefaultViewer
from archskillkit.world import ArchitectureWorld

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "design" / "schemas" / "v2.4"


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return tmp_path


def _fake_binary(directory: Path, name: str, body: str = "exit 0\n") -> str:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    # a useful fake advertises the managed-server capability so the
    # capability probe accepts it
    path.write_text(
        f"#!/bin/sh\n"
        f"if [ \"$1\" = \"--help\" ]; then echo 'start serve export'; fi\n"
        f"{body}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


class TestDescriptors:
    def test_builtin_descriptors_match_design_schema(self):
        schema = yaml.safe_load(
            (SCHEMA_DIR / "viewer-descriptor.yaml").read_text())
        for adapter in ViewerRegistry().adapters():
            js_validate(adapter.descriptor().model_dump(), schema)

    def test_system_default_consumes_every_format(self):
        descriptor = SystemDefaultViewer().descriptor()
        assert set(descriptor.consumes) == {
            "likec4", "arrows", "graphml", "jsoncanvas", "drawio"}


class TestProbing:
    def test_likec4_found_via_fake_path(self, monkeypatch, tmp_path):
        fake = _fake_binary(tmp_path / "bin", "likec4")
        monkeypatch.setenv("PATH", str(tmp_path / "bin"))
        monkeypatch.delenv("HOME", raising=False)
        assert find_likec4_binary() == fake
        probe = LikeC4Viewer().probe()
        assert probe["available"] is True
        assert probe["detail"] == fake

    def test_likec4_unavailable_when_nowhere(self, monkeypatch):
        monkeypatch.setenv("PATH", str(Path(__file__).parent))
        monkeypatch.setenv("HOME", str(Path(__file__).parent / "no-home"))
        probe = LikeC4Viewer().probe()
        assert probe["available"] is False

    def test_drawio_unavailable_without_binary(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PATH", str(tmp_path))
        probe = ViewerRegistry().find("drawio-desktop").probe()
        assert probe["available"] is False

    def test_argv_building_is_pure(self, monkeypatch, tmp_path):
        fake = _fake_binary(tmp_path / "bin", "likec4")
        monkeypatch.setenv("PATH", str(tmp_path / "bin"))
        artifact = tmp_path / "likec4" / "model.c4"
        argv = LikeC4Viewer().launch_argv(artifact)
        assert argv[0] == fake
        assert argv[1] == "start"
        assert argv[2] == str(artifact.parent)


class _ManagedSleepServer(ViewerAdapter):
    """Deterministic long-running viewer for lifecycle tests."""

    def descriptor(self) -> ViewerDescriptor:
        return ViewerDescriptor(
            id="sleep-server", name="Sleep server",
            consumes=["likec4"], modes=["MANAGED_SERVER"],
            capabilities=ViewerCapabilities(view=True))

    def probe(self) -> dict:
        return {"available": True, "detail": "test stub"}

    def launch_argv(self, artifact: Path) -> list[str]:
        return [sys.executable, "-c", "import time; time.sleep(60)"]


class TestLaunchLifecycle:
    def test_managed_launch_registers_and_stop_unregisters(
            self, sandbox, tmp_path):
        runtime = RuntimeRegistry()
        session = launch(_ManagedSleepServer(), tmp_path / "model.c4",
                         runtime_registry=runtime)
        assert session.managed is True
        assert [e.run_id for e in runtime.active()] == \
            ["viewer-sleep-server"]

        stop(session, runtime_registry=runtime)
        for _ in range(50):
            if not RuntimeRegistry._pid_alive(session.pid):
                break
            time.sleep(0.02)
        assert RuntimeRegistry._pid_alive(session.pid) is False
        assert runtime.active() == []

    def test_orphaned_viewer_is_reaped_by_cleanup(self, sandbox, tmp_path):
        runtime = RuntimeRegistry()
        session = launch(_ManagedSleepServer(), tmp_path / "model.c4",
                         runtime_registry=runtime)
        session.process.kill()  # orphan the process
        session.process.wait()  # the parent reaps; PID is really gone
        removed = runtime.cleanup_orphans()
        assert [e.run_id for e in removed] == ["viewer-sleep-server"]
        assert runtime.active() == []

    def test_unmanaged_processes_are_not_registered(self, sandbox, tmp_path):
        session = launch(SystemDefaultViewer(), tmp_path / "x.txt")
        assert session.managed is False
        assert RuntimeRegistry().active() == []

    def test_launch_refuses_unavailable_viewer(self, sandbox, tmp_path,
                                               monkeypatch):
        class _Broken(ViewerAdapter):
            def descriptor(self) -> ViewerDescriptor:
                return _ManagedSleepServer().descriptor()

            def probe(self) -> dict:
                return {"available": False, "detail": "missing"}

            def launch_argv(self, artifact: Path) -> list[str]:
                return ["false"]

        with pytest.raises(ViewerUnavailable) as exc:
            launch(_Broken(), tmp_path / "model.c4")
        assert exc.value.code == "VIEWER_UNAVAILABLE"


class TestRouting:
    def test_explicit_viewer_wins(self, sandbox, monkeypatch, tmp_path):
        _fake_binary(tmp_path, "xdg-open")  # keep system-default alive
        monkeypatch.setenv("PATH", str(tmp_path))
        registry = ViewerRegistry()
        chosen = registry.route("likec4", explicit="system-default")
        assert chosen.descriptor().id == "system-default"

    def test_explicit_unknown_format_refused(self, sandbox):
        with pytest.raises(ViewerUnavailable):
            ViewerRegistry().route("graphml", explicit="likec4-server")

    def test_explicit_unavailable_refused(self, sandbox, monkeypatch,
                                          tmp_path):
        monkeypatch.setenv("PATH", str(tmp_path))  # no drawio
        with pytest.raises(ViewerUnavailable):
            ViewerRegistry().route("drawio", explicit="drawio-desktop")

    def test_falls_back_to_first_available(self, sandbox, monkeypatch,
                                           tmp_path):
        monkeypatch.setenv("PATH", str(tmp_path))
        _fake_binary(tmp_path, "likec4")
        registry = ViewerRegistry()
        chosen = registry.route("likec4")
        assert chosen.descriptor().id == "likec4-server"

    def test_nothing_available_raises(self, sandbox, monkeypatch, tmp_path):
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.delenv("HOME", raising=False)
        registry = ViewerRegistry(adapters=[LikeC4Viewer()])
        with pytest.raises(ViewerUnavailable):
            registry.route("likec4")

    def test_viewer_ops_never_touch_world_event_log(
            self, sandbox, tmp_path, repo_with_world):
        world = ArchitectureWorld.for_repo(repo_with_world).open()
        # reopening a world appends pack.loaded events; measure inside a
        # single session so the baseline is meaningful
        before = len(world.graph.events)
        registry = ViewerRegistry()
        registry.status()
        registry.route("likec4")
        launch(SystemDefaultViewer(), tmp_path / "model.c4")
        assert len(world.graph.events) == before
        world.close()


@pytest.fixture()
def repo_with_world(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    for args in (("init", "-q"), ("config", "user.email", "t@t"),
                 ("config", "user.name", "t"), ("add", "-A"),
                 ("commit", "-qm", "init")):
        subprocess.run(["git", "-C", str(repo), *args],
                       check=True, capture_output=True)
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    world.close()
    return repo


class TestViewersCommand:
    def test_viewers_lists_registry_as_json(self, sandbox, capsys):
        assert main(["viewers"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema"] == "arch-skillkit/viewers-v1"
        ids = {v["id"] for v in payload["viewers"]}
        assert {"likec4-server", "drawio-desktop",
                "system-default"} <= ids
        for row in payload["viewers"]:
            assert set(row["probe"]) == {"available", "detail"}
            assert row["capabilities"]["view"] is True

    def test_viewers_needs_no_repository(self, sandbox, capsys):
        # no --repo argument at all: host-level command
        assert main(["viewers"]) == 0
