# ArchSkillKit

> ArchSkillKit is a working name. The final public name may change without affecting the architecture.

[![ci](https://github.com/Rubentxu/arch-skillkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Rubentxu/arch-skillkit/actions/workflows/ci.yml)

**English** | [Español](README.es.md)

ArchSkillKit is an **agent-first, tool-first and repository-clean** toolkit for discovering, reviewing and visualizing software architecture with deterministic tooling and LLM agents. It produces LikeC4 models and Arrows graph views **without writing a single file into the repository being analyzed**.

## The problem

LLM agents usually make sense of a repository through repeated `read → grep → search → infer` cycles. This burns context, increases cost, repeats work that deterministic tools already solve, and produces architectural inferences that are hard to audit.

ArchSkillKit turns the process into:

```text
Repository
    ↓
Deterministic tools (ast-grep, Semgrep, build metadata)
    ↓
Evidence bundle
    ↓
Architecture agents
    ↓
LikeC4 model + Arrows views + reports
```

## Core thesis

1. The source repository is **read-only input**.
2. Every generated asset lives in an **external workspace** following the XDG Base Directory Specification.
3. Mature existing tools do the deterministic work: ast-grep, Semgrep, build metadata, LikeC4, Arrows.
4. LLMs should not scan repositories blindly: they reason over prior evidence.
5. Skills, prompts, rules and conventions are the core of the value.
6. V1 avoids backend, database, own MCP server, own parser and multi-agent frameworks.
7. Any own code must be a very thin glue layer, justified with evidence.

## Golden rule

> No future improvement may force ArchSkillKit assets to be mixed with the repository being analyzed.

## Key properties

- **Repository-clean** — the `git status` of the analyzed repository is identical before and after the analysis.
- **Evidence first** — knowledge is classified as `DETECTED`, `INFERRED` or `DECLARED`, with `high | medium | low` confidence; high-confidence claims require evidence references.
- **Tool first** — ast-grep, Semgrep, LikeC4 and mise do the heavy lifting; own code is thin glue only.
- **Agent-portable** — distributed as an Agent Skill, usable from any compatible coding agent.
- **Dual visualization** — LikeC4 is the canonical architecture model; Arrows is the exploratory, detailed projection.
- **Emergent architecture** — advanced capabilities are only built when a measured, observable trigger justifies them.

## Expected result of V1

From any repository:

```text
cd /path/to/repository
<open a compatible agent>
"Analyze the architecture of this project"
```

The solution detects the project, creates or reuses an external workspace, runs deterministic scanners, produces an evidence bundle, infers the architecture with agents, generates/updates LikeC4, generates Arrows views, reviews contradictions and hallucinations, and leaves the source repository's `git status` untouched.

## Status

**Phase 2 in progress.** The V1 design specification is complete (product documentation, ADRs, the initial Agent Skill and schema examples). Phase 1 delivered the external XDG workspace, project registry, run manifest and doctor as thin-glue scripts. Phase 2 starts deterministic scanning: the ast-grep structural outline (Rust, Kotlin/Java, TypeScript) runs from a pinned mise toolchain and produces raw evidence — no LLM involved. Scripts are tested with BATS in [`tests/`](tests/). See the [roadmap](docs/17-roadmap.md) and the [backlog](docs/24-project-backlog.md).

## Documentation

Recommended reading order (the documentation is currently written in Spanish; English translations are planned and contributions are welcome):

1. [Vision](docs/00-vision.md)
2. [Reference architecture](docs/03-architecture.md)
3. [External workspace contract](docs/04-workspace-layout.md)
4. [Scanning pipeline](docs/07-scanning-pipeline.md)
5. [Evidence model](docs/08-evidence-model.md)
6. [Agent model](docs/09-agent-model.md)
7. [Emergent architecture](docs/16-emergent-architecture.md)
8. [Roadmap](docs/17-roadmap.md)
9. [UAT catalog](docs/19-uat.md)
10. [Architecture Decision Records](docs/adr/README.md)

The full document set is listed in the [manifest](MANIFEST.md).

## Contributing

See the [contributing guide](docs/22-contributing.md). In short: prefer, in order — a rule, a Skill/reference, a declarative adapter, a thin-glue script. Own code is the last resort. Significant architectural changes require an ADR.

## License

Distributed under the [MIT license](LICENSE). An informal Spanish translation is available in [LICENSE.es.md](LICENSE.es.md); the English version is the legally binding one.
