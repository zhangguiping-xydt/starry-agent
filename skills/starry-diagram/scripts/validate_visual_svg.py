from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import (
        canonical_svg_hash,
        colors_in_text,
        locked_colors,
        parse_svg,
        parse_viewbox,
        read_yaml,
        required_visual_labels,
        semantic_items,
        svg_semantic_elements,
        svg_text_content,
        write_json,
    )
    from notation import contract_version, validate_visual_notation
    from profiles import (
        enhancement_rank,
        layout_for,
        load_layouts,
        load_notations,
        load_profiles,
        profile_for,
    )
    from visual_geometry import analyze_visual_geometry
    from visual_identity import analyze_visual_identity
    from visual_legibility import analyze_visual_legibility
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import (
        canonical_svg_hash,
        colors_in_text,
        locked_colors,
        parse_svg,
        parse_viewbox,
        read_yaml,
        required_visual_labels,
        semantic_items,
        svg_semantic_elements,
        svg_text_content,
        write_json,
    )
    from notation import contract_version, validate_visual_notation
    from profiles import (
        enhancement_rank,
        layout_for,
        load_layouts,
        load_notations,
        load_profiles,
        profile_for,
    )
    from visual_geometry import analyze_visual_geometry
    from visual_identity import analyze_visual_identity
    from visual_legibility import analyze_visual_legibility


_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
_EDGE_LIKE_KINDS = {"edge", "message", "relationship", "transition"}
_GROUP_LIKE_KINDS = {"group", "lane"}


def _number(value: str | None) -> float | None:
    if not isinstance(value, str):
        return None
    match = _NUMBER_RE.fullmatch(value.strip().removesuffix("px"))
    if match is None:
        return None
    return float(match.group(0))


def _color_tokens(lock: dict[str, Any]) -> set[str]:
    return locked_colors(lock)


def _typography(lock: dict[str, Any]) -> Mapping[str, Any]:
    tokens = lock.get("style_tokens", {})
    typography = tokens.get("typography") if isinstance(tokens, Mapping) else None
    return typography if isinstance(typography, Mapping) else {}


def _validate_canvas(
    lock: dict[str, Any],
    root: Any,
    errors: list[str],
) -> dict[str, Any]:
    actual = parse_viewbox(root.attrib.get("viewBox"))
    if actual is None:
        errors.append("visual.svg viewBox must contain four positive-space numbers")
        return {"actual_viewBox": root.attrib.get("viewBox")}

    canvas = lock.get("canvas", {})
    mode = canvas.get("mode", "fixed") if isinstance(canvas, Mapping) else "fixed"
    result: dict[str, Any] = {"mode": mode, "actual_viewBox": list(actual)}
    if mode == "fixed" and isinstance(canvas, Mapping):
        width = canvas.get("width")
        height = canvas.get("height")
        expected = (0.0, 0.0, float(width), float(height)) if width and height else None
        result["expected_viewBox"] = list(expected) if expected else None
        if expected is not None and actual != expected:
            errors.append(
                "visual.svg viewBox does not match fixed canvas: "
                f"expected {expected}, got {actual}"
            )
    elif mode == "auto" and isinstance(canvas, Mapping):
        max_width = canvas.get("max_width")
        max_height = canvas.get("max_height")
        if isinstance(max_width, int) and actual[2] > max_width:
            errors.append(f"visual.svg width {actual[2]} exceeds canvas.max_width {max_width}")
        if isinstance(max_height, int) and actual[3] > max_height:
            errors.append(f"visual.svg height {actual[3]} exceeds canvas.max_height {max_height}")
    return result


