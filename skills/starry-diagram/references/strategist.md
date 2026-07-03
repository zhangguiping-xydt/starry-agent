# Diagram Strategist

Mission: transform source material into a diagram pack plan that is explicit, source-grounded, and safe to execute.

Outputs:
- `diagram_manifest.yaml` at the pack root.
- For every generated diagram, a `diagram_spec.md` and `diagram_lock.yaml` in that diagram directory.

## Candidate diagram types

| Type | Generate when source contains |
| --- | --- |
| architecture | modules, services, stores, runtime boundaries, external systems |
| business-architecture | business domains, capability layers, roles, value streams |
| flow | ordered steps, decisions, approvals, status transitions |
| swimlane | multiple actors, teams, systems, or roles sharing process responsibility |
| sequence | ordered calls, messages, async events, or agent orchestration |
| er | entities, fields, keys, and cardinality facts |
| state | lifecycle states and transitions |
| data-flow | collection, transformation, storage, sync, and consumption |
| deployment | environments, containers, servers, network boundaries, infrastructure |
| component | modules, services, packages, dependencies |
| event-flow | producers, topics, subscribers, projections, async events |
| concept | mechanisms, loops, layers, flywheels, abstract relationships |

## Fact gate

Do not infer services, roles, fields, relationships, states, calls, events, or cardinalities not present in source material. Missing required facts produce skipped or needs_clarification, not invented content.

## Manifest fields

Use `project`, `mode`, `source_summary`, `naming_glossary`, and `diagrams`. `naming_glossary` records pack-level canonical ids and labels so the same entity uses the same identity across diagrams. Each diagram entry records `id`, `title`, `type`, `status`, `reason`, `source_refs`, and `style_id`; generated diagrams also record output directory. Entries with `needs_clarification` or fact-insufficient `skipped` status include a non-empty `missing` list naming the absent facts.

## Lock fields

Use `id`, `title`, `type`, `source_format`, `visual_style`, `canvas`, `nodes`, `edges`, `groups`, `style_tokens`, and type-specific fields such as participants, entities, states, messages, or cardinalities when applicable. Edge records include `kind: command | event | data | projection | call` whenever command flow, event flow, data flow, projections, or service calls could otherwise be confused.
