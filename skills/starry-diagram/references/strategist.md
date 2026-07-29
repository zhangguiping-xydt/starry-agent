# Diagram Strategist

Mission: transform source material into a diagram pack plan that is explicit, source-grounded, and safe to execute.

Read `../templates/profiles/diagram_profiles.yaml`, `../templates/layouts/technical_layouts.yaml`, and `../templates/notations/technical_notations.yaml` before choosing a viewpoint, renderer, layout, notation, or enhancement level. Evaluate `pick_when`, `skip_when`, and `alternatives` for every plausible type and allowed layout. The selected contracts are executable, not suggestions.

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

Use `contract_version: 4`, `project`, `mode`, `source_summary`, `naming_glossary`, `pack_identity`, and `diagrams`. `naming_glossary` records pack-level canonical ids and labels so the same entity uses the same identity across diagrams. `pack_identity` locks visual behavior separately from palette, typography, stroke language, and texture; read `visual-identity.md`. Each diagram entry records `id`, `title`, `type`, `status`, `reason`, and `source_refs`; generated diagrams also record a distinct `reading_question`, `viewpoint_family`, `notation_profile`, output directory, `layout_pattern`, and a type-native `diagram_treatment`. A non-preferred viewpoint or pattern also records `viewpoint_reason` or `layout_reason`. Entries with `needs_clarification` or fact-insufficient `skipped` status include a non-empty `missing` list naming the absent facts.

For four or more generated diagrams, evaluate pack diversity after the fact gate. Do not generate a false ER, deployment, ownership, state, or event view to satisfy a quota. If one viewpoint owns more than half the pack or one viewpoint/layout/notation signature appears more than twice, select a fact-complete alternative, split overview/detail companion views, or record a source-grounded `diversity_reason` explaining why repetition is unavoidable.

## Lock fields

Use `contract_version: 4`, `id`, `title`, `type`, `viewpoint_family`, `reading_question`, `notation_profile`, `source_format`, `visual_style`, `pack_identity`, `diagram_treatment`, `layout_plan`, `canvas`, `delivery_target`, `style_tokens`, and every semantic section required by the selected profile. Copy the manifest pack identity exactly into each generated lock. The treatment's `renderer_family` equals the locked type. Examples of semantic sections include nodes/edges/groups, participants/messages/fragments, entities/relationships, states/transitions, or lanes. Add `notation_role` to every semantic record covered by the selected notation profile. Edge-like records include `kind: command | event | data | projection | call | return | async` whenever command flow, event flow, data flow, projections, service calls, responses, or asynchronous messages could otherwise be confused. Sequence diagrams exceeding the readability soft limit declare message `fragments`; flow data/schema contracts use `notation_role: data-object` and stay off the primary process path.

The layout plan selects one allowed catalog pattern, direction, density, and view role; covers every non-container semantic item through `primary_items` or one region; and classifies every edge-like item exactly once as primary, secondary, or control. Follow `layout-planning.md`.

Apply the selected pattern's section and total-item limits before locking semantics. Split over-budget content into multiple manifest entries. Do not use a larger auto canvas or smaller typography as a substitute for splitting.

Use `canvas.mode: fixed` when the target dimensions are a real delivery constraint. Make its viewBox exactly `0 0 <width> <height>`. Use `canvas.mode: auto` for topology-driven technical diagrams that should grow with their contents; optionally set max_width, max_height, and margin.

Lock `delivery_target` to the real Wiki, document, web, or export viewport. Do not infer a slide-sized viewport merely because the diagram is wide. Select a preset or author `visual_behavior.mode: custom`, then resolve the pack palette, typography, stroke language, geometry, and connectors into `style_tokens`. The resolved colors, typography, and strokes must exactly match `pack_identity`. The visual gate evaluates the final effective size after the canvas is scaled into the delivery target.
