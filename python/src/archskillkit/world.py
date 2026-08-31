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

from activegraph import Graph, Runtime
from activegraph.store import open_store

from archskillkit.ids import RepoNotFound, compute_project_id, projects_root, repo_remote, repo_root
from archskillkit.packs.arch_core import (
    ClaimData,
    EvidenceData,
    ObservationData,
    ProjectData,
    pack,
)
from archskillkit.packs.arch_model import pack as arch_model_pack

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


class PromotionError(Exception):
    """A promotion precondition failed (claim lifecycle, M2-C2)."""


class ArchitectureWorld:
    """One durable run per project; the db lives in the project workspace."""

    RUN_ID = "world"

    def __init__(self, project_id: str, name: str = "", root: str = "", remote: str = ""):
        self.project_id = project_id
        self.project_name = name or project_id.rsplit("-", 1)[0]
        self.root = root
        self.remote = remote
        self.workspace = projects_root() / project_id
        self.db_path = self.workspace / "activegraph.sqlite"
        self._runtime: Runtime | None = None
        self._graph: Graph | None = None

    # ---- construction -------------------------------------------------

    @classmethod
    def for_repo(cls, repo_path: str | Path) -> "ArchitectureWorld":
        root = repo_root(repo_path)
        if root is None:
            raise RepoNotFound(f"not a git repository: {repo_path}")
        remote = repo_remote(root)
        project_id = compute_project_id(str(root), remote)
        return cls(project_id=project_id, name=root.name, root=str(root), remote=remote)

    # ---- lifecycle ----------------------------------------------------

    def open(self) -> "ArchitectureWorld":
        for sub in WORKSPACE_SUBDIRS:
            (self.workspace / sub).mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{self.db_path}"
        if self.db_path.exists():
            # Resume: Runtime.load replays the log and continues the
            # store's id sequence; a fresh Runtime would restart ids and
            # collide with recorded events.
            runtime = Runtime.load(url, run_id=self.RUN_ID)
        else:
            runtime = Runtime(Graph(run_id=self.RUN_ID), persist_to=url)
        # Schema validation must hold in every session — load every pack.
        runtime.load_pack(pack)
        runtime.load_pack(arch_model_pack)
        self._runtime, self._graph = runtime, runtime.graph
        return self

    def close(self) -> None:
        self._runtime, self._graph = None, None

    def __enter__(self) -> "ArchitectureWorld":
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
        return self.graph.add_object("claim", claim.model_dump()).id

    def link_evidenced_by(self, claim_id: str, evidence_id: str) -> str:
        return self.graph.add_relation(claim_id, evidence_id, "evidenced_by", {}).id

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
        """Explicit acceptance (M2-C2): refused for claims without evidence
        or with unresolved contradictions — never silent."""
        claim = self.get_object(claim_id)
        if claim["type"] != "claim":
            raise PromotionError(f"{claim_id} is not a claim")
        status = claim["data"].get("status")
        if status == "accepted":
            return
        if status == "contradicted":
            raise PromotionError(
                f"claim {claim_id} is contradicted; resolve the conflict first")
        if not claim["data"].get("evidence_refs"):
            raise PromotionError(
                f"claim {claim_id} has no evidence references")
        self.graph.patch_object(claim_id, {"status": "accepted"}, actor=actor)

    def add_architecture_element(self, name: str, kind: str,
                                 origin: str = "DETECTED",
                                 confidence: str = "high") -> str:
        """Idempotent by (name, kind) — returns the element id."""
        existing = self.find_objects("architecture_element", name=name)
        if existing:
            return existing[0]["id"]
        return self.graph.add_object("architecture_element", {
            "name": name, "kind": kind, "origin": origin,
            "confidence": confidence, "summary": "",
        }).id

    def add_architecture_relation(self, kind: str, source_id: str,
                                  target_id: str,
                                  data: dict | None = None) -> str:
        """Idempotent by (kind, source, target) — returns the edge id."""
        for rel in self.graph.relations(source=source_id, target=target_id):
            if rel.type == kind:
                return rel.id
        return self.graph.add_relation(
            source_id, target_id, kind, data or {}).id

    def architecture_relations(self) -> list[dict]:
        """Typed edges whose two endpoints are architecture elements —
        the domain-level view of ArchitectureRelation (docs/v2/04)."""
        elements = {o["id"] for o in self.find_objects("architecture_element")}
        out = []
        for rel in self.graph.relations():
            if rel.source in elements and rel.target in elements:
                out.append({"id": rel.id, "kind": rel.type,
                            "source": rel.source, "target": rel.target,
                            "data": rel.data})
        return out

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

    def replay_verify(self) -> ReplayReport:
        """Prove the log reproduces current state with a fresh projection."""
        live = json.dumps(self.snapshot(), sort_keys=True)
        url = f"sqlite:///{self.db_path}"
        reloaded = Runtime.load(url, run_id=self.RUN_ID)
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
        events = len(list(open_store(url, run_id=self.RUN_ID).iter_events()))
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
