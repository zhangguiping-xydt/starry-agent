from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

try:
    from common import semantic_items, svg_semantic_elements
    from notation import contract_version
    from visual_geometry import _semantic_element_bbox
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import semantic_items, svg_semantic_elements
    from notation import contract_version
    from visual_geometry import _semantic_element_bbox


_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\Z")
_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
_COMPOSITION_RHYTHMS = {"focal", "dense", "explanatory"}
_LINECAPS = {"butt", "round", "square"}
_LINEJOINS = {"miter", "round", "bevel"}
_EDGE_KINDS = {"edge", "message", "relationship", "transition"}
_GROUP_KINDS = {"group", "lane"}
_BEHAVIOR_FIELDS = (
    "description",
    "shape_language",
    "whitespace_rhythm",
    "decoration",
    "elevation",
)
_TREATMENT_FIELDS = (
    "renderer_family",
    "composition_rhythm",
    "emphasis",
    "boundary_style",
    "connector_style",
)
_V5_TREATMENT_FIELDS = (
    "hierarchy_strategy",
    "spacing_strategy",
    "differentiation_strategy",
)
_STROKE_WIDTH_FIELDS = (
    "node_width",
    "boundary_width",
    "connector_width",
    "emphasis_width",
)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    match = _NUMBER_RE.fullmatch(value.strip().removesuffix("px"))
    return float(match.group(0)) if match else None


def _local_name(element: Any) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _descendants(element: Any, name: str) -> list[Any]:
    return [child for child in element.iter() if _local_name(child) == name]


def _mapping_equal(left: Any, right: Any) -> bool:
    return isinstance(left, Mapping) and isinstance(right, Mapping) and dict(left) == dict(right)


