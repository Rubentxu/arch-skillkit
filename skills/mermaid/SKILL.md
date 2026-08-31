---
name: mermaid
description: >
  Generate high-quality Mermaid diagrams for reports and documentation.
  Supports flowcharts, sequence diagrams, class diagrams, ER diagrams,
  C4, architecture, mindmaps, Gantt charts and 20+ more diagram types,
  with official syntax references for each. Use when a diagram must be
  embedded in Markdown (GitHub renders it natively), when producing
  ArchSkillKit reports, or when the user asks for "a diagram" without a
  specific tool.
---
<!-- Adapted from WH-2099/mermaid-skill (MIT): https://github.com/WH-2099/mermaid-skill. See ATTRIBUTION.md and skills/mermaid/LICENSE. -->

# Mermaid Diagram Generator

Generate high-quality Mermaid diagram code based on user requirements.

## Workflow

1. **Understand Requirements**: Analyze user description to determine the most suitable diagram type
2. **Read Documentation**: Read the corresponding syntax reference for the diagram type
3. **Generate Code**: Generate Mermaid code following the specification
4. **Apply Styling**: Apply appropriate themes and style configurations

## Diagram Type Reference

Select the appropriate diagram type and read the corresponding documentation:

| Type | Documentation | Use Cases |
| ---- | ------------- | --------- |
| Flowchart | [flowchart.md](references/flowchart.md) | Processes, decisions, steps |
| Sequence Diagram | [sequenceDiagram.md](references/sequenceDiagram.md) | Interactions, messaging, API calls |
| Class Diagram | [classDiagram.md](references/classDiagram.md) | Class structure, inheritance, associations |
| State Diagram | [stateDiagram.md](references/stateDiagram.md) | State machines, state transitions |
| ER Diagram | [entityRelationshipDiagram.md](references/entityRelationshipDiagram.md) | Database design, entity relationships |
| Gantt Chart | [gantt.md](references/gantt.md) | Project planning, timelines |
| Pie Chart | [pie.md](references/pie.md) | Proportions, distributions |
| Mindmap | [mindmap.md](references/mindmap.md) | Hierarchical structures, knowledge graphs |
| Timeline | [timeline.md](references/timeline.md) | Historical events, milestones |
| Git Graph | [gitgraph.md](references/gitgraph.md) | Branches, merges, versions |
| Quadrant Chart | [quadrantChart.md](references/quadrantChart.md) | Four-quadrant analysis |
| Requirement Diagram | [requirementDiagram.md](references/requirementDiagram.md) | Requirements traceability |
| C4 Diagram | [c4.md](references/c4.md) | System architecture (C4 model) |
| Sankey Diagram | [sankey.md](references/sankey.md) | Flow, conversions |
| XY Chart | [xyChart.md](references/xyChart.md) | Line charts, bar charts |
| Block Diagram | [block.md](references/block.md) | System components, modules |
| Packet Diagram | [packet.md](references/packet.md) | Network protocols, data structures |
| Kanban | [kanban.md](references/kanban.md) | Task management, workflows |
| Architecture Diagram | [architecture.md](references/architecture.md) | System architecture |
| Radar Chart | [radar.md](references/radar.md) | Multi-dimensional comparison |
| Treemap | [treemap.md](references/treemap.md) | Hierarchical data visualization |
| User Journey | [userJourney.md](references/userJourney.md) | User experience flows |
| ZenUML | [zenuml.md](references/zenuml.md) | Sequence diagrams (code style) |

## Configuration & Themes

- [Theming](references/config-theming.md) - Custom colors and styles
- [Directives](references/config-directives.md) - Diagram-level configuration
- [Layouts](references/config-layouts.md) - Layout direction and spacing
- [Configuration](references/config-configuration.md) - Global settings
- [Math](references/config-math.md) - LaTeX math support

## Output Specification

Generated Mermaid code should:

1. Be wrapped in ```mermaid code blocks
2. Have correct syntax that renders directly
3. Have clear structure with proper line breaks and indentation
4. Use semantic node naming
5. Include styling when needed to improve visual appearance

## Example Output

```mermaid
flowchart TD
    A[Start] --> B{Condition}
    B -->|Yes| C[Execute]
    B -->|No| D[End]
    C --> D

```

---

## ArchSkillKit Integration

- **Reports**: `report.sh` embeds mermaid blocks in
  `reports/index.md` (GitHub renders them natively). When adding a
  diagram to a report, follow the Output Specification above and keep
  node ids sanitized (`[A-Za-z0-9_]+`) — raw ids break the renderer.
- **Choosing between mermaid and the projection formats**: mermaid is
  for embedded, human-scale diagrams in Markdown reports. For curated
  architecture use LikeC4, for exploration Arrows, and for the V2.2
  projection formats (JSON Canvas / GraphML / draw.io) follow
  `architecture-discovery/references/v2.2-projection-policy.md`.
  `architecture-discovery/references/v2.2-visual-intent-examples.md`
  routes a VisualIntent to the right format.
- **Large graphs**: past a few hundred nodes, prefer GraphML (analysis
  tools handle layout) over mermaid flowcharts — see
  `docs/v2/34-projection-routing-policy.md` thresholds.
