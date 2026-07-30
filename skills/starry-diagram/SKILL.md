---
name: starry-diagram
description: Use when creating design diagrams, diagram packs, architecture diagrams, ER diagrams, sequence diagrams, swimlane diagrams, business flows, data flows, deployment diagrams, state machines, event flows, or polished SVG diagrams from requirements, PRDs, technical designs, architecture notes, or design documents.
---

# Starry Diagram

## Overview

Create trustworthy diagram packs from source material. The semantic source is truth, enhanced SVG is presentation. Every visual output must preserve the semantic contract recorded in locks and reports.

## Mandatory Pipeline

Source intake → Diagram Strategist → type/viewpoint/layout/notation selection and complexity/diversity gate → pack identity and executable per-diagram treatment lock → `diagram_manifest.yaml` → `diagram_spec.md`/`diagram_lock.yaml` → delivery target and typography lock → Semantic track before visual track → type-native semantic grammar and density gate → content-driven visual hierarchy and composition → type-native Visual track → notation/identity/geometry/legibility/composition quality gate → target-size preview → technical visual review and revision loop → optional high-density raster delivery → `embed.md` and reports.

Execute every gate with the bundled scripts. A written claim that a gate passed is not sufficient.

## Default diagram-pack mode

When the user does not specify a diagram type, evaluate architecture/business-architecture/flow/swimlane/sequence/er/state/data-flow/deployment/component/event-flow/concept. Each candidate status must be one of generated/skipped/needs_clarification with a source-grounded reason. New packs use `contract_version: 5`; every generated entry declares a distinct `reading_question`, a source-grounded `viewpoint_family`, a compatible `notation_profile`, and a type-native `diagram_treatment`.

## Fact gate

Do not invent services, roles, fields, relationships, states, calls, events, or cardinalities. If a required fact is absent from source material, mark the diagram as skipped or needs_clarification instead of filling gaps.

## Type profile gate

Before creating a generated entry, read `templates/profiles/diagram_profiles.yaml`, `templates/layouts/technical_layouts.yaml`, `templates/notations/technical_notations.yaml`, and the selected `references/diagram-types/<type>.md`. Evaluate every candidate's `pick_when`, `skip_when`, and `alternatives`; do not choose from positive keyword matches alone. Treat the type profile, viewpoint, notation profile, and selected layout pattern as executable contracts for semantic sections, renderers, composition, technical symbols, complexity limits, routing quality, and enhancement level. Record `layout_pattern` in the manifest and a complete `layout_plan.selection_reason` in the lock. When using an allowed but non-preferred renderer, viewpoint, or layout, also record a source-grounded fallback reason.

For packs with four or more generated diagrams, evaluate viewpoint and visual-signature repetition before writing locks. Do not force an inapplicable type to satisfy diversity. When the source genuinely supports only repeated views, record `diversity_reason`; otherwise select distinct eligible viewpoints or split overview/detail companion views.

## Visual identity gate

Read `references/visual-identity.md` before selecting or customizing appearance. Lock one `pack_identity` for family consistency, then give each generated diagram a `diagram_treatment` whose `renderer_family` equals its technical type. Presets are editable starting points, not a closed style list; use `visual_behavior.mode: custom` for behavior that no preset captures.

Keep `style_tokens` as resolved deterministic values and validate that their colors, typography, and strokes match the pack identity. Use `style_tokens.connectors.routing: adaptive` for contract v5+: connector geometry belongs to the selected technical type and edge role, not the visual preset. Before drawing each diagram, re-read the pack identity and the diagram's treatment. Share tokens and measurement helpers across renderers, but do not route different technical types through one generic card or `svg_node()` implementation.

For contract v5, make treatment executable: declare a source-grounded `focal_item` for focal/explanatory compositions plus explicit hierarchy, spacing, and differentiation strategies. The focal item must be on the primary path and visibly emphasized. Stamp `data-visual-tier` on every semantic element. The visual gate verifies tier binding, focal emphasis, canvas use, and stranded margins; prose intent alone cannot pass.

If a candidate exceeds the selected layout pattern's section or total-item limits, split it into overview/detail or separate concern diagrams before creating the lock. Only an explicit user-approved `layout_plan.complexity_exception` may keep an over-budget single diagram.

Run `python scripts/validate_diagram_manifest.py <diagram_manifest.yaml> --root <pack-root>` and `python scripts/validate_diagram_lock.py <diagram_lock.yaml>` before writing semantic source. Do not continue after a failed manifest or lock.

## Required Artifacts