def validate_pack_identity(
    identity: Any,
    *,
    style_tokens: Any = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(identity, Mapping):
        return {"checked": True}, ["pack_identity must be a mapping for contract v4"], warnings

    identity_id = identity.get("id")
    if not _text(identity_id):
        errors.append("pack_identity.id must be a non-empty string")

    behavior = identity.get("visual_behavior")
    if not isinstance(behavior, Mapping):
        errors.append("pack_identity.visual_behavior must be a mapping")
        behavior = {}
    mode = behavior.get("mode")
    if mode not in {"preset", "custom"}:
        errors.append("pack_identity.visual_behavior.mode must be preset or custom")
    if mode == "preset" and not _text(behavior.get("preset_id")):
        errors.append("preset visual behavior requires visual_behavior.preset_id")
    for field in _BEHAVIOR_FIELDS:
        if not _text(behavior.get(field)):
            errors.append(f"pack_identity.visual_behavior.{field} must be non-empty")

    palette = identity.get("palette")
    if not isinstance(palette, Mapping):
        errors.append("pack_identity.palette must be a mapping")
        palette = {}
    for name in ("background", "surface", "primary", "accent", "text", "muted", "line"):
        color = palette.get(name)
        if not isinstance(color, str) or _HEX_COLOR_RE.fullmatch(color) is None:
            errors.append(f"pack_identity.palette.{name} must be a six-digit HEX color")

    typography = identity.get("typography")
    if not isinstance(typography, Mapping) or not typography:
        errors.append("pack_identity.typography must be a non-empty mapping")
        typography = {}

    strokes = identity.get("stroke_language")
    if not isinstance(strokes, Mapping):
        errors.append("pack_identity.stroke_language must be a mapping")
        strokes = {}
    for field in _STROKE_WIDTH_FIELDS:
        value = _number(strokes.get(field))
        if value is None or value <= 0:
            errors.append(f"pack_identity.stroke_language.{field} must be positive")
    if strokes.get("linecap") not in _LINECAPS:
        errors.append(f"pack_identity.stroke_language.linecap must be one of {sorted(_LINECAPS)}")
    if strokes.get("linejoin") not in _LINEJOINS:
        errors.append(
            f"pack_identity.stroke_language.linejoin must be one of {sorted(_LINEJOINS)}"
        )

    texture = identity.get("texture")
    if not isinstance(texture, Mapping):
        errors.append("pack_identity.texture must be a mapping")
        texture = {}
    if not _text(texture.get("mode")):
        errors.append("pack_identity.texture.mode must be a non-empty string")
    if not _text(texture.get("description")):
        errors.append("pack_identity.texture.description must be a non-empty string")

    if style_tokens is not None:
        if not isinstance(style_tokens, Mapping):
            errors.append("style_tokens must be a mapping")
        else:
            if not _mapping_equal(palette, style_tokens.get("colors")):
                errors.append("style_tokens.colors must exactly match pack_identity.palette")
            if not _mapping_equal(typography, style_tokens.get("typography")):
                errors.append(
                    "style_tokens.typography must exactly match pack_identity.typography"
                )
            if not _mapping_equal(strokes, style_tokens.get("strokes")):
                errors.append("style_tokens.strokes must exactly match pack_identity.stroke_language")
            connectors = style_tokens.get("connectors")
            if isinstance(connectors, Mapping):
                connector_width = _number(connectors.get("width"))
                locked_width = _number(strokes.get("connector_width"))
                if connector_width is not None and locked_width is not None:
                    if abs(connector_width - locked_width) > 1e-6:
                        errors.append(
                            "style_tokens.connectors.width must match "
                            "pack_identity.stroke_language.connector_width"
                        )

    return {
        "checked": True,
        "id": identity_id,
        "behavior_mode": mode,
        "preset_id": behavior.get("preset_id") if isinstance(behavior, Mapping) else None,
    }, errors, warnings


def validate_diagram_treatment(
    treatment: Any,
    diagram_type: Any,
    version: int = 4,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(treatment, Mapping):
        return {"checked": True}, ["diagram_treatment must be a mapping for contract v4"], warnings
    for field in _TREATMENT_FIELDS:
        if not _text(treatment.get(field)):
            errors.append(f"diagram_treatment.{field} must be a non-empty string")
    if treatment.get("composition_rhythm") not in _COMPOSITION_RHYTHMS:
        errors.append(
            "diagram_treatment.composition_rhythm must be one of "
            f"{sorted(_COMPOSITION_RHYTHMS)}"
        )
    if isinstance(diagram_type, str) and treatment.get("renderer_family") != diagram_type:
        errors.append(
            "diagram_treatment.renderer_family must equal the locked diagram type; "
            "do not route different technical types through one generic card renderer"
        )
    variation_reason = treatment.get("variation_reason")
    if variation_reason is not None and not _text(variation_reason):
        errors.append("diagram_treatment.variation_reason must be non-empty when provided")
    if version >= 5:
        for field in _V5_TREATMENT_FIELDS:
            if not _text(treatment.get(field)):
                errors.append(f"diagram_treatment.{field} must be non-empty for contract v5")
        rhythm = treatment.get("composition_rhythm")
        focal_item = treatment.get("focal_item")
        if rhythm in {"focal", "explanatory"} and not _text(focal_item):
            errors.append(
                "diagram_treatment.focal_item must name the visual anchor for "
                f"contract v5 {rhythm} compositions"
            )
        if focal_item is not None and not _text(focal_item):
            errors.append("diagram_treatment.focal_item must be non-empty when provided")
    return {
        "checked": True,
        "renderer_family": treatment.get("renderer_family"),
        "composition_rhythm": treatment.get("composition_rhythm"),
        "signature": treatment_signature(treatment),
        "focal_item": treatment.get("focal_item"),
    }, errors, warnings


def treatment_signature(treatment: Any) -> str | None:
    if not isinstance(treatment, Mapping):
        return None
    fields = list(_TREATMENT_FIELDS[1:])
    if any(field in treatment for field in _V5_TREATMENT_FIELDS):
        fields.extend(_V5_TREATMENT_FIELDS)
    values = [treatment.get(field) for field in fields]
    if not all(_text(value) for value in values):
        return None
    return "|".join(str(value).strip().casefold() for value in values)


def _expected_visual_tiers(lock: Mapping[str, Any]) -> dict[str, str]:
    layout_plan = lock.get("layout_plan", {})
    layout_plan = layout_plan if isinstance(layout_plan, Mapping) else {}
    treatment = lock.get("diagram_treatment", {})
    treatment = treatment if isinstance(treatment, Mapping) else {}
    primary = set(layout_plan.get("primary_items", []))
    edge_roles = layout_plan.get("edge_roles", {})
    edge_roles = edge_roles if isinstance(edge_roles, Mapping) else {}
    primary.update(edge_roles.get("primary", []))
    secondary = set(edge_roles.get("secondary", []))
    control = set(edge_roles.get("control", []))
    focal_item = treatment.get("focal_item")

    tiers: dict[str, str] = {}
    for item in semantic_items(dict(lock)):
        item_id = item["id"]
        role = item.get("notation_role")
        if item_id == focal_item:
            tier = "focal"
        elif item_id in control or role in {"guardrail", "stop-condition"}:
            tier = "control"
        elif item_id in primary:
            tier = "primary"
        elif item_id in secondary or role == "data-object":
            tier = "secondary"
        elif item["kind"] in _GROUP_KINDS or item["kind"] == "fragment":
            tier = "context"
        else:
            tier = "secondary"
        tiers[item_id] = tier
    return tiers


def _visible_style_signature(element: Any) -> tuple[str, str, float] | None:
    for child in element.iter():
        if _local_name(child) not in {
            "rect",
            "circle",
            "ellipse",
            "polygon",
            "path",
            "line",
            "polyline",
        }:
            continue
        fill = child.attrib.get("fill", "none").upper()
        stroke = child.attrib.get("stroke", "none").upper()
        width = _number(child.attrib.get("stroke-width")) or 1.0
        if fill != "NONE" or stroke != "NONE":
            return fill, stroke, round(width, 3)
    return None


def _is_emphasized(
    element: Any,
    identity: Mapping[str, Any],
) -> bool:
    strokes = identity.get("stroke_language", {})
    strokes = strokes if isinstance(strokes, Mapping) else {}
    emphasis_width = _number(strokes.get("emphasis_width"))
    palette = identity.get("palette", {})
    palette = palette if isinstance(palette, Mapping) else {}
    emphasis_fill_colors = {
        str(palette[name]).upper()
        for name in ("primary", "accent", "success", "warning", "danger")
        if isinstance(palette.get(name), str)
    }
    emphasis_stroke_colors = {
        str(palette[name]).upper()
        for name in ("accent", "success", "warning", "danger")
        if isinstance(palette.get(name), str)
    }
    for child in element.iter():
        if _local_name(child) not in {
            "rect",
            "circle",
            "ellipse",
            "polygon",
            "path",
            "line",
            "polyline",
        }:
            continue
        width = _number(child.attrib.get("stroke-width")) or 1.0
        fill = child.attrib.get("fill", "none").upper()
        stroke = child.attrib.get("stroke", "none").upper()
        if emphasis_width is not None and abs(width - emphasis_width) <= 1e-6:
            return True
        if fill != "NONE" and fill in emphasis_fill_colors:
            return True
        if stroke in emphasis_stroke_colors:
            return True
    return False


def _analyze_v5_composition(
    lock: Mapping[str, Any],
    root: Any,
    elements: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    viewbox = root.attrib.get("viewBox", "").replace(",", " ").split()
    try:
        left, top, width, height = [float(value) for value in viewbox]
    except (TypeError, ValueError):
        return {"checked": False}
    if width <= 0 or height <= 0:
        return {"checked": False}

    boxes: list[tuple[float, float, float, float]] = []
    for item in semantic_items(dict(lock)):
        if item["kind"] in _EDGE_KINDS or item["kind"] in _GROUP_KINDS:
            continue
        element = elements.get(item["id"])
        box = _semantic_element_bbox(element) if element is not None else None
        if box is not None:
            boxes.append(box)
    if not boxes:
        errors.append("contract v5 visual composition has no analyzable semantic geometry")
        return {"checked": True, "analyzable_items": 0}

    content = (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )
    width_fraction = (content[2] - content[0]) / width
    height_fraction = (content[3] - content[1]) / height
    margins = {
        "left": max(0.0, (content[0] - left) / width),
        "right": max(0.0, (left + width - content[2]) / width),
        "top": max(0.0, (content[1] - top) / height),
        "bottom": max(0.0, (top + height - content[3]) / height),
    }
    rhythm = str(lock.get("diagram_treatment", {}).get("composition_rhythm", ""))
    minimums = {
        "focal": (0.58, 0.28),
        "explanatory": (0.68, 0.48),
        "dense": (0.76, 0.62),
    }
    min_width, min_height = minimums.get(rhythm, (0.58, 0.28))
    if width_fraction + 1e-6 < min_width:
        errors.append(
            f"contract v5 {rhythm} composition uses {width_fraction:.0%} of canvas width; "
            f"minimum is {min_width:.0%}"
        )
    if height_fraction + 1e-6 < min_height:
        errors.append(
            f"contract v5 {rhythm} composition uses {height_fraction:.0%} of canvas height; "
            f"minimum is {min_height:.0%}"
        )
    margin_limits = {
        "left": 0.22,
        "right": 0.22,
        "top": 0.38,
        "bottom": 0.22,
    }
    for side, limit in margin_limits.items():
        if margins[side] > limit:
            errors.append(
                f"contract v5 composition leaves {margins[side]:.0%} {side} margin; "
                f"maximum is {limit:.0%}"
            )
    return {
        "checked": True,
        "analyzable_items": len(boxes),
        "content_bounds": [round(value, 2) for value in content],
        "width_fraction": round(width_fraction, 4),
        "height_fraction": round(height_fraction, 4),
        "margins": {name: round(value, 4) for name, value in margins.items()},
    }


def _is_diamond(element: Any) -> bool:
    for polygon in _descendants(element, "polygon"):
        values = [float(value) for value in _NUMBER_RE.findall(polygon.attrib.get("points", ""))]
        if len(values) == 8:
            points = list(zip(values[0::2], values[1::2]))
            if len({point[0] for point in points}) >= 3 and len(
                {point[1] for point in points}
            ) >= 3:
                return True
    return any("rotate" in rect.attrib.get("transform", "") for rect in _descendants(element, "rect"))


def _has_lifeline(element: Any) -> bool:
    if not _descendants(element, "rect"):
        return False
    for line in _descendants(element, "line"):
        x1 = _number(line.attrib.get("x1"))
        x2 = _number(line.attrib.get("x2"))
        y1 = _number(line.attrib.get("y1"))
        y2 = _number(line.attrib.get("y2"))
        if None not in {x1, x2, y1, y2} and abs(float(x1) - float(x2)) <= 1:
            if abs(float(y2) - float(y1)) >= 20:
                return True
    return False


def _shape_for(element: Any, role: str | None) -> str:
    if _has_lifeline(element):
        return "lifeline"
    if _is_diamond(element):
        return "diamond"
    circles = _descendants(element, "circle") + _descendants(element, "ellipse")
    rects = _descendants(element, "rect")
    lines = _descendants(element, "line")
    paths = _descendants(element, "path")
    if role == "datastore" and circles and (rects or paths):
        return "datastore"
    if role == "entity" and rects and (lines or paths):
        return "entity"
    if circles:
        return "circle"
    if rects:
        rounded = False
        for rect in rects:
            width = _number(rect.attrib.get("width"))
            height = _number(rect.attrib.get("height"))
            radius = _number(rect.attrib.get("rx")) or 0.0
            if width and height and radius >= min(width, height) * 0.15:
                rounded = True
                break
        return "rounded-rect" if rounded else "rect"
    if paths:
        return "path"
    if lines:
        return "line"
    return "unknown"


def _edge_mode(element: Any) -> str:
    modes: set[str] = set()
    for path in _descendants(element, "path"):
        data = path.attrib.get("d", "")
        if re.search(r"[CQSAcqsa]", data):
            modes.add("curved")
        elif re.search(r"[HVhv]", data):
            modes.add("orthogonal")
        elif re.search(r"[Ll]", data):
            modes.add("straight")
    for line in _descendants(element, "line"):
        x1 = _number(line.attrib.get("x1"))
        x2 = _number(line.attrib.get("x2"))
        y1 = _number(line.attrib.get("y1"))
        y2 = _number(line.attrib.get("y2"))
        if None not in {x1, x2, y1, y2}:
            if abs(float(x1) - float(x2)) <= 1 or abs(float(y1) - float(y2)) <= 1:
                modes.add("orthogonal")
            else:
                modes.add("straight")
    if not modes:
        return "unknown"
    return next(iter(modes)) if len(modes) == 1 else "mixed"


def _dominant(values: list[str]) -> str:
    if not values:
        return "none"
    counts = Counter(values)
    name, count = counts.most_common(1)[0]
    return name if count / len(values) >= 0.75 else "mixed"


def _validate_stroke_language(
    root: Any,
    identity: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    strokes = identity.get("stroke_language", {})
    if not isinstance(strokes, Mapping):
        return {"checked": False}
    allowed_widths = {
        round(value, 6)
        for field in _STROKE_WIDTH_FIELDS
        if (value := _number(strokes.get(field))) is not None
    }
    expected_cap = strokes.get("linecap")
    expected_join = strokes.get("linejoin")
    seen_widths: set[float] = set()
    invalid_widths: set[float] = set()
    invalid_caps: set[str] = set()
    invalid_joins: set[str] = set()
    checked_elements: set[int] = set()
    semantic_elements = svg_semantic_elements(root)
    for semantic in semantic_elements.values():
        for element in semantic.iter():
            if id(element) in checked_elements:
                continue
            checked_elements.add(id(element))
            if _local_name(element) not in {"line", "path", "rect", "circle", "ellipse", "polygon", "polyline"}:
                continue
            stroke = element.attrib.get("stroke")
            if stroke is None or stroke.strip().casefold() == "none":
                continue
            width = _number(element.attrib.get("stroke-width"))
            actual_width = 1.0 if width is None else width
            seen_widths.add(round(actual_width, 6))
            if allowed_widths and round(actual_width, 6) not in allowed_widths:
                invalid_widths.add(round(actual_width, 6))
            if _local_name(element) in {"line", "path", "polygon", "polyline"}:
                actual_cap = element.attrib.get("stroke-linecap", "butt")
                actual_join = element.attrib.get("stroke-linejoin", "miter")
                if expected_cap and actual_cap != expected_cap:
                    invalid_caps.add(actual_cap)
                if expected_join and actual_join != expected_join:
                    invalid_joins.add(actual_join)
    for width in sorted(invalid_widths):
        errors.append(
            f"visual.svg stroke-width {width:g} is outside pack_identity.stroke_language"
        )
    for cap in sorted(invalid_caps):
        errors.append(
            f"visual.svg stroke-linecap {cap!r} does not match {expected_cap!r}"
        )
    for join in sorted(invalid_joins):
        errors.append(
            f"visual.svg stroke-linejoin {join!r} does not match {expected_join!r}"
        )
    return {"checked": True, "seen_widths": sorted(seen_widths)}


def analyze_visual_identity(
    lock: Mapping[str, Any],
    root: Any,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    version = contract_version(lock)
    if version < 4:
        return {"checked": False, "contract_version": version}, errors, warnings

    identity = lock.get("pack_identity")
    treatment = lock.get("diagram_treatment")
    if not isinstance(identity, Mapping) or not isinstance(treatment, Mapping):
        return {"checked": True, "contract_version": version}, errors, warnings

    metadata_expectations = {
        "data-pack-identity": identity.get("id"),
        "data-renderer-family": treatment.get("renderer_family"),
        "data-composition-rhythm": treatment.get("composition_rhythm"),
    }
    for attribute, expected in metadata_expectations.items():
        actual = root.attrib.get(attribute)
        if actual != expected:
            errors.append(f"visual.svg {attribute} must be {expected!r}, got {actual!r}")

    stroke_report = _validate_stroke_language(root, identity, errors)
    elements = svg_semantic_elements(root)
    node_shapes: list[str] = []
    boundary_shapes: list[str] = []
    connector_modes: list[str] = []
    role_shapes: Counter[str] = Counter()
    for item in semantic_items(dict(lock)):
        element = elements.get(item["id"])
        if element is None:
            continue
        role = item.get("notation_role")
        if item["kind"] in _EDGE_KINDS:
            connector_modes.append(_edge_mode(element))
        elif item["kind"] in _GROUP_KINDS:
            boundary_shapes.append(_shape_for(element, role))
        else:
            shape = _shape_for(element, role)
            node_shapes.append(shape)
            role_shapes[f"{role or 'untyped'}:{shape}"] += 1

    dominant_shape = _dominant(node_shapes)
    boundary_shape = _dominant(boundary_shapes)
    connector_mode = _dominant(connector_modes)
    rounded_count = sum(shape == "rounded-rect" for shape in node_shapes)
    rounded_ratio = rounded_count / len(node_shapes) if node_shapes else 0.0
    technical_markers = sum(
        shape in {"diamond", "circle", "lifeline", "datastore", "entity"}
        for shape in node_shapes
    )
    rhythm = str(treatment.get("composition_rhythm", "unknown"))
    signature = "|".join((dominant_shape, boundary_shape, connector_mode, rhythm))
    tier_report: dict[str, Any] = {"checked": False}
    composition_report: dict[str, Any] = {"checked": False}
    if version >= 5:
        expected_tiers = _expected_visual_tiers(lock)
        semantic_by_id = {
            item["id"]: item for item in semantic_items(dict(lock))
        }
        tier_counts: Counter[str] = Counter()
        style_signatures: dict[str, tuple[str, str, float] | None] = {}
        for item_id, expected_tier in expected_tiers.items():
            element = elements.get(item_id)
            if element is None:
                continue
            actual_tier = element.attrib.get("data-visual-tier")
            if actual_tier != expected_tier:
                errors.append(
                    f"semantic element {item_id} data-visual-tier must be "
                    f"{expected_tier!r}, got {actual_tier!r}"
                )
            tier_counts[str(actual_tier)] += 1
            style_signatures[item_id] = _visible_style_signature(element)

        focal_item = treatment.get("focal_item")
        if isinstance(focal_item, str) and focal_item:
            focal_element = elements.get(focal_item)
            if focal_element is not None and not _is_emphasized(focal_element, identity):
                errors.append(
                    f"diagram_treatment.focal_item {focal_item!r} must use the locked "
                    "emphasis stroke or a semantic emphasis color"
                )
            focal_signature = style_signatures.get(focal_item)
            focal_kind = semantic_by_id.get(focal_item, {}).get("kind")
            peer_signatures = [
                style
                for item_id, style in style_signatures.items()
                if item_id != focal_item and expected_tiers.get(item_id) in {"primary", "secondary"}
                and semantic_by_id.get(item_id, {}).get("kind") == focal_kind
                and style is not None
            ]
            if focal_signature is not None and peer_signatures and all(
                style == focal_signature for style in peer_signatures
            ):
                errors.append(
                    f"diagram_treatment.focal_item {focal_item!r} is visually identical "
                    "to every primary/supporting item"
                )
        tier_report = {
            "checked": True,
            "expected": dict(sorted(expected_tiers.items())),
            "counts": dict(sorted(tier_counts.items())),
            "focal_item": focal_item,
        }
        composition_report = _analyze_v5_composition(lock, root, elements, errors)
        if composition_report.get("checked"):
            width_bucket = round(float(composition_report.get("width_fraction", 0)) * 4) / 4
            height_bucket = round(float(composition_report.get("height_fraction", 0)) * 4) / 4
            signature = "|".join(
                (
                    signature,
                    f"span:{width_bucket:.2f}x{height_bucket:.2f}",
                    f"tiers:{','.join(sorted(tier_counts))}",
                )
            )
    return {
        "checked": True,
        "contract_version": version,
        "pack_identity": identity.get("id"),
        "renderer_family": treatment.get("renderer_family"),
        "composition_rhythm": rhythm,
        "shape_counts": dict(sorted(Counter(node_shapes).items())),
        "boundary_shape_counts": dict(sorted(Counter(boundary_shapes).items())),
        "connector_mode_counts": dict(sorted(Counter(connector_modes).items())),
        "role_shapes": dict(sorted(role_shapes.items())),
        "rounded_semantic_ratio": round(rounded_ratio, 4),
        "technical_marker_count": technical_markers,
        "card_like": rounded_ratio >= 0.75 and technical_markers == 0,
        "signature": signature,
        "stroke_language": stroke_report,
        "visual_hierarchy": tier_report,
        "composition": composition_report,
    }, errors, warnings
