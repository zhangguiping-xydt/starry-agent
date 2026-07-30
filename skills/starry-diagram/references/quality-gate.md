# Quality Gate

Run every gate before handoff. A report written by the agent is not proof; generate reports with the bundled scripts.

## Gate order

1. `validate_diagram_manifest.py diagram_manifest.yaml --root <pack-root>`
2. `validate_diagram_lock.py diagram_lock.yaml`
3. `validate_semantic_source.py diagram_lock.yaml source.*`
4. Render semantic.svg and write render_report.json.
5. Create visual.svg after the semantic gate passes.
6. `validate_visual_svg.py diagram_lock.yaml visual.svg --semantic-svg semantic.svg`
7. `render_preview.py diagram_lock.yaml visual.svg preview.png --report preview_render_report.json`
8. Inspect `preview.png` at 100%, revise until the technical visual review passes, and write `preview_review.yaml`.
9. `validate_preview_review.py preview.png preview_review.yaml`
10. If `raster_delivery` is declared, `render_delivery_raster.py diagram_lock.yaml visual.svg delivery.png --report delivery_render_report.json`.
11. `build_check_report.py <diagram-directory>`
12. `build_embed_blocks.py <pack-root>` only after every generated diagram passes.

## Lock checks

- Diagram type exists in `diagram_profiles.yaml`.
- Source format is allowed by the type profile.
- A non-preferred renderer has a source-grounded `renderer_reason`.
- Enhancement level meets the type minimum.
- Type-specific semantic sections exist and are internally valid.
- Type-native semantic grammar passes: process/data-object separation, decision/merge topology, standard state pseudo-states, contiguous sequence order and density mitigation, and explicit loop feedback.
- Fixed canvas dimensions and viewBox agree; auto canvas bounds are valid.
- Delivery target defines the actual embedding viewport and legibility thresholds.
- Contract v4 defines pack visual behavior separately from palette, typography, stroke language, and texture; resolved style tokens exactly match the pack identity.
- Layout selection has a source-grounded reason after Pick/Skip/Alternative evaluation.
- Contract v3 locks declare viewpoint, reading question, notation profile, and valid notation roles.
- Layout-specific notation signatures exist, such as a decision in a branching flow or a boundary in a layered architecture.

## Manifest checks

- Required pack metadata and diagram entries exist.
- Diagram ids are unique and statuses are valid.
- Generated entries declare renderer and enhancement level allowed by their type profile.
- Skipped and needs_clarification entries name the missing facts.
- Generated entry id, type, renderer, style, and enhancement level match diagram_lock.yaml.
- Generated entry layout pattern matches diagram_lock.yaml.
- Contract v3 generated entries declare distinct reading questions and compatible viewpoint/notation profiles.
- Repeated pack viewpoints or visual signatures have a source-grounded diversity reason only when no fact-complete alternative exists.
- Every generated v4 diagram declares a renderer family equal to its technical type and a per-diagram treatment.

## Semantic checks

- Every locked semantic item has a stable source identity.
- Every locked label is present.
- Endpoints and memberships reference existing semantic ids.
- Sequence order, ER fields/keys/cardinalities, state transitions, and swimlane ownership pass their type rules.
- Sequence call/return kinds and phase fragments remain source-grounded; high-density scenarios cannot pass as one ungrouped message wall.

## Visual checks

- SVG parses and its canvas follows the lock.
- Required labels remain visible.
- Colors and fonts come from style_tokens.
- SVG root identity metadata and actual stroke widths/caps/joins match the v4+ pack identity.
- Contract v5 semantic groups carry the computed visual tiers; focal emphasis and composition-span checks pass.
- Every visible text element declares a locked `data-text-role` and uses that role's exact size.
- No text falls below the minimum effective font size after scaling into the delivery viewport.
- Every semantic id is present exactly once through stable metadata or a supported renderer id.
- Edge endpoints and group/lane memberships match the lock.
- Every locked notation role matches `data-notation-role` and a permitted real SVG shape.
- Decisions, lifelines, datastores, terminals, boundaries, lanes, and state markers cannot be replaced by generic rectangles.
- Flow data objects render as note/data-object geometry, state initial/final markers use standard pseudo-state geometry, and sequence returns use dashed connectors while calls remain solid.
- No unlisted semantic identity is introduced.
- Medium and strong enhancement are not geometry-identical to semantic.svg.
- Every non-container semantic item is covered by the layout plan and every edge has one visual role.
- Selected layout complexity limits are not exceeded without explicit user approval.
- Analyzable edge coverage meets the selected layout threshold.
- Edge crossings, edge-to-nonendpoint-node intersections, and long routes stay within the selected layout limits.
- Contract v5 clear forward edges use direct routes; bend counts and actual/direct detour ratios satisfy `technical_layouts.yaml.route_economy`.
- Edge labels meet `style_tokens.typography.edge_label_size`, not only the global minimum.
- Text stays inside its owning geometry with locked delivery padding.
- Text and nodes do not overlap or leave the canvas.
- Edge labels do not overlap nodes and remain unambiguously anchored to their own route.
- Text contrast meets the delivery target ratio.
- Measurable text coverage meets the delivery target threshold.

## Preview checks

- `preview.png` exists and is rendered from the passed `visual.svg`.
- PNG dimensions exactly match `delivery_target`; derive height from viewBox when omitted.
- `build_check_report.py` validates the PNG independently of the renderer report.
- `preview_review.yaml` matches the current PNG and visual SVG hashes and every technical visual review check passes.
- When `raster_delivery` is declared, the font stack resolves to a declared non-generic family, `delivery.png` dimensions equal the logical target dimensions multiplied by `pixel_ratio`, and `delivery_render_report.json` binds it to the current `visual.svg`; it is not used as the target-size review artifact.

## Failure handling

| Failure | Handling |
| --- | --- |
| Missing source facts | Mark skipped or needs_clarification in manifest |
| Invalid profile, routing, or lock | Stop before semantic source generation |
| Repeated viewpoint or visual signature | Select a fact-complete alternate view, split companion views, or record why repetition is unavoidable |
| Three or more technical types collapse into one rounded-card signature | Use type-native renderers; use `visual_diversity_reason` only when the source truly prevents a distinct technical treatment |
| Notation role or geometry mismatch | Use the selected technical symbol; metadata-only relabeling is not a fix |
| Type-native semantic grammar failure | Reclassify the semantic item, repair topology, add source-grounded sequence fragments, or split the diagram; do not silence the rule with styling |
| Semantic mismatch | Fail semantic gate; do not render |
| Renderer unavailable | Write render_unavailable and a failed check report |
| Visual semantic drift | Write visual_failed; keep semantic artifacts |
| Visual no-op at medium/strong | Fail visual gate and perform the required visual work |
| Text overflow or undersized delivery text | Expand/reflow geometry, reroute downstream edges, or split the diagram |
| Clear edge takes an unnecessary dogleg | Replace it with the direct chord; retain bends only for detected obstacles, backward feedback, or control rails |
| Missing or wrong-size preview | Render `preview.png` at the locked delivery target and rebuild reports |
| Missing or wrong-size raster delivery | Render `delivery.png` from `visual.svg` at the declared `pixel_ratio`; keep `preview.png` unchanged |
| Raster font resolves to an undeclared fallback | Install a declared family or update the style font stack, then rerender; do not sharpen the bitmap |
| Stale or failed technical review | Inspect the current preview, revise the SVG, rerender, and rebind the review hash |
| Pack contains a failed diagram | Fail diagram_pack_report; do not present the pack as passed |
