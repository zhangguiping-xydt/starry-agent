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

## Raster publication density

The delivery viewport is measured in logical CSS pixels. It is not the same as the number of bitmap pixels used for publication. For destinations that rasterize uploads, do not reuse the 1× review preview as the final image. Add this optional lock block:

```yaml
raster_delivery:
  format: png
  pixel_ratio: 2
```

`pixel_ratio` must be an integer from 2 through 4. A 1200 × 675 logical viewport with `pixel_ratio: 2` produces a 2400 × 1350 `delivery.png`, while the diagram is still reviewed at 1200 × 675. The embedding HTML or destination metadata must preserve the logical viewport; increasing bitmap pixels must not make the diagram occupy more page width.

High-density raster delivery fixes edge and glyph sharpness on high-DPI screens. It does not fix undersized typography. If the 1× target-size preview is hard to read, reflow, enlarge typography, or split the diagram before rendering the publication bitmap.

The font stack must name at least one real, non-generic family before the generic fallback. Raster rendering resolves the stack with Fontconfig and records the selected family in `delivery_render_report.json`. If the stack resolves outside its declared non-generic families, rendering fails instead of silently substituting an unrelated font. Install Fontconfig and at least one declared family on the render host.

## Typography roles

Use the complete scale from the locked pack identity or selected preset:

```yaml
typography:
  font_family: "Source Han Sans CN, Noto Sans CJK SC, Microsoft YaHei, sans-serif"
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

When `raster_delivery` is declared, render the high-density publication artifact only after the target-size review passes:

```bash
python scripts/render_delivery_raster.py diagram_lock.yaml visual.svg delivery.png \
  --report delivery_render_report.json
```

`build_check_report.py` fails if the declared `delivery.png` is missing, its dimensions do not equal the logical delivery target multiplied by `pixel_ratio`, its resolved font is not one of the declared non-generic families, or its render-report hashes do not match the current `visual.svg` and `delivery.png`.
