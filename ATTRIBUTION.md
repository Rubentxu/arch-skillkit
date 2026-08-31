# Attribution

ArchSkillKit incorporates community agent skills, adapted to this
project's conventions (pinned toolchain, repository-clean invariant,
evidence formats). Their essence is preserved; integration sections and
project-specific gotchas were added on top.

| Skill | Source | License |
|---|---|---|
| `skills/ast-grep/` | [ast-grep/agent-skill](https://github.com/ast-grep/agent-skill) — the official ast-grep agent skill (`ast-grep/skills/ast-grep` + the `outline` skill). | No explicit license file in the source repository at integration time; reproduced from the official ast-grep plugin with attribution. |
| `skills/semgrep/` | [semgrep/skills](https://github.com/semgrep/skills) — the official Semgrep agent skills (`skills/semgrep`). | [Semgrep Rules License v1.0](https://semgrep.dev/legal/rules-license) — reference kept in this file; the skill prose is documentation for the open Semgrep CLI. |
| `skills/mermaid/` | [WH-2099/mermaid-skill](https://github.com/WH-2099/mermaid-skill) — 23+ diagram types with the official Mermaid documentation as references. | [MIT](skills/mermaid/LICENSE) — license file vendored with the skill. |

## Local changes vs. the originals

- Every `SKILL.md` gained an **ArchSkillKit Integration** section
  (pinned mise toolchain, project rule-pack locations, repository-clean
  invariant, evidence payload formats, projection routing).
- `skills/mermaid/SKILL.md` was converted from slash-command format to a
  plain agent skill (frontmatter description rewritten, `$ARGUMENTS`
  removed); the diagram references are verbatim.
- `skills/ast-grep/references/outline.md` is the official `outline`
  skill with its frontmatter converted to a heading.
- `skills/semgrep/SKILL.md` documents the OSS `extra.lines` gate and the
  `--no-rewrite-rule-ids` requirement that ArchSkillKit's own pipeline
  depends on.

Upstream improvements should be re-synced from the sources above.
