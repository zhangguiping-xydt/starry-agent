from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from typing import Any

try:
    from visual_geometry import (
        _bbox_for_element,
        _local_name,
        _semantic_element_bbox,
        _semantic_element_geometry,
    )
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from visual_geometry import (
        _bbox_for_element,
        _local_name,
        _semantic_element_bbox,
        _semantic_element_geometry,
    )


_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{6})$")
_NODE_KINDS = {"node", "participant", "entity", "state"}
_CONTAINER_KINDS = {"group", "lane"}
_EDGE_KINDS = {"edge", "message", "relationship", "transition"}
_TEXT_ROLE_TOKENS = {
    "diagram-title": "diagram_title_size",
    "group-title": "group_title_size",
    "node-title": "node_title_size",
    "node-body": "node_body_size",
    "edge-label": "edge_label_size",
    "annotation": "annotation_size",
}

BBox = tuple[float, float, float, float]
Point = tuple[float, float]


def _number(value: str | None) -> float | None:
    if not isinstance(value, str):
        return None
    match = _NUMBER_RE.fullmatch(value.strip().removesuffix("px"))
    return float(match.group(0)) if match else None


def _first_number(value: str | None) -> float | None:
    if not isinstance(value, str):
        return None
    match = _NUMBER_RE.search(value)
    return float(match.group(0)) if match else None


def _style_value(element: Any, name: str) -> str | None:
    direct = element.attrib.get(name)
    if direct is not None:
        return direct
    style = element.attrib.get("style", "")
    for declaration in style.split(";"):
        key, separator, value = declaration.partition(":")
        if separator and key.strip() == name:
            return value.strip()
    return None


def _inherited_value(element: Any, name: str, parents: Mapping[Any, Any]) -> str | None:
    current = element
    while current is not None:
        value = _style_value(current, name)
        if value is not None:
            return value
        current = parents.get(current)
    return None


def _semantic_owner(element: Any, parents: Mapping[Any, Any]) -> Any | None:
    current = element
    while current is not None:
        if current.attrib.get("data-diagram-id") and current.attrib.get("data-diagram-kind"):
            return current
        current = parents.get(current)
    return None


def _character_width_factor(character: str) -> float:
    if character.isspace():
        return 0.33
    if unicodedata.east_asian_width(character) in {"W", "F"}:
        return 1.0
    category = unicodedata.category(character)
    if category.startswith("P"):
        return 0.42
    if character.isupper():
        return 0.66
    if character.islower() or character.isdigit():
        return 0.56
    return 0.64


def _estimated_text_width(text: str, font_size: float) -> float:
    return sum(_character_width_factor(character) for character in text) * font_size


def _text_bbox(
    text: str,
    x: float,
    y: float,
    font_size: float,
    anchor: str,
    baseline: str | None,
) -> BBox:
    width = _estimated_text_width(text, font_size)
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width
    else:
        left = x

    if baseline in {"middle", "central"}:
        top = y - font_size / 2
    elif baseline in {"hanging", "text-before-edge"}:
        top = y
    else:
        top = y - font_size * 0.8
    return left, top, left + width, top + font_size


def _visible_text(value: str) -> str:
    return " ".join(value.split())


