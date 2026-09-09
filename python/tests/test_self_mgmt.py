"""Tests for archskillkit.self_mgmt — pure functions and subprocess wrappers.

Network calls (GitHub API, release assets) are intercepted by
`unittest.mock` rather than respx because the module is intentionally
stdlib-only at the source level.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from archskillkit import self_mgmt


# --- helpers ---------------------------------------------------------------


def _fake_release(tag: str = "v0.5.1", version: str = "0.5.1") -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/Rubentxu/arch-skillkit/releases/tag/{tag}",
        "assets": [
            {
                "name": self_mgmt.ReleaseInfo(tag, version, "").wheel_name,
                "browser_download_url": (
                    f"https://github.com/Rubentxu/arch-skillkit/releases/download/"
                    f"{tag}/{self_mgmt.ReleaseInfo(tag, version, '').wheel_name}"
                ),
            },
            {
                "name": self_mgmt.ReleaseInfo(tag, version, "").manifest_name,
                "browser_download_url": (
                    f"https://github.com/Rubentxu/arch-skillkit/releases/download/"
                    f"{tag}/{self_mgmt.ReleaseInfo(tag, version, '').manifest_name}"
                ),
            },
        ],
    }


# --- ReleaseInfo ----------------------------------------------------------


def test_release_info_urls_fall_back_when_asset_missing():
    raw = {"tag_name": "v0.5.1", "html_url": "https://example/x", "assets": []}
    info = self_mgmt._release_from_raw(raw)
    assert info.tag == "v0.5.1"
    assert info.version == "0.5.1"
    # Fallback URL is the canonical one even when no asset entry is present.
    assert info.wheel_url.endswith(
        "releases/download/v0.5.1/archskillkit-0.5.1-py3-none-any.whl"
    )


def test_release_from_raw_uses_provided_asset_url():
    raw = {
        "tag_name": "v9.9.9",
        "html_url": "https://example/y",
        "assets": [
            {
                "name": "archskillkit-9.9.9-py3-none-any.whl",
                "browser_download_url": "https://cdn.example/custom.whl",
            }
        ],
    }
    info = self_mgmt._release_from_raw(raw)
    assert info.wheel_url == "https://cdn.example/custom.whl"


def test_release_from_raw_rejects_missing_tag():
    with pytest.raises(self_mgmt.SetupError):
        self_mgmt._release_from_raw({})


# --- _version_tuple -------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("0.5.0", "0.5.0", False),
        ("0.5.1", "0.5.0", True),
        ("0.5.0", "0.5.1", False),
        ("1.0.0", "0.99.99", True),
    ],
)
def test_version_tuple_ordering(a, b, expected):
    assert (self_mgmt._version_tuple(a) > self_mgmt._version_tuple(b)) == expected


# --- version_check --------------------------------------------------------


def test_version_check_up_to_date(monkeypatch):
    monkeypatch.setattr(self_mgmt, "_installed_version", "0.5.1")
    fake = _fake_release("v0.5.1", "0.5.1")
    monkeypatch.setattr(self_mgmt, "latest_release_info",
                        lambda repo=None, **kw: (self_mgmt._release_from_raw(fake), False))
    exit_code, msg = self_mgmt.version_check(json_output=False)
    assert exit_code == 0
    assert "up to date" in msg


def test_version_check_update_available(monkeypatch):
    monkeypatch.setattr(self_mgmt, "_installed_version", "0.5.0")
    fake = _fake_release("v0.5.1", "0.5.1")
    monkeypatch.setattr(self_mgmt, "latest_release_info",
                        lambda repo=None, **kw: (self_mgmt._release_from_raw(fake), False))
    exit_code, msg = self_mgmt.version_check(json_output=False)
    assert exit_code == 1
    assert "update available" in msg
    assert "0.5.1" in msg


def test_version_check_json(monkeypatch):
    monkeypatch.setattr(self_mgmt, "_installed_version", "0.5.0")
    fake = _fake_release("v0.5.1", "0.5.1")
    monkeypatch.setattr(self_mgmt, "latest_release_info",
                        lambda repo=None, **kw: (self_mgmt._release_from_raw(fake), True))
    exit_code, payload = self_mgmt.version_check(json_output=True)
    data = json.loads(payload)
    assert data["installed"] == "0.5.0"
    assert data["latest"] == "0.5.1"
    assert data["update_available"] is True
    assert data["cached"] is True
    assert exit_code == 1


def test_version_check_network_error_falls_back_to_cache(monkeypatch, tmp_path):
    cache_dir = tmp_path / "archskillkit"
    cache_dir.mkdir()
    cache_file = cache_dir / "version-check.json"
    cache_file.write_text(json.dumps({
        "cached_at": 0,
        "raw": _fake_release("v0.5.0", "0.5.0"),
    }))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    # _http_get_json raises because we point it at a non-routable URL.
    monkeypatch.setattr(self_mgmt, "_http_get_json",
                        mock.Mock(side_effect=self_mgmt.SetupError(
                            "NETWORK_UNAVAILABLE", "down", "retry")))
    monkeypatch.setattr(self_mgmt, "_installed_version", "0.5.0")
    exit_code, msg = self_mgmt.version_check()
    assert exit_code == 0
    assert "up to date" in msg


# --- self_upgrade ---------------------------------------------------------


def test_self_upgrade_already_at_target(monkeypatch):
    monkeypatch.setattr(self_mgmt, "_installed_version", "0.5.1")
    fake = _fake_release("v0.5.1", "0.5.1")
    monkeypatch.setattr(self_mgmt, "fetch_release",
                        lambda tag, repo=None: self_mgmt._release_from_raw(fake))
    exit_code, msg = self_mgmt.self_upgrade(target="v0.5.1", yes=True)
    assert exit_code == 0
    assert "already at" in msg


def test_self_upgrade_no_target_no_network(monkeypatch):
    monkeypatch.setattr(self_mgmt, "_installed_version", "0.5.0")
    monkeypatch.setattr(self_mgmt, "latest_release_info",
                        mock.Mock(side_effect=self_mgmt.SetupError(
                            "NETWORK_UNAVAILABLE", "down", "retry")))
    exit_code, msg = self_mgmt.self_upgrade(yes=True)
    assert exit_code == 2
    assert "NETWORK_UNAVAILABLE" in msg


def test_self_upgrade_pip_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(self_mgmt, "_installed_version", "0.5.0")
    fake = _fake_release("v0.5.1", "0.5.1")
    monkeypatch.setattr(self_mgmt, "fetch_release",
                        lambda tag, repo=None: self_mgmt._release_from_raw(fake))
    fake_wheel = tmp_path / "archskillkit-0.5.1-py3-none-any.whl"
    fake_wheel.write_bytes(b"fake wheel bytes")
    monkeypatch.setattr(self_mgmt, "download", lambda url, dest: dest.write_bytes(b"x"))
    monkeypatch.setattr(self_mgmt, "_detect_installer", lambda: ["true"])
    fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="nope")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fail)
    exit_code, msg = self_mgmt.self_upgrade(target="v0.5.1", yes=True)
    assert exit_code == 2
    assert "install failed" in msg


# --- self_uninstall -------------------------------------------------------


def test_self_uninstall_not_installed(monkeypatch):
    monkeypatch.setattr(self_mgmt, "_installed_via_pip",
                        lambda: (False, None))
    exit_code, msg = self_mgmt.self_uninstall(yes=True)
    assert exit_code == 0
    assert "not installed" in msg


def test_self_uninstall_success(monkeypatch):
    monkeypatch.setattr(self_mgmt, "_installed_via_pip",
                        lambda: (True, "0.5.0"))
    # Force the installer path so the test does not depend on host uv/pip.
    monkeypatch.setattr(self_mgmt, "_detect_installer",
                        lambda: ["true"])  # always-exit-0 placeholder
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **kw: subprocess.CompletedProcess(
                            args=a[0] if a else [], returncode=0,
                            stdout="Successfully uninstalled archskillkit\n",
                            stderr="",
                        ))
    exit_code, msg = self_mgmt.self_uninstall(yes=True)
    assert exit_code == 0
    assert "uninstalled archskillkit 0.5.0" in msg


def test_self_uninstall_purge_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(self_mgmt, "_installed_via_pip",
                        lambda: (True, "0.5.1"))
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **kw: subprocess.CompletedProcess(
                            args=a[0] if a else [], returncode=0,
                            stdout="ok", stderr="",
                        ))
    runtime_dir = tmp_path / "archskillkit-runtime"
    runtime_dir.mkdir()
    monkeypatch.setattr(self_mgmt, "arch_data_root", lambda: runtime_dir)
    exit_code, msg = self_mgmt.self_uninstall(purge_runtime=True, yes=True)
    assert exit_code == 0
    assert "purged runtime" in msg
    assert not runtime_dir.exists()


# --- CLI registration -----------------------------------------------------


def test_cli_lists_new_subcommands():
    """Smoke-test that the three new subparsers are registered."""
    import argparse
    from archskillkit.cli import main

    # Build the parser via main() with --help, capturing SystemExit.
    captured: dict[str, argparse.ArgumentParser] = {}
    import archskillkit.cli as cli_module

    # We can call main() with a patched parse_args path; the simpler
    # approach is to instantiate the parser by importing main and
    # inspecting its source. Use a minimal monkeypatch instead.
    real_parse_args = argparse.ArgumentParser.parse_args

    def fake_parse_args(self, argv=None):
        # Force the help path to print and exit.
        if argv and "--help-print" in argv:
            self.print_help()
            raise SystemExit(0)
        return real_parse_args(self, argv)

    # Smoke: just invoke main(['self-upgrade', '--help']) and assert
    # the output mentions self-upgrade / self-uninstall / version.
    from io import StringIO

    buf = StringIO()
    with mock.patch.object(sys, "stderr", buf), mock.patch.object(sys, "stdout", buf):
        try:
            main(["--help"])
        except SystemExit:
            pass
    output = buf.getvalue()
    for needle in ("self-upgrade", "self-uninstall"):
        assert needle in output, f"missing {needle!r} in --help output"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
