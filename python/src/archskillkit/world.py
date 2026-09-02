"""Architecture World — the project-scoped event-sourced knowledge graph.

Encapsulates ActiveGraph behind the domain (ADR-0024): callers see only
observations, claims, evidence and replay; the runtime, store URLs and
graph types stay inside this module. The event log inside
activegraph.sqlite is the source of truth (ADR-0015); snapshot() is a
pure projection of it and replay_verify() proves that projection is
reconstructible (H2-1, UAT2-004).
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from activegraph import Graph, Runtime
from activegraph.store import open_store

from archskillkit.errors import PromotionError  # noqa: F401 (re-export)
from archskillkit.ids import (
    ProjectContext,
    projects_root,
)
from archskillkit.packs.arch_core import (
    ClaimData,
    EvidenceData,
    ObservationData,
    ProjectData,
    pack,
)
from archskillkit.packs.arch_model import pack as arch_model_pack
from archskillkit.repositories import (
    ArchitecturePolicyService,
    ArchitectureRepository,
    ClaimRepository,
    KnowledgeGapService,
    ProposalService,
)

WORKSPACE_SUBDIRS = ("evidence", "knowledge", "likec4", "arrows", "reports", "exports")


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ReplayReport:
    ok: bool
    detail: str
    objects: int
    relations: int
    events: int


class ArchitectureWorld:
    """A project-scoped event-sourced knowledge graph run.

    The main world lives in run "world"; forks (architectural proposals,
    docs/v2/08) live in sibling runs of the same activegraph.sqlite —
    the event log branching keeps main untouched (UAT2-012).
    """

    DEFAULT_RUN_ID = "world"

    def __init__(self, project_id: str, name: str = "", root: str = "",
                 remote: str = "", run_id: str = ""):
        self.project_id = project_id
        self.project_name = name or project_id.rsplit("-", 1)[0]
        self.root = root
        self.remote = remote
        self.run_id = run_id or self.DEFAULT_RUN_ID
        self.workspace = projects_root() / project_id
        self.db_path = self.workspace / "activegraph.sqlite"
        self._runtime: Runtime | None = None
        self._graph: Graph | None = None
        self.claims = ClaimRepository(self)
        self.architecture = ArchitectureRepository(self)
        self.policies = ArchitecturePolicyService(self)
        self.gaps = KnowledgeGapService(self)
        self.proposals_service = ProposalService(self)

    # ---- construction -------------------------------------------------

    @classmethod
    def for_repo(cls, repo_path: str | Path) -> ArchitectureWorld:
        ctx = ProjectContext.for_repo(repo_path)
        return cls(project_id=ctx.project_id, name=ctx.name,
                   root=str(ctx.root), remote=ctx.remote)

    # ---- lifecycle ----------------------------------------------------

    def open(self) -> ArchitectureWorld:
        for sub in WORKSPACE_SUBDIRS:
            (self.workspace / sub).mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{self.db_path}"
        if self.db_path.exists() and _run_exists(self.db_path, self.run_id):
            # Resume: Runtime.load replays the log and continues the
            # store's id sequence; a fresh Runtime would restart ids and
            # collide with recorded events.
            runtime = Runtime.load(url, run_id=self.run_id)
        else:
            runtime = Runtime(Graph(run_id=self.run_id), persist_to=url)
        # Schema validation must hold in every session — load every pack.
        runtime.load_pack(pack)
        runtime.load_pack(arch_model_pack)
        self._runtime, self._graph = runtime, runtime.graph
        return self

    def close(self) -> None:
        self._runtime, self._graph = None, None

    def __enter__(self) -> Self:
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def graph(self) -> Graph:
        if self._graph is None:
            raise RuntimeError("world is not open; call open() first")
        return self._graph

    # ---- writes -------------------------------------------------------

    def ensure_project(self) -> str:
        """Idempotently anchor this repository into the world."""
        for existing in self.graph.objects(type="project"):
            if existing.data.get("project_id") == self.project_id:
                return existing.id
        project = ProjectData(
            project_id=self.project_id,
            name=self.project_name,
            root=self.root,
            remote=self.remote,
            created_at=_utcnow(),
        )
        obj = self.graph.add_object("project", project.model_dump())
        self._write_project_json(project)
        return obj.id

    def record_observation(self, observation: ObservationData) -> str:
        return self.graph.add_object("observation", observation.model_dump()).id

    def record_evidence(self, evidence: EvidenceData) -> str:
        return self.graph.add_object("evidence", evidence.model_dump()).id

    def propose_claim(self, claim: ClaimData) -> str:
        return self.claims.add(claim)
    def link_evidenced_by(self, claim_id: str, evidence_id: str) -> str:
        return self.claims.link_evidenced_by(claim_id, evidence_id)
    # ---- domain queries (used by the promotion services) ---------------

    def find_objects(self, obj_type: str, **data_match) -> list[dict]:
        """Objects of a type whose data contains every given key=value."""
        out = []
        for obj in self.graph.objects(type=obj_type):
            if all(obj.data.get(k) == v for k, v in data_match.items()):
                out.append({"id": obj.id, "type": obj.type, "data": obj.data})
        return out

    def get_object(self, object_id: str) -> dict:
        obj = self.graph.get_object(object_id)
        if obj is None:
            raise KeyError(object_id)
        return {"id": obj.id, "type": obj.type, "data": obj.data}

    def accept_claim(self, claim_id: str, actor: str = "user") -> None:
        self.claims.accept(claim_id, actor=actor)
    def add_architecture_element(self, name: str, kind: str,
                                 origin: str = "DETECTED",
                                 confidence: str = "high") -> str:
        return self.architecture.add_element(name, kind, origin, confidence)
    def add_architecture_relation(self, kind: str, source_id: str,
                                  target_id: str,
                                  data: dict | None = None) -> str:
        return self.architecture.add_relation(kind, source_id, target_id, data)
    def architecture_relations(self) -> list[dict]:
        return self.architecture.relations()
    # ---- reactive architecture (Phase F: drift + stale model) ----------

    def record_architecture_rule(self, name: str, statement: str,
                                 forbidden_relation: str,
                                 source_category: str, target_category: str,
                                 severity: str = "high") -> str:
        return self.policies.record_rule(name, statement, forbidden_relation,
                                         source_category, target_category,
                                         severity)
    # ---- domain port (docs/v2/45 §4, V2.3-F4) --------------------------
    # ActiveGraph stays behind these domain methods: promotion/proposals
    # must never touch `.graph` directly (ADR-0024).

    def observation_is_claimed(self, observation_id: str) -> bool:
        return self.claims.observation_is_claimed(observation_id)
    def propose_derived_claim(self, claim: ClaimData,
                              observation_id: str) -> str:
        return self.claims.propose_derived_claim(claim, observation_id)
    def claim_observation_ids(self, claim_id: str) -> list[str]:
        return self.claims.observation_ids_of_claim(claim_id)
    def link_contradicts(self, observation_id: str, claim_id: str,
                         reason: str) -> None:
        self.claims.link_contradicts(observation_id, claim_id, reason)
    def claim_is_contradicted(self, claim_id: str) -> bool:
        return self.claims.is_contradicted(claim_id)
    def set_claim_status(self, claim_id: str, status: str) -> None:
        self.claims.set_status(claim_id, status)
    def set_object_fields(self, object_id: str, fields: dict) -> None:
        self.graph.patch_object(object_id, fields)

    def remove_relation_by_id(self, relation_id: str) -> None:
        self.architecture.remove_relation(relation_id)
    def remove_object_by_id(self, object_id: str) -> None:
        self.architecture.remove_element(object_id)
    def persist_findings(self, findings: list[dict]) -> int:
        return self.policies.persist_findings(findings)
    def detect_drift(self) -> dict:
        return self.policies.detect_drift()
    def detect_stale_model(self, index) -> dict:
        return self.policies.detect_stale_model(index)
    # ---- fork/diff of the architecture (Phase G, docs/v2/08) -----------

    def fork(self, name: str) -> ArchitectureWorld:
        """Branch this world's event log into an independent proposal run
        `proposal-<name>`. Idempotent by name: an existing fork run is
        reopened, never re-branched."""
        from activegraph.store import open_store
        from activegraph.store.sqlite import SQLiteEventStore

        fork_run_id = f"proposal-{name}"
        if self.db_path.exists() and _run_exists(self.db_path, fork_run_id):
            return self.view(fork_run_id)
        url = f"sqlite:///{self.db_path}"
        events = list(open_store(url, run_id=self.run_id).iter_events())
        if events:
            SQLiteEventStore.fork_run(
                str(self.db_path), parent_run_id=self.run_id,
                new_run_id=fork_run_id, at_event_id=events[-1].id,
                label=name, created_at=_utcnow())
        return self.view(fork_run_id)

    def has_run(self, run_id: str) -> bool:
        return self.db_path.exists() and _run_exists(self.db_path, run_id)

    def view(self, run_id: str) -> ArchitectureWorld:
        return ArchitectureWorld(
            project_id=self.project_id, name=self.project_name,
            root=self.root, remote=self.remote, run_id=run_id).open()

    def record_proposal(self, name: str, rationale: str = "") -> str:
        return self.proposals_service.record(name, rationale)
    def _proposal(self, name: str) -> dict:
        return self.proposals_service.get(name)
    def approve_proposal(self, name: str, actor: str) -> None:
        self.proposals_service.approve(name, actor=actor)
    def reject_proposal(self, name: str, actor: str) -> None:
        self.proposals_service.reject(name, actor=actor)
    # ---- reads --------------------------------------------------------

    def snapshot(self) -> dict:
        """Canonical projection: stable under replay (H2-1)."""
        objects: dict[str, dict] = {}
        counts: dict[str, int] = {}
        for obj in sorted(self.graph.all_objects(), key=lambda o: o.id):
            objects[obj.id] = {"type": obj.type, "data": obj.data}
            counts[obj.type] = counts.get(obj.type, 0) + 1
        relations = [
            {"id": r.id, "type": r.type, "source": r.source,
             "target": r.target, "data": r.data}
            for r in sorted(self.graph.relations(), key=lambda r: r.id)
        ]
        return {"counts": counts, "objects": objects, "relations": relations}

    def last_event_id(self) -> str:
        """Position of the event log (V2.4 ArchitectureSnapshot,
        ADR-0033). Deterministic for the same log."""
        events = self.graph.events
        return events[-1].id if events else "evt_000"

    def architecture_rules(self) -> list[dict]:
        """Declared boundary rules (ADR-0022) — governance read."""
        return self.find_objects("architecture_rule")

    def findings(self) -> list[dict]:
        """Persisted review/drift findings — governance read."""
        return self.find_objects("finding")

    def proposals(self) -> list[dict]:
        """Recorded proposals — governance read."""
        return self.find_objects("proposal")

    # ---- knowledge gaps (V2.4 M2) --------------------------------------

    def record_knowledge_gap(self, question: str, impact: str = "medium",
                             related_refs: list[str] | None = None,
                             evidence_needed: list[str] | None = None) -> str:
        return self.gaps.record(question, impact=impact,
                                related_refs=related_refs,
                                evidence_needed=evidence_needed)

    def knowledge_gaps(self, status: str | None = None) -> list[dict]:
        return self.gaps.list(status=status)

    def set_knowledge_gap_status(self, gap_id: str, status: str) -> None:
        self.gaps.set_status(gap_id, status)

    def replay_verify(self) -> ReplayReport:
        """Prove the log reproduces current state with a fresh projection."""
        live = json.dumps(self.snapshot(), sort_keys=True)
        url = f"sqlite:///{self.db_path}"
        reloaded = Runtime.load(url, run_id=self.run_id)
        replayed_graph = reloaded.graph
        replayed = json.dumps(
            {"counts": _counts_of(replayed_graph),
             "objects": {o.id: {"type": o.type, "data": o.data}
                         for o in sorted(replayed_graph.all_objects(), key=lambda o: o.id)},
             "relations": [{"id": r.id, "type": r.type, "source": r.source,
                            "target": r.target, "data": r.data}
                           for r in sorted(replayed_graph.relations(), key=lambda r: r.id)]},
            sort_keys=True,
        )
        events = len(list(open_store(url, run_id=self.run_id).iter_events()))
        ok = live == replayed
        n_objects = len(json.loads(replayed)["objects"])
        n_relations = len(json.loads(replayed)["relations"])
        detail = "replay reproduces current state" if ok else (
            "replay diverged from current state")
        return ReplayReport(ok=ok, detail=detail, objects=n_objects,
                            relations=n_relations, events=events)

    # ---- helpers ------------------------------------------------------

    def _write_project_json(self, project: ProjectData) -> None:
        path = self.workspace / "project.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "project_id": project.project_id,
            "name": project.name,
            "root": project.root,
            "remote": project.remote,
            "created_at": project.created_at,
        }, indent=2) + "\n")


def _counts_of(graph: Graph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obj in graph.all_objects():
        counts[obj.type] = counts.get(obj.type, 0) + 1
    return counts


def _run_exists(db_path: Path, run_id: str) -> bool:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM events WHERE run_id = ? LIMIT 1", (run_id,)).fetchone()
    return row is not None