Each generated diagram directory must contain `diagram_spec.md`, `diagram_lock.yaml`, `source.*`, `semantic.svg` or `render_unavailable`, `visual.svg` or `visual_failed`, `preview.png`, `preview_review.yaml`, `embed.md`, and `check_report.json`. When `raster_delivery` is present in the lock, it must also contain `delivery.png`, `delivery_render_report.json`, and `delivery_report.json`. The pack root must contain `diagram_manifest.yaml` and `diagram_pack_report.json`. Diagrams marked `skipped` or `needs_clarification` only require a manifest entry; do not create semantic source, SVG files, or a diagram directory for them unless the user explicitly asks for a diagnostic directory.

## Delivery and typography lock

Lock the real embedding viewport before layout. Read `references/delivery-and-legibility.md`, define `delivery_target`, and copy a complete role-based typography scale from the locked pack identity or selected preset. Judge font size, padding, label anchoring, and contrast after scaling the SVG into that viewport.

Treat typography as geometry. Keep each role size stable. When text does not fit, expand the node, reflow its lines, recompute neighboring geometry, and reroute downstream edges. Never shrink a role, enlarge the canvas, or hide text to pass the gate.

## Semantic track before visual track

Build and validate the source representation first, then render semantic output, and only then enhance presentation. The semantic track owns nodes, edges, labels, participants, entities, states, messages, cardinalities, and required grouping.

Give every semantic item a stable identity and every notation-covered item a source-grounded `notation_role`. Use `id="<lock-id>"` in Graphviz/SVG. In Mermaid and PlantUML, add a renderer-safe comment marker `diagram-id:<lock-id>` for every locked item. Run `python scripts/validate_semantic_source.py <diagram_lock.yaml> <source.*>` before rendering.

Treat semantic roles as executable grammar, not labels. In activity flows, keep data contracts and data objects off the primary process path and connect them through `kind: data` control-sidecar associations. Decisions require real alternative branches and merges require real convergence. In state machines, initial/final pseudo-states are unlabeled standard markers; put submit/accept meaning on transitions or named states. In high-density sequence diagrams, partition the message stream with contiguous `phase` fragments; use `alt|opt|loop|ref` only for source-grounded control semantics. Classify replies as `kind: return` so visual validation can require dashed return connectors.

## Visual track rule

Visual enhancement may improve layout, spacing, hierarchy, color, typography, and polish. visual.svg must not change semantics. Any visual result that adds, removes, renames, or re-wires semantic elements must fail the visual quality gate.

Treat outputs as technical diagrams, not presentation slides. Optimize notation fidelity, topology, containment, routing, legibility, and editability. Do not add decorative imagery, gratuitous shadows, or slide chrome.

Every semantic visual group must declare `data-diagram-id` and `data-diagram-kind`. Notation-covered items must also declare `data-notation-role`; edge-like items must declare `data-from` and `data-to`; groups and lanes must declare comma-separated `data-members`. Preserve the exact ids, roles, and endpoints from the lock. Metadata alone is insufficient: the visual gate verifies that the real SVG geometry matches the locked notation role.

For medium and strong enhancement, visual.svg must contain a real geometric or typographic improvement. Copying semantic.svg or changing metadata only is a failed visual stage.

Construct visual.svg from the locked layout plan: allocate regions first, place `primary_items` on the dominant axis, then route primary, secondary, and control edges in that order. When endpoints share a clear visual axis, connect them directly. When they do not, follow the selected layout's `routing_family`: use minimal orthogonal connectors for layered and boundary-heavy diagrams, reserve symmetric diagonals for real decision/merge branches, preserve lifecycle axes, and use radial connectors only for radial or loop layouts. Keep true obstacle avoidance, backward feedback, loopbacks, and control links on outer rails or shared buses. Put `data-text-role` on every visible `<text>`. The visual gate rejects excessive crossings, edges passing through non-endpoint nodes, unnecessary aligned-path bends, routing-family violations, excessive detour ratios, unsupported geometry coverage, overlong routes, node/text collisions, text overflow, role-size drift, low effective delivery size, weak contrast, and ambiguous edge-label anchoring.

For contract v4+, put `data-pack-identity`, `data-renderer-family`, and `data-composition-rhythm` on the SVG root. For v5, also bind every semantic item to its computed visual tier and execute the focal emphasis. Use only the permitted stroke widths, caps, and joins from `pack_identity.stroke_language`. The pack gate rejects repeated rounded-card signatures across distinct technical types unless the manifest records a source-grounded `visual_diversity_reason`.

Run:

```bash
python scripts/validate_visual_svg.py diagram_lock.yaml visual.svg --semantic-svg semantic.svg
python scripts/render_preview.py diagram_lock.yaml visual.svg preview.png --report preview_render_report.json
```

