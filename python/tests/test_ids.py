"""Parity tests for identity + path resolution against the V1 bash helpers.

The expected values below were computed with the reference bash
implementation in skills/architecture-discovery/scripts/lib/common.sh.
If one of these fails, Python and the V1 scripts would disagree about
which workspace belongs to a repository — that must never happen.
"""

import subprocess
from pathlib import Path

from archskillkit.ids import (
    arch_cache_root,
    arch_config_root,
    arch_data_root,
    arch_state_root,
    compute_project_id,
    normalize_remote,
    project_name,
    repo_remote,
    repo_root,
)


class TestNormalizeRemote:
    def test_scp_form_gitlab(self):
        # Exact bash behavior (common.sh): the colon stays when no slash
        # immediately follows it. Identity stability beats prettiness.
        assert normalize_remote("git@gitlab.com:grp/repo.git") == "gitlab.com:grp/repo"

    def test_scp_form_github(self):
        # No slash after the colon → bash keeps the colon (identity quirk).
        assert normalize_remote("git@github.com:Rubentxu/arch-skillkit.git") == (
            "github.com:Rubentxu/arch-skillkit"
        )

    def test_https_with_user(self):
        assert normalize_remote("https://user@github.com/rubentxu/fixture.git") == (
            "github.com/rubentxu/fixture"
        )

    def test_https_plain(self):
        assert normalize_remote("https://github.com/rubentxu/fixture") == (
            "github.com/rubentxu/fixture"
        )

    def test_ssh_with_port(self):
        assert normalize_remote("ssh://git@host:2222/grp/repo.git") == "host/grp/repo"

    def test_git_protocol(self):
        assert normalize_remote("git://host/grp/repo.git") == "host/grp/repo"

    def test_trailing_slash(self):
        assert normalize_remote("https://github.com/grp/repo/") == "github.com/grp/repo"


class TestProjectIdentity:
    def test_name_sanitized(self):
        assert project_name("/tmp/x/My Weird_Repo.Name") == "My-Weird_Repo.Name"

    def test_project_id_seeded_by_remote(self):
        # reference: printf '%s' "github.com/rubentxu/fixture" | sha256sum
        assert compute_project_id("/tmp/anywhere/fixture", "github.com/rubentxu/fixture") == (
            "fixture-b470c680"
        )

    def test_project_id_falls_back_to_path(self):
        # reference: printf '%s' "/tmp/ci/fixture" | sha256sum
        assert compute_project_id("/tmp/ci/fixture", "") == "fixture-e6dffbf7"

    def test_real_world_pipeline_kotlin(self):
        # The id already living in the user's workspace from V1 validation.
        assert compute_project_id(
            "/home/rubentxu/Proyectos/kotlin/pipeline-kotlin",
            "github.com/Rubentxu/pipeline-kotlin",
        ) == "pipeline-kotlin-b7d1577d"


class TestXdgRoots:
    def test_defaults(self, monkeypatch):
        for var in ("ARCH_SKILLKIT_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                    "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            monkeypatch.delenv(var, raising=False)
        expected = Path.home()
        assert str(arch_config_root()) == str(expected / ".config" / "arch-skillkit")
        assert str(arch_data_root()) == str(expected / ".local" / "share" / "arch-skillkit")
        assert str(arch_state_root()) == str(expected / ".local" / "state" / "arch-skillkit")
        assert str(arch_cache_root()) == str(expected / ".cache" / "arch-skillkit")

    def test_xdg_overrides(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        assert str(arch_data_root()) == str(tmp_path / "data" / "arch-skillkit")
        assert str(arch_config_root()) == str(tmp_path / "cfg" / "arch-skillkit")

    def test_arch_skillkit_home_wins_over_xdg_data(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("ARCH_SKILLKIT_HOME", str(tmp_path / "override"))
        assert str(arch_data_root()) == str(tmp_path / "override")


class TestRepoDetection:
    def test_repo_root_and_remote(self, tmp_path):
        repo = tmp_path / "fixture"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "remote", "add", "origin", "https://github.com/rubentxu/fixture.git")
        root = repo_root(repo)
        assert root == repo.resolve()
        assert repo_remote(root) == "github.com/rubentxu/fixture"

    def test_no_remote_gives_empty(self, tmp_path):
        repo = tmp_path / "fixture"
        repo.mkdir()
        _git(repo, "init", "-q")
        root = repo_root(repo)
        assert repo_remote(root) == ""

    def test_outside_repo_is_none(self, tmp_path):
        assert repo_root(tmp_path) is None


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)
