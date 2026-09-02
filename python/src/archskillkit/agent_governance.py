"""Agent governance (V2.4 M4, docs/v2/59 slice 16 acceptance:
"prompt hash/skill revision recorded for embedded LLM candidate").

Every candidate produced by an embedded LLM agent (via the
propose MCP tools) MUST carry an immutable record of:

- the PromptSpec that produced the compiled prompt
  (name + version + sha-256 of the spec content)
- the SkillRevision(s) the agent was operating under
  (skill name + declared version + sha-256 of SKILL.md)

The metadata is persisted into the fork's world store as a
`proposal_metadata` object, alongside the proposal object itself,
so any later `arch_propose_review` can surface the exact
prompt + skill chain that produced the candidate. This is the
provenance required by ADR-0041 to answer "what generated this?".

The hash is content-addressed: any change to the PromptSpec body
or the SKILL.md file changes the hash and invalidates the
provenance chain. Old candidates remain replayable against the
hashes they recorded.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.application.queries.prompt import (
    ARCHITECTURE_ANALYST,
    PromptSpec,
)

METADATA_SCHEMA = "arch-skillkit/proposal-metadata-v1"
METADATA_OBJECT_TYPE = "proposal_metadata"


class SkillRevision(BaseModel):
    """A pinned, content-addressed reference to a skill file.

    `version` is the declared semantic version from SKILL.md
    frontmatter. `content_hash` is the sha-256 of the full SKILL.md
    body (after the closing `---`), so any edit to the skill's
    instructions changes the hash and breaks the provenance chain."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    content_hash: str


class ProposalMetadata(BaseModel):
    """The provenance record attached to a candidate fork.

    `prompt_spec_hash` and `prompt_spec_version` identify the
    PromptSpec that compiled the prompt. `skill_revisions` lists
    the skills the agent declared it was using. Both are immutable
    once recorded (the world store treats them as facts)."""

    model_config = ConfigDict(extra="forbid")

    schema: str = METADATA_SCHEMA
    prompt_spec_name: str
    prompt_spec_version: str
    prompt_spec_hash: str
    skill_revisions: list[SkillRevision] = Field(default_factory=list)
    skill_count: int = 0  # derived; wire layer reads this directly

    def model_post_init(self, _context: object) -> None:
        # Keep skill_count in sync with the revision list. Both
        # callers (persistence and wire) get a consistent view.
        self.skill_count = len(self.skill_revisions)

    def to_object(self) -> dict:
        """Wire projection of this record."""
        return self.model_dump()


# ---------- prompt spec registry ----------


_PROMPT_SPECS: dict[str, PromptSpec] = {
    ARCHITECTURE_ANALYST.name: ARCHITECTURE_ANALYST,
}


def prompt_specs_registry() -> dict[str, PromptSpec]:
    """Return the prompt specs available for compilation.

    The registry is in-process and versioned via the spec's own
    declared version + digest. A spec is keyed by name; consumers
    MUST record both the version and the digest so a name-only
    match is never trusted across spec upgrades."""
    return dict(_PROMPT_SPECS)


def get_prompt_spec(name: str) -> PromptSpec:
    """Look up a prompt spec by name. Raises KeyError if missing."""
    if name not in _PROMPT_SPECS:
        raise KeyError(f"unknown prompt spec {name!r}; registered: {sorted(_PROMPT_SPECS.keys())}")
    return _PROMPT_SPECS[name]


# ---------- skill revision parsing ----------


_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<fm>.*?)\n---\s*\n(?P<body>.*)$",
    re.DOTALL,
)
_FIELD_RE = re.compile(r"^(?P<key>\w+):\s*(?P<value>.+?)\s*$")


def _parse_frontmatter(skill_md: Path) -> tuple[dict[str, str], str]:
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"missing YAML frontmatter in {skill_md}")
    fields: dict[str, str] = {}
    for line in match.group("fm").splitlines():
        m = _FIELD_RE.match(line)
        if m:
            fields[m.group("key")] = m.group("value")
    body = match.group("body")
    return fields, body


def _content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def load_skill_revisions(skills_root: Path) -> list[SkillRevision]:
    """Read every `<skills_root>/<name>/SKILL.md` and return a
    SkillRevision for each.

    Skills without a `version:` field in their frontmatter are
    SKIPPED with a warning-free fallback: they are not considered
    governed and MUST NOT appear in a ProposalMetadata. This is
    deliberate: only skills that opt into versioning get versioned
    provenance."""
    out: list[SkillRevision] = []
    if not skills_root.exists():
        return out
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            fields, body = _parse_frontmatter(skill_md)
        except ValueError:
            continue
        name = fields.get("name", skill_dir.name)
        version = fields.get("version")
        if not version:
            continue
        out.append(SkillRevision(name=name, version=version, content_hash=_content_hash(body)))
    return out


def find_skill_revision(name: str, skills_root: Path) -> SkillRevision | None:
    """Look up a single skill by name. Returns None if missing or
    not versioned."""
    skill_md = skills_root / name / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        fields, body = _parse_frontmatter(skill_md)
    except ValueError:
        return None
    version = fields.get("version")
    if not version:
        return None
    return SkillRevision(
        name=fields.get("name", name), version=version, content_hash=_content_hash(body)
    )


# ---------- persistence in the fork ----------


def record_proposal_metadata(world, run_id: str, metadata: ProposalMetadata) -> str:
    """Persist the metadata into the candidate fork.

    Returns the object id. The metadata object is stored with
    status=recorded so a future ledger query can filter it.

    Idempotent on (run_id, prompt_spec_hash): recording the same
    provenance chain twice returns the existing object id.
    """
    fork = world.view(run_id)
    try:
        existing = fork.find_objects(
            METADATA_OBJECT_TYPE, prompt_spec_hash=metadata.prompt_spec_hash
        )
        if existing:
            return existing[0]["id"]
        obj_id = fork.graph.add_object(METADATA_OBJECT_TYPE, metadata.model_dump()).id
        # Force the fork's sqlite sink to commit before we close
        # the view. Without this, a follow-up read on a freshly
        # opened world can miss the row because the parent's
        # `with world:` exit has not yet flushed the fork's
        # background sink workers.
        if fork._runtime is not None:
            fork._runtime.flush_sinks(timeout=1.0)
        return obj_id
    finally:
        fork.close()


def get_proposal_metadata(world, run_id: str) -> ProposalMetadata | None:
    """Read the metadata recorded against a candidate fork.

    Returns None when no metadata is recorded (legacy candidates,
    or candidates created via paths that don't record metadata).
    On multiple metadata objects (shouldn't happen; provenance is
    idempotent by spec hash), returns the first.
    """
    fork = world.view(run_id)
    try:
        for obj in fork.find_objects(METADATA_OBJECT_TYPE):
            return ProposalMetadata(**obj["data"])
    finally:
        fork.close()
    return None
