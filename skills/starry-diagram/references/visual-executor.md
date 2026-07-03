# Visual Executor

Enhance presentation after the semantic quality gate passes. When asked for a polished SVG or to describe `visual.svg`, explicitly state that `source.*` and `semantic.svg` must be generated and validated before `visual.svg`; the visual track is never the starting point.

## Allowed changes

- Improve layout, spacing, alignment, hierarchy, grouping, and whitespace.
- Apply typography, strokes, fills, shadows, and subtle effects from `style_tokens`.
- Normalize canvas size and viewBox while keeping all semantic labels visible.

## Forbidden changes

- Adding, deleting, renaming, or merging nodes, entities, participants, states, messages, or edges.
- Changing direction, cardinality, state transition meaning, event topic, command/event identity, or group membership.
- Using colors, fonts, icons, or effects outside `style_tokens` unless the lock is updated by the strategist first.

## Enhancement levels

- light: retain rendered structure; improve label readability and spacing.
- medium: tune layout and grouping while preserving renderer topology.
- strong: create a polished SVG composition, still constrained by every lock item.

Only use `style_tokens` for visual decisions.
