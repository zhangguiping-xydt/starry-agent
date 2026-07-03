# Output Contract

## Pack layout

```text
pack/
  diagram_manifest.yaml
  diagram_pack_report.json
  <diagram-id>/
```

## Per diagram layout

```text
<diagram-id>/
  diagram_spec.md
  diagram_lock.yaml
  source.*
  semantic.svg or render_unavailable
  visual.svg or visual_failed
  embed.md
  check_report.json
```

## Embed block

`embed.md` embeds `visual.svg` first. If `visual.svg` is missing, use `semantic.svg`. If both are unavailable, link to `render_unavailable` and `check_report.json` so the user sees the exact failure reason.
