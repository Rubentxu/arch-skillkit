"""Agent governance tests (V2.4 M4, docs/v2/59 slice 16 acceptance:
"prompt hash/skill revision recorded for embedded LLM candidate").

Coverage:

- PromptSpec registry returns the canonical architecture-analyst
  spec with a stable sha-256 digest.
- Skill revision parsing reads version + body from SKILL.md
  frontmatter; unversioned skills are skipped.
- Proposals handlers record metadata when --prompt-spec and
  --skill are provided.
- MCP arch_prompt_registry and arch_skill_registry return the
  canonical content-addressed references.
- MCP arch_propose_create with prompt_spec + skill records the
  full provenance chain into the candidate fork; arch_propose_review
  surfaces the metadata in its envelope.
- A new admin tool that is admin-gated (regression for slice 15):
  arch_prompt_registry and arch_skill_registry refuse calls when
  admin is disabled.
- Editing the SKILL.md body changes the content hash and the
  recorded provenance is no longer replayable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from archskillkit.agent_governance import (
    METADATA_SCHEMA,
    ProposalMetadata,
    SkillRevision,
    find_skill_revision,
    get_prompt_spec,
    load_skill_revisions,
    prompt_specs_registry,
)
from archskillkit.application.queries.prompt import (
    ARCHITECTURE_ANALYST,
    PromptSpec,
)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


# ---------- pure unit tests (no subprocess) ----------


class TestPromptSpecRegistry:
    def test_architecture_analyst_is_registered(self):
        registry = prompt_specs_registry()
        assert "architecture-analyst" in registry
        spec = registry["architecture-analyst"]
        assert spec.name == ARCHITECTURE_ANALYST.name
        assert spec.version == ARCHITECTURE_ANALYST.version

    def test_get_prompt_spec_returns_same_instance(self):
        spec = get_prompt_spec("architecture-analyst")
        assert spec is ARCHITECTURE_ANALYST

    def test_get_prompt_spec_unknown_raises_keyerror(self):
        with pytest.raises(KeyError):
            get_prompt_spec("does-not-exist")

    def test_digest_is_stable_sha256_hex(self):
        spec = PromptSpec(
            name="test-spec",
            version="1.0.0",
            role="r",
            objective="o",
            output_schema={"type": "object"},
        )
        d = spec.digest()
        assert len(d) == 64
        assert all(c in "0123456789abcdef" for c in d)
        # Stable: same content → same digest
        assert spec.digest() == d
        # Tamper: change one byte
        spec2 = PromptSpec(
            name="test-spec",
            version="1.0.0",
            role="r",
            objective="o2",  # changed
            output_schema={"type": "object"},
        )
        assert spec2.digest() != d


class TestSkillRevisionParsing:
    def _write_skill(
        self, root: Path, name: str, body: str, *, version: str | None = "1.0.0"
    ) -> Path:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        if version:
            skill_md.write_text(
                f"---\nname: {name}\nversion: {version}\ndescription: test\n---\n\n{body}\n"
            )
        else:
            skill_md.write_text(f"---\nname: {name}\ndescription: test\n---\n\n{body}\n")
        return skill_md

    def test_load_skill_revisions_reads_version_and_body(self, tmp_path):
        skills_root = tmp_path / "skills"
        self._write_skill(skills_root, "alpha", "alpha body", version="1.0.0")
        self._write_skill(skills_root, "beta", "beta body", version="2.3.4")
        revs = load_skill_revisions(skills_root)
        names = sorted(r.name for r in revs)
        assert names == ["alpha", "beta"]
        beta = next(r for r in revs if r.name == "beta")
        assert beta.version == "2.3.4"
        assert len(beta.content_hash) == 64

    def test_load_skill_revisions_skips_unversioned(self, tmp_path):
        skills_root = tmp_path / "skills"
        self._write_skill(skills_root, "alpha", "alpha body", version="1.0.0")
        self._write_skill(skills_root, "ghost", "ghost body", version=None)
        revs = load_skill_revisions(skills_root)
        assert [r.name for r in revs] == ["alpha"]

    def test_editing_skill_body_changes_hash(self, tmp_path):
        skills_root = tmp_path / "skills"
        md = self._write_skill(skills_root, "alpha", "alpha body", version="1.0.0")
        rev1 = find_skill_revision("alpha", skills_root)
        md.write_text(md.read_text().replace("alpha body", "alpha body!"))
        rev2 = find_skill_revision("alpha", skills_root)
        assert rev1.content_hash != rev2.content_hash

    def test_find_skill_revision_returns_none_for_missing(self, tmp_path):
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        assert find_skill_revision("nope", skills_root) is None

    def test_find_skill_revision_returns_none_for_unversioned(self, tmp_path):
        skills_root = tmp_path / "skills"
        self._write_skill(skills_root, "ghost", "ghost body", version=None)
        assert find_skill_revision("ghost", skills_root) is None


class TestProposalMetadata:
    def test_metadata_round_trip(self):
        m = ProposalMetadata(
            prompt_spec_name="architecture-analyst",
            prompt_spec_version="1.0.0",
            prompt_spec_hash=ARCHITECTURE_ANALYST.digest(),
            skill_revisions=[
                SkillRevision(name="arch-investigation", version="1.0.0", content_hash="a" * 64),
            ],
        )
        d = m.to_object()
        assert d["schema"] == METADATA_SCHEMA
        m2 = ProposalMetadata(**d)
        assert m2.prompt_spec_hash == m.prompt_spec_hash
        assert m2.skill_revisions[0].name == "arch-investigation"


# ---------- E2E tests (MCP server subprocess) ----------


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    # Point the skill registry at the test skills dir, which the
    # fixture populates with a versioned arch-investigation +
    # arch-reviewer pair.
    monkeypatch.setenv("ARCH_SKILLKIT_SKILLS_ROOT", str(tmp_path / "skills"))


@pytest.fixture()
def repo(sandbox, tmp_path):
    # First populate the test skills tree.
    skills_root = tmp_path / "skills"
    for name in ("arch-investigation", "arch-reviewer"):
        skill_dir = skills_root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\nversion: 1.0.0\n"
            f"description: test {name}\n---\n\n"
            f"# {name}\n\nbody for {name}\n"
        )

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
    astgrep = tmp_path / "outline.json"
    astgrep.write_text(
        json.dumps(
            {
                "ruleId": "outline.rust.function",
                "text": "main",
                "file": "src/main.rs",
                "language": "Rust",
                "range": {"start": {"line": 0, "column": 0}},
                "lines": "fn main() {}",
                "metaVariables": {"single": {}, "multi": {}},
            }
        )
    )
    semgrep = tmp_path / "patterns.json"
    semgrep.write_text(json.dumps({"results": []}))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "ingest-code",
            "--repo",
            str(repo),
            "--astgrep",
            str(astgrep),
            "--semgrep",
            str(semgrep),
            "--run-id",
            "world",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "discover",
            "--repo",
            str(repo),
            "--run-id",
            "world",
        ],
        check=True,
        capture_output=True,
    )
    return repo


def _session(repo_path, *, admin=False):
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = os.environ.copy()

    async def _runner(coro_factory):
        params = StdioServerParameters(
            command=sys.executable,
            args=(
                ["-m", "archskillkit", "mcp", "--repo", repo_path] + (["--admin"] if admin else [])
            ),
            env=env,
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            return await coro_factory(session)

    return asyncio, _runner


def _call(session, tool_name, **arguments):
    return session.call_tool(name=tool_name, arguments=arguments or None)


class TestRegistriesViaMCP:
    def test_prompt_registry_lists_architecture_analyst(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            r = await _call(session, "arch_prompt_registry")
            return r.isError, r.content[0].text

        is_error, text = asyncio.run(runner(call))
        assert is_error is False
        env = json.loads(text)
        assert env["schema"] == "arch-skillkit/prompt-registry-v1"
        names = [s["name"] for s in env["specs"]]
        assert "architecture-analyst" in names
        for spec in env["specs"]:
            assert spec["version"]
            assert len(spec["digest"]) == 64

    def test_skill_registry_lists_versioned_skills(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            r = await _call(session, "arch_skill_registry")
            return r.isError, r.content[0].text

        is_error, text = asyncio.run(runner(call))
        assert is_error is False
        env = json.loads(text)
        assert env["schema"] == "arch-skillkit/skill-registry-v1"
        names = sorted(s["name"] for s in env["skills"])
        assert "arch-investigation" in names
        assert "arch-reviewer" in names
        for s in env["skills"]:
            assert s["version"] == "1.0.0"
            assert len(s["content_hash"]) == 64

    def test_new_tools_are_admin_gated(self, repo):
        """arch_prompt_registry + arch_skill_registry MUST refuse
        when admin is disabled (defence-in-depth regression)."""
        asyncio, runner = _session(str(repo), admin=False)

        async def call(session):
            r1 = await _call(session, "arch_prompt_registry")
            r2 = await _call(session, "arch_skill_registry")
            return r1.isError, r1.content[0].text, r2.isError, r2.content[0].text

        r1_err, r1_text, r2_err, r2_text = asyncio.run(runner(call))
        assert r1_err is True
        assert r2_err is True
        assert "ADMIN_DISABLED" in r1_text
        assert "ADMIN_DISABLED" in r2_text


class TestProvenanceRecorded:
    def test_create_with_provenance_records_metadata(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            r = await _call(
                session,
                "arch_propose_create",
                name="prov",
                prompt_spec="architecture-analyst",
                skill=["arch-investigation", "arch-reviewer"],
            )
            return r.isError, r.content[0].text

        is_error, text = asyncio.run(runner(call))
        assert is_error is False, text
        env = json.loads(text)
        assert env["schema"] == "arch-skillkit/proposal-create-v1"
        assert "metadata" in env
        m = env["metadata"]
        assert m["schema"] == METADATA_SCHEMA
        assert m["prompt_spec_name"] == "architecture-analyst"
        assert m["prompt_spec_version"] == "1.0.0"
        assert len(m["prompt_spec_hash"]) == 64
        skills = sorted(s["name"] for s in m["skill_revisions"])
        assert skills == ["arch-investigation", "arch-reviewer"]

    def test_review_surfaces_metadata(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            await _call(
                session,
                "arch_propose_create",
                name="prov2",
                prompt_spec="architecture-analyst",
                skill=["arch-investigation"],
            )
            r = await _call(session, "arch_propose_review", name="prov2")
            return r.isError, r.content[0].text

        is_error, text = asyncio.run(runner(call))
        assert is_error is False, text
        env = json.loads(text)
        assert env["schema"] == "arch-skillkit/proposal-review-v1"
        assert "metadata" in env
        assert env["metadata"]["prompt_spec_name"] == "architecture-analyst"

    def test_list_shows_provenance_summary(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            await _call(
                session, "arch_propose_create", name="prov3", prompt_spec="architecture-analyst"
            )
            r = await _call(session, "arch_propose_list")
            return json.loads(r.content[0].text)

        env = asyncio.run(runner(call))
        row = next(c for c in env["candidates"] if c["run_id"] == "proposal-prov3")
        assert "metadata" in row
        assert row["metadata"]["prompt_spec_name"] == "architecture-analyst"
        assert row["metadata"]["skill_count"] == 0

    def test_create_without_provenance_omits_metadata(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            r = await _call(session, "arch_propose_create", name="bare")
            return json.loads(r.content[0].text)

        env = asyncio.run(runner(call))
        assert "metadata" not in env

    def test_unknown_prompt_spec_returns_metadata_error(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            r = await _call(session, "arch_propose_create", name="bad", prompt_spec="no-such-spec")
            return r.isError, r.content[0].text

        is_error, text = asyncio.run(runner(call))
        assert is_error is True
        env = json.loads(text)
        assert env["error"] == "METADATA_INVALID"

    def test_unversioned_skill_returns_metadata_error(self, repo, tmp_path):
        """A skill without `version:` in frontmatter MUST NOT be
        accepted as provenance — the caller has to upgrade the
        skill or drop the declaration."""
        # Add an unversioned skill to the same skills_root.
        skills_root = Path(os.environ["ARCH_SKILLKIT_SKILLS_ROOT"])
        unversioned = skills_root / "arch-ghost"
        unversioned.mkdir(parents=True, exist_ok=True)
        (unversioned / "SKILL.md").write_text(
            "---\nname: arch-ghost\ndescription: ghost\n---\n\nbody\n"
        )
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            r = await _call(
                session,
                "arch_propose_create",
                name="bad2",
                prompt_spec="architecture-analyst",
                skill=["arch-ghost"],
            )
            return r.isError, r.content[0].text

        is_error, text = asyncio.run(runner(call))
        assert is_error is True
        env = json.loads(text)
        assert env["error"] == "METADATA_INVALID"
        assert env["skill"] == "arch-ghost"