def _validate_typography(
    lock: dict[str, Any],
    root: Any,
    errors: list[str],
) -> dict[str, Any]:
    typography = _typography(lock)
    minimum = typography.get("min_font_size")
    family = typography.get("font_family")
    seen_sizes: list[float] = []
    seen_families: set[str] = set()
    for element in root.iter():
        size = _number(element.attrib.get("font-size"))
        if size is not None:
            seen_sizes.append(size)
            if isinstance(minimum, int | float) and size < float(minimum):
                errors.append(
                    f"text font-size {size:g} is below style_tokens typography minimum {minimum}"
                )
        element_family = element.attrib.get("font-family")
        if element_family:
            seen_families.add(element_family)
            if isinstance(family, str) and family not in element_family:
                errors.append(
                    f"visual.svg uses font family outside style_tokens: {element_family}"
                )

    edge_label_minimum = typography.get("edge_label_size")
    if isinstance(edge_label_minimum, int | float):
        for element in root.iter():
            if _inferred_kind(element) not in _EDGE_LIKE_KINDS:
                continue
            for descendant in element.iter():
                if descendant.tag.rsplit("}", 1)[-1] != "text":
                    continue
                size = _number(descendant.attrib.get("font-size"))
                if size is not None and size < float(edge_label_minimum):
                    item_id = (
                        element.attrib.get("data-diagram-id")
                        or element.attrib.get("id")
                        or "<unknown>"
                    )
                    errors.append(
                        f"edge label {item_id} font-size {size:g} is below "
                        f"style_tokens typography edge_label_size {edge_label_minimum}"
                    )
    return {
        "minimum": min(seen_sizes) if seen_sizes else None,
        "families": sorted(seen_families),
    }


def _inferred_kind(element: Any) -> str | None:
    explicit = element.attrib.get("data-diagram-kind")
    if explicit:
        return explicit
    classes = set(element.attrib.get("class", "").split())
    if "node" in classes:
        return "node"
    if "edge" in classes:
        return "edge"
    if "cluster" in classes:
        return "group"
    return None


