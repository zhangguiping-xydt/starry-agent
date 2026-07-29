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
| `no_slide_chrome` | The diagram does not add page furniture, decorative card grids, hero copy, badges, or imagery unrelated to technical reading. |

## Review artifact

```yaml
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
  no_slide_chrome: passed
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
