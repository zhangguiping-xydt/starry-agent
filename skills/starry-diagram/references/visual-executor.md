# Visual Executor

Enhance presentation after the semantic quality gate passes. When asked for a polished SVG or to describe `visual.svg`, explicitly state that `source.*` and `semantic.svg` must be generated and validated before `visual.svg`; the visual track is never the starting point.

The output is a technical diagram. Prioritize notation fidelity, topology, containment, routing, legibility, and editability. Do not introduce slide chrome, decorative imagery, or effects that do not improve technical reading.

## Allowed changes

- Improve layout, spacing, alignment, hierarchy, grouping, and whitespace.
- Apply typography, strokes, fills, shadows, and subtle effects from `style_tokens`.
- Normalize canvas size and viewBox while keeping all semantic labels visible.
- Add stable semantic metadata required by the visual gate.

## Forbidden changes

- Adding, deleting, renaming, or merging nodes, entities, participants, states, messages, or edges.
- Changing direction, cardinality, state transition meaning, event topic, command/event identity, or group membership.
- Using colors, fonts, icons, or effects outside `style_tokens` unless the lock is updated by the strategist first.
- Moving an activity outside its lane, a component outside its boundary, or a message outside its locked order.

## Enhancement levels

- light: retain rendered structure; improve label readability and spacing.
- medium: tune layout and grouping while preserving renderer topology.
- strong: create a polished SVG composition, still constrained by every lock item.

Only use `style_tokens` for visual decisions.

## Layout execution

Read `layout_plan` and the selected entry in `templates/layouts/technical_layouts.yaml` before editing geometry.

1. Allocate regions, lanes, layers, boundaries, or rails before placing nodes.
2. Place `primary_items` on the pattern's dominant reading axis.
3. Place secondary region members without weakening the primary path.
4. Route `edge_roles.primary`, then `secondary`, then `control`.
5. Route loopbacks and control links on outer rails, shared buses, or explicit ports.
6. Run the geometry-aware visual gate and revise until it passes.

Do not solve excess complexity by shrinking labels, lengthening the canvas, or routing repeated diagonals across unrelated regions.

## Semantic metadata

Wrap every semantic visual item in a group with `data-diagram-id` and `data-diagram-kind`. Edge-like items also carry `data-from` and `data-to`. Groups and lanes carry `data-members="id-a,id-b"`. These attributes make semantic equivalence machine-verifiable and do not affect rendering.

When the renderer already preserves lock ids, stamp the remaining metadata deterministically:

```bash
python scripts/stamp_visual_metadata.py diagram_lock.yaml visual.svg
```

The command fails if any locked item cannot be mapped. It does not count as visual enhancement because it does not change geometry.

## No-op rule

Light enhancement may retain renderer geometry. Medium and strong enhancement must produce a real geometric or typographic change. Metadata-only edits do not count. Validate against semantic.svg with `validate_visual_svg.py --semantic-svg`.