def _validate_semantic_identity(
    lock: dict[str, Any],
    root: Any,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    initial_error_count = len(errors)
    expected_items = semantic_items(lock)
    expected_ids = {item["id"] for item in expected_items}
    elements = svg_semantic_elements(root)
    missing: list[str] = []
    verified: list[str] = []

    semantic_id_counts = Counter(
        item_id
        for element in root.iter()
        if (
            item_id := element.attrib.get("data-diagram-id") or element.attrib.get("id")
        ) in expected_ids
    )
    duplicate_ids = sorted(
        item_id for item_id, count in semantic_id_counts.items() if count > 1
    )
    for item_id in duplicate_ids:
        errors.append(f"visual.svg contains duplicate semantic id: {item_id}")

    for item in expected_items:
        item_id = item["id"]
        kind = item["kind"]
        element = elements.get(item_id)
        if element is None:
            missing.append(item_id)
            errors.append(f"visual.svg missing semantic id: {item_id}")
            continue
        actual_kind = _inferred_kind(element)
        compatible_kinds = {kind}
        if kind in _EDGE_LIKE_KINDS:
            compatible_kinds.add("edge")
        if kind in _GROUP_LIKE_KINDS:
            compatible_kinds.add("group")
        if actual_kind is None:
            errors.append(f"semantic element {item_id} must declare data-diagram-kind")
        elif actual_kind not in compatible_kinds:
            errors.append(
                f"semantic element {item_id} has kind {actual_kind!r}, expected {kind!r}"
            )

        if kind in _EDGE_LIKE_KINDS:
            for endpoint in ("from", "to"):
                expected_endpoint = item.get(endpoint)
                actual_endpoint = element.attrib.get(f"data-{endpoint}")
                if expected_endpoint and actual_endpoint != expected_endpoint:
                    errors.append(
                        f"semantic element {item_id} data-{endpoint} must be "
                        f"{expected_endpoint!r}, got {actual_endpoint!r}"
                    )
        if kind in _GROUP_LIKE_KINDS:
            expected_record = next(
                (
                    value
                    for value in lock.get(item["section"], [])
                    if isinstance(value, Mapping) and value.get("id") == item_id
                ),
                None,
            )
            expected_members = set(expected_record.get("members", [])) if expected_record else set()
            member_text = element.attrib.get("data-members")
            actual_members = {
                member.strip() for member in member_text.split(",") if member.strip()
            } if member_text else set()
            if expected_members != actual_members:
                errors.append(
                    f"semantic element {item_id} data-members must equal "
                    f"{sorted(expected_members)}, got {sorted(actual_members)}"
                )
        verified.append(item_id)

    declared_ids = {
        element.attrib["data-diagram-id"]
        for element in root.iter()
        if element.attrib.get("data-diagram-id")
    }
    extra = sorted(declared_ids - expected_ids)
    for item_id in extra:
        errors.append(f"visual.svg introduces unlisted semantic id: {item_id}")

    legacy_ids = [
        item_id
        for item_id in verified
        if elements[item_id].attrib.get("data-diagram-id") is None
    ]
    if legacy_ids:
        warnings.append(
            "semantic identity inferred from SVG id/class; prefer explicit data-diagram-id metadata: "
            + ", ".join(sorted(legacy_ids))
        )
    return {
        "valid": len(errors) == initial_error_count,
        "expected": len(expected_items),
        "verified": len(verified),
        "missing": sorted(missing),
        "extra": extra,
        "duplicates": duplicate_ids,
    }


def _validate_visual_change(
    lock: dict[str, Any],
    visual_path: Path,
    semantic_path: Path | None,
    profiles_data: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    if semantic_path is None:
        return {"checked": False, "changed": None}
    if not semantic_path.exists():
        errors.append(f"semantic SVG not found: {semantic_path}")
        return {"checked": False, "changed": None}
    semantic_hash = canonical_svg_hash(semantic_path)
    visual_hash = canonical_svg_hash(visual_path)
    changed = semantic_hash != visual_hash
    visual_style = lock.get("visual_style", {})
    level = visual_style.get("enhancement_level") if isinstance(visual_style, Mapping) else None
    level_rank = enhancement_rank(level, profiles_data)
    medium_rank = enhancement_rank("medium", profiles_data)
    if not changed and level_rank is not None and medium_rank is not None:
        if level_rank >= medium_rank:
            errors.append(
                f"visual stage was a no-op for enhancement level {level}; "
                "semantic.svg and visual.svg have identical geometry"
            )
        else:
            warnings.append("light visual stage produced no geometric change")
    return {
        "checked": True,
        "changed": changed,
        "semantic_hash": semantic_hash,
        "visual_hash": visual_hash,
    }


def validate_visual(
    lock: dict[str, Any],
    svg_text: str,
    svg_path: Path,
    *,
    semantic_path: Path | None = None,
    profiles_data: dict[str, Any] | None = None,
    layouts_data: dict[str, Any] | None = None,
    notations_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    profiles_data = profiles_data or load_profiles()
    layouts_data = layouts_data or load_layouts()
    notations_data = notations_data or load_notations()

    try:
        root = parse_svg(svg_path)
    except Exception as exc:
        errors.append(str(exc))
        return {
            "status": "failed",
            "visual": {"errors": errors, "warnings": warnings},
        }

    profile = profile_for(lock.get("type"), profiles_data)
    if profile is None:
        errors.append(f"unknown diagram type: {lock.get('type')!r}")

    text_content = svg_text_content(root)
    for label in required_visual_labels(lock):
        if label not in text_content:
            errors.append(f"missing required visual label: {label}")

    allowed_colors = _color_tokens(lock)
    for color in sorted(colors_in_text(svg_text)):
        if color not in allowed_colors:
            errors.append(f"visual.svg uses color outside style_tokens: {color}")

    canvas_report = _validate_canvas(lock, root, errors)
    typography_report = _validate_typography(lock, root, errors)
    identity_report = _validate_semantic_identity(lock, root, errors, warnings)
    notation_report, notation_errors, notation_warnings = validate_visual_notation(
        lock,
        root,
        notations_data,
    )
    errors.extend(notation_errors)
    warnings.extend(notation_warnings)
    identity_style_report, identity_style_errors, identity_style_warnings = (
        analyze_visual_identity(lock, root)
    )
    errors.extend(identity_style_errors)
    warnings.extend(identity_style_warnings)
    change_report = _validate_visual_change(
        lock,
        svg_path,
        semantic_path,
        profiles_data,
        errors,
        warnings,
    )
    geometry_report: dict[str, Any] = {"checked": False}
    legibility_report: dict[str, Any] = {"checked": False}
    actual_viewbox = parse_viewbox(root.attrib.get("viewBox"))
    layout_plan = lock.get("layout_plan", {})
    pattern = layout_plan.get("pattern") if isinstance(layout_plan, Mapping) else None
    layout = layout_for(pattern, layouts_data)
    if actual_viewbox is not None and layout is not None:
        quality_limits = layout.get("quality_limits", {})
        if isinstance(quality_limits, Mapping):
            effective_limits = dict(quality_limits)
            if contract_version(lock) >= 5:
                route_economy = layouts_data.get("route_economy")
                if isinstance(route_economy, Mapping):
                    effective_limits["route_economy"] = dict(route_economy)
            visual_style = lock.get("visual_style", {})
            level = (
                visual_style.get("enhancement_level")
                if isinstance(visual_style, Mapping)
                else None
            )
            level_rank = enhancement_rank(level, profiles_data)
            medium_rank = enhancement_rank("medium", profiles_data)
            if (
                level_rank is not None
                and medium_rank is not None
                and level_rank < medium_rank
            ):
                effective_limits["min_analyzable_edge_fraction"] = 0.0
            geometry_report, geometry_errors, geometry_warnings = analyze_visual_geometry(
                root,
                actual_viewbox,
                effective_limits,
                edge_roles=(
                    layout_plan.get("edge_roles")
                    if isinstance(layout_plan, Mapping)
                    else None
                ),
                primary_items=(
                    layout_plan.get("primary_items")
                    if isinstance(layout_plan, Mapping)
                    else None
                ),
                allow_backward_detours=pattern
                in {"branching-flow", "loop-mechanism", "state-transition"},
            )
            geometry_report["checked"] = True
            geometry_report["pattern"] = pattern
            errors.extend(geometry_errors)
            warnings.extend(geometry_warnings)

    if actual_viewbox is not None:
        legibility_report, legibility_errors, legibility_warnings = analyze_visual_legibility(
            root,
            actual_viewbox,
            lock,
        )
        legibility_report["checked"] = True
        errors.extend(legibility_errors)
        warnings.extend(legibility_warnings)

    return {
        "status": "failed" if errors else "passed",
        "visual": {
            "errors": errors,
            "warnings": warnings,
            "canvas": canvas_report,
            "typography": typography_report,
            "semantic_identity": identity_report,
            "notation": notation_report,
            "visual_identity": identity_style_report,
            "visual_change": change_report,
            "geometry": geometry_report,
            "legibility": legibility_report,
        },
    }


def validate_visual_svg(
    lock_path: Path,
    svg_path: Path,
    *,
    semantic_path: Path | None = None,
    profiles_path: Path | None = None,
    layouts_path: Path | None = None,
    notations_path: Path | None = None,
) -> dict[str, Any]:
    lock = read_yaml(lock_path)
    svg_text = svg_path.read_text(encoding="utf-8")
    return validate_visual(
        lock,
        svg_text,
        svg_path,
        semantic_path=semantic_path,
        profiles_data=load_profiles(profiles_path),
        layouts_data=load_layouts(layouts_path),
        notations_data=load_notations(notations_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a starry diagram SVG against a lock file.")
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("svg_file", type=Path)
    parser.add_argument("--semantic-svg", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--layouts", type=Path)
    parser.add_argument("--notations", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_visual_svg(
        args.lock_file,
        args.svg_file,
        semantic_path=args.semantic_svg,
        profiles_path=args.profiles,
        layouts_path=args.layouts,
        notations_path=args.notations,
    )
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