def _text_fragments(root: Any, parents: Mapping[Any, Any]) -> tuple[list[dict[str, Any]], int]:
    fragments: list[dict[str, Any]] = []
    unmeasurable = 0
    for text_element in root.iter():
        if _local_name(text_element.tag) != "text":
            continue
        owner = _semantic_owner(text_element, parents)
        owner_id = owner.attrib.get("data-diagram-id") if owner is not None else None
        owner_kind = owner.attrib.get("data-diagram-kind") if owner is not None else None
        role = _inherited_value(text_element, "data-text-role", parents)
        anchor = _inherited_value(text_element, "text-anchor", parents) or "start"
        baseline = _inherited_value(text_element, "dominant-baseline", parents)
        base_x = _first_number(_inherited_value(text_element, "x", parents))
        base_y = _first_number(_inherited_value(text_element, "y", parents))
        tspans = [child for child in text_element if _local_name(child.tag) == "tspan"]
        candidates = tspans or [text_element]
        cursor_x = base_x
        cursor_y = base_y

        for candidate in candidates:
            label = _visible_text("".join(candidate.itertext()))
            if not label:
                continue
            if candidate is not text_element:
                x_value = _first_number(candidate.attrib.get("x"))
                y_value = _first_number(candidate.attrib.get("y"))
                dx = _first_number(candidate.attrib.get("dx")) or 0.0
                dy = _first_number(candidate.attrib.get("dy")) or 0.0
                cursor_x = x_value if x_value is not None else cursor_x
                cursor_y = y_value if y_value is not None else cursor_y
                if cursor_x is not None:
                    cursor_x += dx
                if cursor_y is not None:
                    cursor_y += dy
            font_size = _number(_inherited_value(candidate, "font-size", parents))
            x = cursor_x
            y = cursor_y
            transformed = any(
                current.attrib.get("transform")
                for current in (candidate, text_element, owner)
                if current is not None
            )
            if font_size is None or x is None or y is None or transformed:
                unmeasurable += 1
                fragments.append(
                    {
                        "text": label,
                        "role": role,
                        "font_size": font_size,
                        "owner_id": owner_id,
                        "owner_kind": owner_kind,
                        "fill": _inherited_value(candidate, "fill", parents),
                        "bbox": None,
                    }
                )
                continue
            box = _text_bbox(label, x, y, font_size, anchor, baseline)
            fragments.append(
                {
                    "text": label,
                    "role": role,
                    "font_size": font_size,
                    "owner_id": owner_id,
                    "owner_kind": owner_kind,
                    "fill": _inherited_value(candidate, "fill", parents),
                    "bbox": box,
                }
            )
            cursor_x = box[2]
    return fragments, unmeasurable


def _box_area(box: BBox) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _contains(outer: BBox, inner: BBox, padding: float = 0.0) -> bool:
    return (
        inner[0] >= outer[0] + padding
        and inner[1] >= outer[1] + padding
        and inner[2] <= outer[2] - padding
        and inner[3] <= outer[3] - padding
    )


def _overlap(first: BBox, second: BBox, tolerance: float = 0.0) -> bool:
    return (
        min(first[2], second[2]) - max(first[0], second[0]) > tolerance
        and min(first[3], second[3]) - max(first[1], second[1]) > tolerance
    )


def _point_segment_distance(point: Point, first: Point, second: Point) -> float:
    dx = second[0] - first[0]
    dy = second[1] - first[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return math.hypot(point[0] - first[0], point[1] - first[1])
    ratio = ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / (dx * dx + dy * dy)
    ratio = max(0.0, min(1.0, ratio))
    projection = (first[0] + ratio * dx, first[1] + ratio * dy)
    return math.hypot(point[0] - projection[0], point[1] - projection[1])


def _delivery_scale(lock: Mapping[str, Any], viewbox: BBox) -> float:
    target = lock.get("delivery_target", {})
    if not isinstance(target, Mapping):
        return 1.0
    width = target.get("width_px")
    height = target.get("height_px")
    scales: list[float] = []
    if isinstance(width, int | float) and width > 0:
        scales.append(float(width) / viewbox[2])
    if isinstance(height, int | float) and height > 0:
        scales.append(float(height) / viewbox[3])
    return min(scales) if scales else 1.0


def _rgb(color: str | None) -> tuple[float, float, float] | None:
    match = _HEX_COLOR_RE.fullmatch(color or "")
    if match is None:
        return None
    value = match.group(1)
    return tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(value) for value in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground: str | None, background: str | None) -> float | None:
    foreground_rgb = _rgb(foreground)
    background_rgb = _rgb(background)
    if foreground_rgb is None or background_rgb is None:
        return None
    first = _luminance(foreground_rgb)
    second = _luminance(background_rgb)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _background_for_fragment(
    fragment: Mapping[str, Any],
    owners: Mapping[str, Any],
    fallback: str | None,
) -> str | None:
    owner_id = fragment.get("owner_id")
    box = fragment.get("bbox")
    if not isinstance(owner_id, str) or not isinstance(box, tuple):
        return fallback
    owner = owners.get(owner_id)
    if owner is None:
        return fallback
    center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    candidates: list[tuple[float, str]] = []
    for element in owner.iter():
        shape_box = _bbox_for_element(element)
        fill = _style_value(element, "fill")
        if shape_box is None or not fill or fill == "none":
            continue
        if shape_box[0] <= center[0] <= shape_box[2] and shape_box[1] <= center[1] <= shape_box[3]:
            candidates.append((_box_area(shape_box), fill))
    return min(candidates)[1] if candidates else fallback


