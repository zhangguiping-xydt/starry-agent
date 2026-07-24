# Layout Planning

Select a technical composition before writing semantic source or visual SVG. Read `../templates/layouts/technical_layouts.yaml`, evaluate every layout pattern allowed by the selected type profile, and record the selected pattern in both the manifest and lock.

## Layout plan contract

Every generated `diagram_lock.yaml` contains:

```yaml
layout_plan:
  pattern: branching-flow
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

1. Allocate canvas regions, lanes, layers, boundaries, or rails.
2. Place `primary_items` on the dominant reading axis.
3. Place region members and secondary items without disturbing the primary path.
4. Route primary edges, then secondary edges, then control edges.
5. Put loopbacks and control connections on outer rails or shared buses.
6. Run the geometry-aware visual gate and revise until crossings, node intrusions, long routes, and typography checks pass.

The catalog is a composition grammar, not a slide template. Do not add page chrome, decorative imagery, card grids, or shadows that do not improve technical reading.
