# Layout Planning

Select a reading viewpoint, notation profile, and technical composition before writing semantic source or visual SVG. Read `../templates/notations/technical_notations.yaml` and `../templates/layouts/technical_layouts.yaml`, evaluate every allowed pattern's `pick_when`, `skip_when`, and `alternatives`, and record the selected notation and pattern in both the manifest and lock. A positive keyword match is insufficient when a skip condition applies.

## Layout plan contract

Every generated `diagram_lock.yaml` contains:

```yaml
layout_plan:
  pattern: branching-flow
  selection_reason: "The source has one happy path, two explicit decisions, and converging exception routes."
  direction: left-to-right
  density: balanced
  view_role: standalone
  primary_items: [start, validate, decide, finish]
  regions:
    - id: exceptions
      placement: bottom
      members: [retry, fail]
  edge_roles:
    primary: [start-validate, validate-decide, decide-finish]
    secondary: [decide-retry, retry-validate]
    control: []
```

Allowed density values are `sparse`, `balanced`, and `dense`. Allowed view roles are `standalone`, `overview`, and `detail`. Region placement is one of `top`, `bottom`, `left`, `right`, `center`, `background`, or `lanes`.

`selection_reason` must cite source-grounded structure that satisfies the selected pattern and explain why the nearest alternative is not primary. For a non-preferred pattern, also provide `layout_plan.reason` describing why the preferred renderer/layout cannot express the source cleanly.

Apply density as an execution rule:

- `sparse`: emphasize one mechanism or short primary path; expand whitespace and do not add supporting regions merely to fill the canvas.
- `balanced`: use the style's locked gaps and keep primary and secondary information visibly distinct.
- `dense`: use only for a detail or standalone view whose item count remains within budget; preserve every typography role and gap floor. `dense` is invalid for an overview.

Some patterns also define `readability_limits`, which are softer than the hard section budget but still executable. Exceeding a sequence diagram's participant/message soft limit requires contiguous `phase` fragments that partition the message stream. Preserve source-grounded `alt|opt|loop|ref` fragments for control semantics, but do not treat them as a substitute for density partitioning. If phases cannot stay within budget, split the scenario; a taller canvas is not mitigation.

`view_role: overview` prioritizes topology and major boundaries; move operational labels or exception detail to companion views. `view_role: detail` may carry more annotations but cannot shrink typography or bypass complexity limits.

`primary_items` establishes visual hierarchy; it does not add or reorder semantics. Every edge-like semantic id must appear exactly once in `edge_roles.primary`, `edge_roles.secondary`, or `edge_roles.control`. Region members must reference existing non-edge semantic ids and may appear in at most one region.

## Complexity gate

The selected layout pattern defines executable per-section and total-item limits. If a candidate exceeds a limit, split it into overview/detail or separate concern diagrams before creating the lock.

Do not bypass the limit with smaller fonts, a larger canvas, or denser routing. An over-budget single diagram is allowed only when the user explicitly approves it; record:

```yaml
layout_plan:
  complexity_exception:
    user_approved: true
    reason: "The user explicitly requires a single printable topology map."
```

The validator rejects an unapproved exception and reports an approved exception as a warning.

## Construction order

1. Allocate canvas regions, lanes, layers, boundaries, or rails required by the notation profile.
2. Place `primary_items` on the dominant reading axis.
3. Place region members and secondary items without disturbing the primary path.
4. Route primary edges, then secondary edges, then control edges.
5. Test endpoint alignment and the selected layout's `routing_family`. A clear same-axis connection stays straight; a clear off-axis connection may use the smallest type-native orthogonal route instead of a diagonal.
6. Reserve symmetric diagonals for source-grounded decision/merge branches and radial/loop layouts. Put verified backward feedback, loopbacks, obstacle avoidance, and control connections on outer rails or shared buses.
7. Run the geometry-aware visual gate and revise until crossings, node intrusions, unnecessary detours, routing-rhythm violations, long routes, and typography checks pass.

The catalog is a composition grammar, not a slide template. Do not add page chrome, decorative imagery, card grids, or shadows that do not improve technical reading.