def analyze_visual_legibility(
    root: Any,
    viewbox: BBox,
    lock: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    parents = {child: parent for parent in root.iter() for child in parent}
    fragments, unmeasurable = _text_fragments(root, parents)
    target = lock.get("delivery_target", {})
    target = target if isinstance(target, Mapping) else {}
    typography = lock.get("style_tokens", {})
    typography = typography.get("typography", {}) if isinstance(typography, Mapping) else {}
    typography = typography if isinstance(typography, Mapping) else {}
    colors = lock.get("style_tokens", {})
    colors = colors.get("colors", {}) if isinstance(colors, Mapping) else {}
    colors = colors if isinstance(colors, Mapping) else {}
    scale = _delivery_scale(lock, viewbox)
    minimum_effective = float(target.get("min_effective_font_px", 0) or 0)
    minimum_contrast = float(target.get("min_contrast_ratio", 0) or 0)
    minimum_padding = float(target.get("min_text_padding_px", 0) or 0) / scale
    max_label_distance = float(target.get("max_edge_label_distance_px", 0) or 0) / scale
    max_unmeasurable = float(target.get("max_unmeasurable_text_fraction", 0) or 0)

    role_counts: Counter[str] = Counter()
    effective_sizes: list[float] = []
    for fragment in fragments:
        role = fragment.get("role")
        label = fragment["text"]
        size = fragment.get("font_size")
        if role not in _TEXT_ROLE_TOKENS:
            errors.append(f"text {label!r} must declare a supported data-text-role")
            continue
        role_counts[str(role)] += 1
        expected = typography.get(_TEXT_ROLE_TOKENS[str(role)])
        if isinstance(size, int | float) and isinstance(expected, int | float):
            if not math.isclose(float(size), float(expected), abs_tol=0.05):
                errors.append(
                    f"text {label!r} role {role} uses font-size {float(size):g}; "
                    f"locked size is {float(expected):g}"
                )
            effective = float(size) * scale
            effective_sizes.append(effective)
            if minimum_effective and effective + 1e-6 < minimum_effective:
                errors.append(
                    f"text {label!r} effective font-size {effective:.2f}px is below "
                    f"delivery target minimum {minimum_effective:g}px"
                )

    measurable = [fragment for fragment in fragments if isinstance(fragment.get("bbox"), tuple)]
    unmeasurable_fraction = unmeasurable / len(fragments) if fragments else 0.0
    if unmeasurable_fraction > max_unmeasurable:
        errors.append(
            f"visual legibility measures {1 - unmeasurable_fraction:.0%} of text, below required "
            f"{1 - max_unmeasurable:.0%}; flatten transforms and use explicit x/y/font-size"
        )
    elif unmeasurable:
        warnings.append(f"visual legibility skipped {unmeasurable} unmeasurable text fragment(s)")

    owners = {
        element.attrib["data-diagram-id"]: element
        for element in root.iter()
        if element.attrib.get("data-diagram-id") and element.attrib.get("data-diagram-kind")
    }
    owner_boxes = {
        item_id: box
        for item_id, owner in owners.items()
        if owner.attrib.get("data-diagram-kind") in _NODE_KINDS | _CONTAINER_KINDS
        if (box := _semantic_element_bbox(owner)) is not None
    }
    node_boxes = {
        item_id: box
        for item_id, box in owner_boxes.items()
        if owners[item_id].attrib.get("data-diagram-kind") in _NODE_KINDS
    }

    overflows: list[dict[str, str]] = []
    for fragment in measurable:
        owner_id = fragment.get("owner_id")
        owner_kind = fragment.get("owner_kind")
        if owner_kind not in _NODE_KINDS | _CONTAINER_KINDS or owner_id not in owner_boxes:
            continue
        if not _contains(owner_boxes[str(owner_id)], fragment["bbox"], minimum_padding):
            overflows.append({"text": fragment["text"], "owner": str(owner_id)})
    if overflows:
        errors.append(
            f"visual text has {len(overflows)} containment or padding violation(s); "
            "expand the owning geometry and reflow the layout"
        )

    tolerance = 0.75 / scale
    text_overlaps: list[dict[str, str]] = []
    for index, first in enumerate(measurable):
        for second in measurable[index + 1 :]:
            if _overlap(first["bbox"], second["bbox"], tolerance):
                text_overlaps.append({"first": first["text"], "second": second["text"]})
    if text_overlaps:
        errors.append(f"visual text has {len(text_overlaps)} overlap(s)")

    node_overlaps: list[dict[str, str]] = []
    node_ids = sorted(node_boxes)
    for index, first_id in enumerate(node_ids):
        for second_id in node_ids[index + 1 :]:
            if _overlap(node_boxes[first_id], node_boxes[second_id], tolerance):
                node_overlaps.append({"first": first_id, "second": second_id})
    if node_overlaps:
        errors.append(f"visual geometry has {len(node_overlaps)} node overlap(s)")

    canvas_box = (viewbox[0], viewbox[1], viewbox[0] + viewbox[2], viewbox[1] + viewbox[3])
    out_of_bounds = [
        item_id for item_id, box in node_boxes.items() if not _contains(canvas_box, box)
    ]
    if out_of_bounds:
        errors.append(f"visual nodes fall outside the canvas: {sorted(out_of_bounds)}")

    label_node_overlaps: list[dict[str, str]] = []
    unanchored_labels: list[dict[str, Any]] = []
    for fragment in measurable:
        if fragment.get("role") != "edge-label":
            continue
        owner_id = fragment.get("owner_id")
        owner = owners.get(str(owner_id))
        if owner is None or owner.attrib.get("data-diagram-kind") not in _EDGE_KINDS:
            errors.append(
                f"edge label {fragment['text']!r} must belong to an edge-like semantic group"
            )
            continue
        for node_id, box in node_boxes.items():
            if _overlap(fragment["bbox"], box, tolerance):
                label_node_overlaps.append({"label": fragment["text"], "node": node_id})
        segments, supported = _semantic_element_geometry(owner)
        if not supported or not segments:
            unanchored_labels.append({"label": fragment["text"], "distance_px": None})
            continue
        center = (
            (fragment["bbox"][0] + fragment["bbox"][2]) / 2,
            (fragment["bbox"][1] + fragment["bbox"][3]) / 2,
        )
        distance = min(_point_segment_distance(center, first, second) for first, second in segments)
        if max_label_distance and distance > max_label_distance:
            unanchored_labels.append(
                {"label": fragment["text"], "distance_px": round(distance * scale, 2)}
            )
    if label_node_overlaps:
        errors.append(f"edge labels overlap {len(label_node_overlaps)} node(s)")
    if unanchored_labels:
        errors.append(
            f"visual has {len(unanchored_labels)} edge label(s) without an unambiguous route anchor"
        )

    contrast_failures: list[dict[str, Any]] = []
    contrast_unmeasurable: list[str] = []
    fallback_background = (
        colors.get("background") if isinstance(colors.get("background"), str) else None
    )
    for fragment in measurable:
        background = _background_for_fragment(fragment, owners, fallback_background)
        ratio = _contrast_ratio(fragment.get("fill"), background)
        if ratio is None:
            contrast_unmeasurable.append(fragment["text"])
        elif minimum_contrast and ratio + 1e-6 < minimum_contrast:
            contrast_failures.append(
                {"text": fragment["text"], "ratio": round(ratio, 2), "background": background}
            )
    if contrast_unmeasurable:
        errors.append(
            f"visual text has {len(contrast_unmeasurable)} unmeasurable contrast case(s); "
            "use explicit locked hex fills on solid token backgrounds"
        )
    if contrast_failures:
        errors.append(
            f"visual text has {len(contrast_failures)} contrast failure(s) below "
            f"{minimum_contrast:g}:1"
        )

    report = {
        "delivery_scale": round(scale, 4),
        "target": dict(target),
        "text": {
            "fragments": len(fragments),
            "measurable": len(measurable),
            "unmeasurable_fraction": round(unmeasurable_fraction, 4),
            "roles": dict(sorted(role_counts.items())),
            "minimum_effective_font_px": round(min(effective_sizes), 2)
            if effective_sizes
            else None,
            "overflows": overflows,
            "overlaps": text_overlaps,
            "contrast_failures": contrast_failures,
            "contrast_unmeasurable": contrast_unmeasurable,
        },
        "geometry": {
            "node_overlaps": node_overlaps,
            "nodes_out_of_bounds": sorted(out_of_bounds),
            "edge_label_node_overlaps": label_node_overlaps,
            "unanchored_edge_labels": unanchored_labels,
        },
    }
    return report, errors, warnings
