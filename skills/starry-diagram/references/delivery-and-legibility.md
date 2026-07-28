# Delivery and Legibility

Lock the final embedding viewport before placing nodes. SVG source dimensions are not a readability guarantee: a 13-unit label on a 1920-wide canvas becomes roughly 8px when embedded at 1200px.

## Delivery target

Every generated lock contains:

```yaml
delivery_target:
  width_px: 1200
  height_px: 675
  fit: contain
  min_effective_font_px: 12
  min_contrast_ratio: 4.5
  min_text_padding_px: 6
  max_edge_label_distance_px: 28
  max_unmeasurable_text_fraction: 0
```

`height_px` is optional. When omitted, derive preview height from the SVG viewBox. Effective font size is the locked SVG font size multiplied by the contain scale into this viewport.

Do not change `delivery_target` to make a failed diagram pass unless the real consumer viewport changed. Split or reflow the diagram instead.

## Typography roles

Use the complete scale from the selected style:

```yaml
typography:
  font_family: "Noto Sans CJK SC"
  diagram_title_size: 28
  group_title_size: 18
  node_title_size: 16
  node_body_size: 14
  edge_label_size: 14
  annotation_size: 13
  min_font_size: 12
```

Put one exact role on every visible SVG text element:

| `data-text-role` | Use |
| --- | --- |
| `diagram-title` | Diagram title inside the canvas |
| `group-title` | Layer, boundary, lane, or cluster heading |
| `node-title` | Primary node, participant, entity, or state label |
| `node-body` | Node descriptions, fields, or secondary lines |
| `edge-label` | Call, event, condition, cardinality, or transition label |
| `annotation` | Legend, note, evidence, or guardrail annotation |

Do not use arbitrary intermediate sizes. If a distinct hierarchy is required, change the style lock before drawing and keep that role consistent across the diagram pack.

## Geometry adapts to typography

Use this correction order when text fails:

1. Preserve the locked role size.
2. Wrap at semantic phrase boundaries.
3. Increase node width or height to restore padding.
4. Recompute peer alignment, lanes, layers, and region bounds.
5. Reroute primary, secondary, and control edges.
6. Split the diagram if the delivery viewport still cannot preserve the minimum effective size.

Never fix overflow by shrinking one label, clipping text, hiding details, or increasing canvas dimensions independently of the delivery target.

## Visual acceptance

`validate_visual_svg.py` evaluates the final SVG at delivery scale and rejects:

- missing or inconsistent text roles;
- effective font sizes below the delivery minimum;
- text outside its owning node or required padding;
- text-to-text and node-to-node overlaps;
- nodes outside the canvas;
- edge labels overlapping nodes or too far from their own route;
- contrast below the locked ratio;
- transforms or implicit positions that make too much text unmeasurable.

After the SVG passes, render the mandatory consumer-size preview:

```bash
python scripts/render_preview.py diagram_lock.yaml visual.svg preview.png \
  --report preview_render_report.json
```

Inspect the PNG at 100% using `technical-visual-review.md`, bind `preview_review.yaml` to both the PNG and `visual.svg` SHA-256 values, and validate the review. Then run `build_check_report.py`. It independently checks PNG dimensions and fails when the preview is absent, does not match `delivery_target`, or has a stale/failed technical review.
