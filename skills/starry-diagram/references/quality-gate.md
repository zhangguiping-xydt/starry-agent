# Quality Gate

Validate every pack and diagram before handoff.

## Checks

- Manifest schema: `project`, `mode`, `source_summary`, and `diagrams` exist; each diagram has id, type, status, and reason.
- Lock schema: `id`, `title`, `type`, `source_format`, `visual_style`, `canvas`, `nodes`, `edges`, `groups`, and `style_tokens` exist where required.
- Semantic source matches lock: all required nodes, participants, entities, states, messages, edges, fields, and labels are present; no unlisted semantics are introduced.
- Cross-diagram naming: the same entity uses the same canonical label/id from the manifest `naming_glossary` across all generated diagrams.
- Missing facts: every `needs_clarification` entry includes a non-empty `missing` list; fact-insufficient `skipped` entries should also name the missing facts.
- Edge semantics: complex interaction, event-flow, and data-flow diagrams do not mix command/event/data/projection meanings ambiguously; edge kinds must come from the lock (`command`, `event`, `data`, `projection`, or `call`).
- Renderer output/render_unavailable: either `semantic.svg` exists and is well formed, or `render_unavailable` records why rendering could not run.
- Visual SVG: XML parses, viewBox exists, labels match lock, colors come from style tokens, and semantic structure is unchanged.
- Reports: write per-diagram `check_report.json` and pack-level `diagram_pack_report.json`.

## Failure handling

| Failure | Handling |
| --- | --- |
| Missing source facts | Mark skipped or needs_clarification in manifest |
| Invalid lock | Stop diagram generation and report schema errors |
| Semantic mismatch | Fail semantic gate; do not run visual track |
| Renderer unavailable | Write `render_unavailable` and continue report generation |
| Visual semantic drift | Write `visual_failed`; keep semantic artifacts |
| Embed unavailable | Report failure and point to semantic or visual fallback |
