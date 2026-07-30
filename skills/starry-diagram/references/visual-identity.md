# Visual Identity Contract

Use contract version 6 for new diagram packs. Keep technical truth separate from visual behavior. Contract v5 remains valid for existing packs and binds treatment prose to visible hierarchy and composition, but it does not require whole-diagram routing composition.

Apply locks in this order:

1. Technical contract: `type`, `viewpoint_family`, `notation_profile`, and `layout_plan`.
2. Pack identity: shared visual behavior, palette, typography, stroke language, and texture.
3. Diagram treatment: type-specific composition and emphasis.

Never let a visual choice change topology, notation roles, containment, cardinality, order, ownership, or state semantics.

## Pack identity

Declare one `pack_identity` in the manifest and copy it exactly into every generated diagram lock.

```yaml
pack_identity:
  id: precise-industrial
  visual_behavior:
    mode: custom
    description: Industrial control-console precision without dashboard chrome.
    shape_language: Sharp boundaries and type-native symbols; ordinary steps use low-radius rectangles.
    whitespace_rhythm: Compact primary path with wide outer rails for control and failure links.
    decoration: Numbering and evidence annotations only; no ornamental cards or illustrations.
    elevation: Flat hierarchy expressed with stroke weight and luminance.
  palette:
    background: "#f8fafc"
    surface: "#ffffff"
    primary: "#1d4ed8"
    accent: "#dc2626"
    text: "#0f172a"
    muted: "#64748b"
    line: "#94a3b8"
  typography: {}
  stroke_language:
    node_width: 1.4
    boundary_width: 1.2
    connector_width: 1.6
    emphasis_width: 2.4
    linecap: square
    linejoin: miter
  texture:
    mode: none
    description: Solid field without grain, grid, glow, or paper texture.
```

`visual_behavior` describes behavior, not colors. `palette` owns color truth. `typography` owns all role sizes and font families. `stroke_language` owns the permitted visible stroke widths, caps, and joins. `texture` is free-form but must remain subordinate to technical reading.

For `mode: preset`, set `preset_id` and copy the selected preset into the pack identity. Presets are starting points, not a closed style vocabulary.

For `mode: custom`, write all behavioral fields directly. Do not create a new preset merely because a request uses unfamiliar aesthetic language.

## Resolved style tokens

Keep `style_tokens` as the deterministic renderer input. For contract v4:

- `style_tokens.colors` exactly equals `pack_identity.palette`.
- `style_tokens.typography` exactly equals `pack_identity.typography`.
- `style_tokens.strokes` exactly equals `pack_identity.stroke_language`.
- `style_tokens.connectors.width` equals `stroke_language.connector_width`.
- `style_tokens.connectors.routing` is `adaptive` for contract v5+: presets do not force every technical type through one connector grammar.
- Geometry and connector tokens may be selected for the pack, but must not erase type-native notation or override the v6 routing composition. Local directness is not absolute: a locked spine, bus, rail, port, orbit, or feedback path may intentionally use a shared corridor, while unrelated edges must not be disguised as one group.

## Diagram treatment

Declare one treatment per generated diagram in both the manifest entry and lock:

```yaml
diagram_treatment:
  renderer_family: sequence
  composition_rhythm: explanatory
  focal_item: failure-response
  emphasis: Failure response and retry ordering.
  boundary_style: Participants remain unboxed; subsystem ownership uses headers only.
  connector_style: Temporal messages with return and failure semantics kept distinct.
  hierarchy_strategy: Failure response is focal; normal calls are primary; returns and notes are supporting.
  spacing_strategy: Reserve a wider retry rail and keep phase boundaries clear at delivery size.
  differentiation_strategy: Use sequence-native lifelines and activation bars rather than component cards.
```

`renderer_family` must equal the diagram `type`. This prevents architecture, flow, state, sequence, ER, deployment, and other diagrams from being routed through one universal card renderer.

Use composition rhythms as follows:

- `focal`: emphasize a small topology, boundary, loop, or primary path.
- `dense`: show a fact-complete detail view that remains within the selected layout budget.
- `explanatory`: reserve space for guards, exception labels, cardinalities, or ordered messages.

`emphasis`, `boundary_style`, and `connector_style` are free descriptions. They are not fixed style enums. Contract v5 additionally requires `hierarchy_strategy`, `spacing_strategy`, and `differentiation_strategy`. `focal` and `explanatory` treatments also name a semantic `focal_item` on `layout_plan.primary_items`.

## Executable hierarchy and composition

For contract v5, every semantic SVG group carries `data-visual-tier`. The deterministic tier binding is:

- `focal`: the locked `focal_item`.
- `primary`: `layout_plan.primary_items` and `edge_roles.primary`.
- `control`: control edges plus guardrail and stop-condition roles.
- `context`: groups, lanes, and fragments.
- `secondary`: supporting, alternate, and data-object items.

The focal item must use the locked emphasis stroke or a semantic emphasis color and must not be visually identical to every peer. The composition gate measures the semantic content span and outer margins at the locked canvas. A treatment fails when a diagram claims focal, explanatory, or dense composition while leaving the content as a small strip or stranded island.

These rules bind intent to output without prescribing a fixed list of styles. The strategist still chooses the visual thesis from the reading question and topology; the validator only rejects unexecuted intent.

## Type-native rendering

Use separate construction logic for each renderer family. Share pack tokens, not generic node construction.

- Architecture/component: components, interfaces, datastores, and containment boundaries.
- Flow/swimlane: terminals, actions, decisions, merges, lanes, and loop rails.
- Sequence: participant headers, lifelines, activations, ordered messages, and returns.
- State: initial/final markers, states, guards, and transitions.
- ER: entities, field compartments, keys, relationships, and endpoint cardinalities.
- Deployment: environments, hosts, runtimes, artifacts, and network boundaries.
- Data/event flow: stores or topics must remain visibly different from ordinary processes.

Do not implement one `svg_node()` or card component that owns every technical role. Shared helpers may measure text, apply colors, or emit metadata; type renderers own geometry and composition.

## Per-diagram execution

Before generating each `visual.svg`:

1. Re-read the manifest `pack_identity`.
2. Re-read the diagram lock's technical contract and `diagram_treatment`.
3. Allocate the selected technical layout.
4. Render type-native notation.
5. Apply only the resolved shared tokens.

Set these attributes on the SVG root:

```xml
<svg data-pack-identity="precise-industrial"
     data-renderer-family="sequence"
     data-composition-rhythm="explanatory">
```

The visual gate verifies these attributes, actual stroke usage, and an actual geometry signature. Metadata alone never proves style or notation fidelity.

## Pack gate

The pack report records identity counts, treatment counts, actual geometry signatures, rounded-card ratios, and technical marker counts. A v4 pack fails when three or more distinct technical types collapse into the same rounded-card signature, unless a source-grounded `visual_diversity_reason` explains why type-native alternatives are factually unavailable.

Do not use the exception to justify a universal renderer or avoid technical notation.