Open `preview.png` at 100% with an image-viewing tool and follow `references/technical-visual-review.md`. Revise and rerender until every technical review check passes, bind `preview_review.yaml` to the current PNG hash, then run:

```bash
python scripts/validate_preview_review.py preview.png preview_review.yaml --visual-svg visual.svg
python scripts/build_check_report.py <diagram-directory>
```

If the destination rasterizes images or does not reliably embed SVG, declare `raster_delivery` in the lock and render `delivery.png` after the preview review. `preview.png` remains the 1× consumer-size review artifact; `delivery.png` is a higher-pixel-density publication artifact and must never replace the target-size review.

Raster rendering must resolve `style_tokens.typography.font_family` to one of the explicitly declared non-generic families. A silent fallback to an unrelated system font is a failed delivery stage.

```bash
python scripts/render_delivery_raster.py diagram_lock.yaml visual.svg delivery.png --report delivery_render_report.json
```

Only hand off a diagram whose generated `check_report.json` has `status: passed`.

## References

- `templates/profiles/diagram_profiles.yaml` for executable per-type contracts.
- `templates/layouts/technical_layouts.yaml` for technical composition patterns, budgets, and geometry limits.
- `templates/notations/technical_notations.yaml` for viewpoint families, semantic roles, and executable visual-shape contracts.
- `references/diagram-types/<type>.md` for the selected diagram type.
- `references/strategist.md` for diagram pack planning and locks.
- `references/layout-planning.md` for the layout-plan schema and construction order.
- `references/technical-notation.md` for v3+ pack diversity, notation roles, and compatibility.
- `references/visual-identity.md` for contract v5 pack identity, executable per-type treatment, hierarchy, composition, and visual-signature gates.
- `references/delivery-and-legibility.md` for delivery viewport, typography roles, and text geometry.
- `references/technical-visual-review.md` for the mandatory target-size review and revision loop.
- `references/semantic-executor.md` for Mermaid/PlantUML/Graphviz/source routing.
- `references/visual-executor.md` for allowed visual enhancement.
- `references/quality-gate.md` for validation and failure handling.
- `references/output-contract.md` for artifact layout and embed blocks.

## Common Mistakes

- Starting from a polished SVG before creating `diagram_lock.yaml`.
- Generating an ER diagram when fields, keys, or cardinalities are missing.
- Naming the same node differently across diagrams, such as `Auth Service` in one diagram and `Authentication API` in another without a glossary mapping; use one canonical label/id from the pack glossary.
- Treating `visual.svg` as a place to add unstated relationships.
- Treating a technical diagram as a slide or infographic.
- Treating a schema, field capacity, file, payload, or other data object as an executable process step.
- Drawing labeled circles as state-machine initial/final pseudo-states or omitting a final marker.
- Keeping a high-density sequence diagram ungrouped after it exceeds the participant/message readability budget.
- Marking response messages as calls or rendering calls and returns with the same connector grammar.
- Selecting a layout after SVG generation instead of before the lock.
- Keeping an over-budget diagram on one canvas by shrinking text or expanding the canvas.
- Judging readability from the SVG source size instead of the locked delivery viewport.
- Omitting `data-text-role`, shrinking one label independently, or allowing text to overflow its node.
- Treating `preview.png` as optional or hand-authoring a preview pass report.
- Reviewing a zoomed SVG instead of the target-size PNG or leaving a stale preview-review hash.
- Uploading the 1× `preview.png` as the final image on a high-DPI raster-only destination instead of declaring and rendering `raster_delivery`.
- Trusting the SVG font-family string without verifying which installed font the rasterizer actually resolved.
- Repeating one viewpoint/layout/notation signature across a pack without evaluating fact-complete alternatives.
- Writing a persuasive treatment paragraph while rendering the same hierarchy, spacing, and canvas signature as every other diagram.
- Declaring a decision, datastore, state, boundary, or participant role in metadata while rendering generic card geometry.
- Leaving semantic items out of `primary_items`/regions or edges out of `edge_roles`.
- Routing control links repeatedly across the primary flow instead of using a side rail or companion view.
- Adding an elbow to a clear same-axis edge merely because a preset says `orthogonal`, or replacing a layout-native orthogonal spine with a web of clear but rhythm-breaking diagonals.
- Using a renderer or enhancement level that violates the selected type profile.
- Copying `semantic.svg` to `visual.svg` for medium or strong enhancement.
- Omitting stable semantic ids and endpoint metadata from visual.svg.
- Omitting `check_report.json` when a renderer is unavailable.
- Collapsing skipped and needs_clarification into the same state.
