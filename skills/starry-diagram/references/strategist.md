# Diagram Strategist

Mission: transform source material into a diagram pack plan that is explicit, source-grounded, and safe to execute.

Read `../templates/profiles/diagram_profiles.yaml` before choosing a renderer or enhancement level. The selected type profile is an executable contract, not a suggestion.

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

Use `id`, `title`, `type`, `source_format`, `visual_style`, `canvas`, `style_tokens`, and every semantic section required by the selected profile. Examples include nodes/edges/groups, participants/messages, entities/relationships, states/transitions, or lanes. Edge-like records include `kind: command | event | data | projection | call` whenever command flow, event flow, data flow, projections, or service calls could otherwise be confused.

Use `canvas.mode: fixed` when the target dimensions are a real delivery constraint. Make its viewBox exactly `0 0 <width> <height>`. Use `canvas.mode: auto` for topology-driven technical diagrams that should grow with their contents; optionally set max_width, max_height, and margin.

Copy the selected technical style into `style_tokens`, including colors and typography. Do not lock only a palette: the visual gate needs a font family and minimum font size to verify legibility.
