# Semantic Executor

Build semantic source and render a semantic SVG without changing the lock.

## Source routing

Use the selected entry in `templates/profiles/diagram_profiles.yaml` as the authoritative routing rule. The table below explains the renderer families; it does not override a profile.

| Diagram need | Preferred source |
| --- | --- |
| Simple flow, state, ER, sequence | Mermaid |
| Complex swimlane, sequence, deployment, entity | PlantUML |
| Architecture, component, data-flow, dense graphs | Graphviz |
| Conceptual poster-like mechanisms | Hand-authored SVG constrained by lock |

## Rules

1. Read `diagram_lock.yaml` before writing any source.
2. Include every required node, participant, entity, state, message, edge, and group from the lock.
3. Do not introduce unlisted semantics, labels, endpoints, fields, states, or relationships.
4. Keep names stable so the quality gate can compare source, lock, and rendered SVG.
5. If the renderer is missing or fails outside source correctness, write `render_unavailable` with the reason and still produce `check_report.json`.
6. Preserve stable ids from the lock. Use `id="<lock-id>"` in Graphviz/SVG and `diagram-id:<lock-id>` comment markers in Mermaid/PlantUML.
7. Run `validate_semantic_source.py` before invoking the renderer.
