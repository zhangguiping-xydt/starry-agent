# Technical Notation Contract

Contract version 3 introduced executable viewpoint and notation roles. Contract version 4 added pack identity, custom visual behavior, per-type treatments, and actual visual-signature checks. Use contract version 5 for new diagram packs; it additionally binds treatment to visible hierarchy, focal emphasis, and content-span composition checks. Diagrams may share palette, typography, and stroke language, but their geometry must remain recognizable as the locked technical type.

## Manifest fields

Every generated entry declares:

```yaml
viewpoint_family: decision
reading_question: Which conditions reject or converge the request?
notation_profile: activity-flow
```

`reading_question` must be distinct inside the pack. Use `viewpoint_reason` when selecting an allowed but non-preferred viewpoint. When more than half of a pack with at least four generated diagrams uses one viewpoint, or one viewpoint/layout/notation signature appears more than twice, record a source-grounded `diversity_reason`. Do not use this exception merely to avoid evaluating eligible alternatives.

The diversity gate never overrides the fact gate. Do not create an ER, deployment, state, event, or ownership view without its required facts.

## Lock fields

Copy the manifest viewpoint, reading question, and notation profile into `diagram_lock.yaml`. Every generated entry in a v3-or-newer manifest must point to a lock with at least the same contract version; mixing it with a legacy v2 lock is invalid because it would bypass notation enforcement. Add `notation_role` to every semantic record covered by the notation profile:

```yaml
nodes:
  - id: validate-input
    label: Input valid?
    notation_role: decision
```

Read `../templates/notations/technical_notations.yaml` for the allowed roles, layout-specific requirements, and visual shapes. Do not invent a role outside the selected notation profile.

Contract v4 also enforces type-native semantic grammar:

- Flow: `decision` has at least two outgoing branches; `merge` has at least two incoming branches; `data-object` stays in a side region and connects through `kind: data` on the control rail.
- State: exactly one unlabeled `initial` pseudo-state and at least one unlabeled `final` pseudo-state; initial has one outgoing transition and no incoming transition; final has no outgoing transition.
- Sequence: message orders are contiguous; `kind: call` and `kind: return` remain distinct; high-density scenarios partition all messages into contiguous `phase` fragments. `alt`, `opt`, `loop`, and `ref` remain available for source-grounded control semantics and do not replace density phases.
- Loop mechanism: the secondary relation set includes a real backward feedback relation rather than a decorative enclosing curve.

## SVG metadata and geometry

Every locked notation role must appear on the corresponding semantic SVG group:

```xml
<g data-diagram-id="validate-input"
   data-diagram-kind="node"
   data-notation-role="decision">
  <polygon points="..." />
</g>
```

`stamp_visual_metadata.py` copies locked notation roles but does not prove the geometry. `validate_visual_svg.py` independently inspects the SVG descendants. Metadata cannot make a rectangle pass as a decision diamond, a header-only participant pass as a sequence lifeline, or a plain rectangle pass as a datastore.

Likewise, a folded-note data object cannot substitute for an action, a single labeled circle cannot substitute for a UML final marker, and a solid response line cannot satisfy `kind: return`.

## Compatibility

Legacy v2 packs remain readable and produce a warning because they do not contain viewpoint or notation evidence. Do not create new v2 packs. Upgrade a diagram to v3 only after assigning source-grounded roles and revising its SVG to satisfy the real geometry contract; use v4 for new work so pack identity and type-native treatment are also enforced.
