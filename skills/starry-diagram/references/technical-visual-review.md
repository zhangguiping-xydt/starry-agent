# Technical Visual Review

Run this review after static visual validation and target-size preview rendering. Inspect `preview.png` at its original pixel size with an available image-viewing tool; do not zoom in to compensate for poor delivery readability.

## Review loop

1. Open `preview.png` at 100%.
2. Evaluate every check below against the locked diagram type, viewpoint, notation profile, layout pattern, and `view_role`.
3. Fix the SVG when a check fails. Preserve semantics and typography roles, then rerun visual validation and preview rendering.
4. Repeat until every check passes.
5. Copy `../templates/locks/preview_review_reference.yaml` to `preview_review.yaml` and replace both SHA-256 values with the reviewed preview and source visual hashes.
6. Run `validate_preview_review.py`; a stale hash or unresolved finding fails the diagram.

## Required checks

| Check | Pass condition |
| --- | --- |
| `diagram_type_recognizable` | The visual grammar reads as the locked architecture, flow, sequence, ER, state, deployment, or other technical type without relying on the title. |
| `primary_path_clear` | The dominant dependency, process, message order, or lifecycle can be followed within a few seconds. |
| `grouping_and_boundaries` | Layers, lanes, zones, contexts, and containment communicate source-grounded ownership or placement without ambiguity. |
| `edge_label_ownership` | Direction and label-to-edge ownership are visually obvious, including loops, exceptions, and long routes. |
| `emphasis_matches_view_role` | Overview emphasizes topology and boundaries; detail emphasizes the selected mechanism without making secondary information compete with the primary path. |
| `technical_notation_fidelity` | Arrow direction, cardinality, participant order, state notation, containment, and edge kinds preserve the lock. |
| `semantic_roles_readable` | Actions, decisions, data objects, states, participants, stores, boundaries, and control/feedback relations are distinguishable by geometry and placement without reading metadata. |
| `density_and_whitespace` | The target-size image has no message wall, stranded region, oversized store/control area, or large empty band that weakens the primary reading path. |
| `no_slide_chrome` | The diagram does not add page furniture, decorative card grids, hero copy, badges, or imagery unrelated to technical reading. |
| `visual_hierarchy_clear` | The v5 focal, primary, secondary, control, and context tiers are visible without inspecting metadata; the focal item is a real reading anchor. |
| `composition_content_driven` | The canvas, dominant axis, spacing, and containment follow this diagram's reading question and topology rather than repeating another diagram's skeleton. |
| `edge_route_economy` | Clear same-axis edges connect directly; off-axis bends stay minimal; every outer rail has an obvious obstacle, feedback, loopback, boundary-port, or control purpose. |
| `edge_routing_rhythm` | Connector geometry reinforces the selected layout: layered/boundary views use an orthogonal spine, decision branches are balanced, lifecycle transitions stay on their axis, and the page does not become a diagonal web. |
| `edge_routing_composition` | The full connector set reads as a designed system: architecture dependencies share backbones/ports, flows have a main spine and explicit branches, loops follow a visible orbit, and sequence/lifecycle straight lines remain type-native rather than being penalized as over-direct. |

## Review artifact

```yaml
contract_version: 6
preview_sha256: "<sha256 of preview.png>"
visual_svg_sha256: "<sha256 of visual.svg>"
reviewed_at_target_size: true
status: passed
checks:
  diagram_type_recognizable: passed
  primary_path_clear: passed
  grouping_and_boundaries: passed
  edge_label_ownership: passed
  emphasis_matches_view_role: passed
  technical_notation_fidelity: passed
  semantic_roles_readable: passed
  density_and_whitespace: passed
  no_slide_chrome: passed
  visual_hierarchy_clear: passed
  composition_content_driven: passed
  edge_route_economy: passed
  edge_routing_rhythm: passed
  edge_routing_composition: passed
findings: []
```

When a review discovers a problem, add a finding while revising:

```yaml
findings:
  - issue: "The retry loop visually crosses the happy path and reads as a forward edge."
    resolved: true
    resolution: "Moved the loop to the outer control rail and regenerated the preview."
```

The final artifact may contain resolved findings, but every finding must set `resolved: true`, the preview and visual hashes must match the current artifacts, and all required checks must be `passed`.

This review supplements machine validation. It cannot override a failed notation-role, geometry, manifest-diversity, or semantic gate.
