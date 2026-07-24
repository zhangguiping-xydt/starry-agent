# Quality Gate

Run every gate before handoff. A report written by the agent is not proof; generate reports with the bundled scripts.

## Gate order

1. `validate_diagram_manifest.py diagram_manifest.yaml --root <pack-root>`
2. `validate_diagram_lock.py diagram_lock.yaml`
3. `validate_semantic_source.py diagram_lock.yaml source.*`
4. Render semantic.svg and write render_report.json.
5. Create visual.svg after the semantic gate passes.
6. `validate_visual_svg.py diagram_lock.yaml visual.svg --semantic-svg semantic.svg`
7. `build_check_report.py <diagram-directory>`
8. `build_embed_blocks.py <pack-root>` only after every generated diagram passes.

## Lock checks

- Diagram type exists in `diagram_profiles.yaml`.
- Source format is allowed by the type profile.
- A non-preferred renderer has a source-grounded `renderer_reason`.
- Enhancement level meets the type minimum.
- Type-specific semantic sections exist and are internally valid.
- Fixed canvas dimensions and viewBox agree; auto canvas bounds are valid.
- Technical style defines required colors, font family, and minimum font size.

## Manifest checks

- Required pack metadata and diagram entries exist.
- Diagram ids are unique and statuses are valid.
- Generated entries declare renderer and enhancement level allowed by their type profile.
- Skipped and needs_clarification entries name the missing facts.
- Generated entry id, type, renderer, style, and enhancement level match diagram_lock.yaml.
- Generated entry layout pattern matches diagram_lock.yaml.

## Semantic checks

- Every locked semantic item has a stable source identity.
- Every locked label is present.
- Endpoints and memberships reference existing semantic ids.
- Sequence order, ER fields/keys/cardinalities, state transitions, and swimlane ownership pass their type rules.

## Visual checks

- SVG parses and its canvas follows the lock.
- Required labels remain visible.
- Colors and fonts come from style_tokens.
- No text falls below the locked minimum font size.
- Every semantic id is present exactly once through stable metadata or a supported renderer id.
- Edge endpoints and group/lane memberships match the lock.
- No unlisted semantic identity is introduced.
- Medium and strong enhancement are not geometry-identical to semantic.svg.
- Every non-container semantic item is covered by the layout plan and every edge has one visual role.
- Selected layout complexity limits are not exceeded without explicit user approval.
- Analyzable edge coverage meets the selected layout threshold.
- Edge crossings, edge-to-nonendpoint-node intersections, and long routes stay within the selected layout limits.
- Edge labels meet `style_tokens.typography.edge_label_size`, not only the global minimum.

## Failure handling

| Failure | Handling |
| --- | --- |
| Missing source facts | Mark skipped or needs_clarification in manifest |
| Invalid profile, routing, or lock | Stop before semantic source generation |
| Semantic mismatch | Fail semantic gate; do not render |
| Renderer unavailable | Write render_unavailable and a failed check report |
| Visual semantic drift | Write visual_failed; keep semantic artifacts |
| Visual no-op at medium/strong | Fail visual gate and perform the required visual work |
| Pack contains a failed diagram | Fail diagram_pack_report; do not present the pack as passed |
