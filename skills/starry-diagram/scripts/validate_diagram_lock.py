from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import parse_viewbox, read_yaml, semantic_items, write_json
    from profiles import enhancement_rank, layout_for, load_layouts, load_profiles, profile_for
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import parse_viewbox, read_yaml, semantic_items, write_json
    from profiles import enhancement_rank, layout_for, load_layouts, load_profiles, profile_for


_REQUIRED_TOP_LEVEL_KEYS = (
    "id",
    "title",
    "type",
    "source_format",
    "visual_style",
    "layout_plan",
    "canvas",
    "delivery_target",
    "style_tokens",
)
_EDGE_KINDS = {"command", "event", "data", "projection", "call"}
_EDGE_LIKE_SEMANTIC_KINDS = {"edge", "message", "relationship", "transition"}
_CONTAINER_SEMANTIC_KINDS = {"group", "lane"}
_DENSITIES = {"sparse", "balanced", "dense"}
_VIEW_ROLES = {"standalone", "overview", "detail"}
_REGION_PLACEMENTS = {"top", "bottom", "left", "right", "center", "background", "lanes"}
_EDGE_ROLES = ("primary", "secondary", "control")
_TYPOGRAPHY_ROLES = (
    "diagram_title_size",
    "group_title_size",
    "node_title_size",
    "node_body_size",
    "edge_label_size",
    "annotation_size",
    "min_font_size",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _format_id(value: Any) -> str:
    return str(value) if value is not None else "<missing>"


def _validate_named_items(
    lock: dict[str, Any],
    section: str,
    errors: list[str],
    *,
    require_label: bool = True,
) -> set[str]:
    values = lock.get(section)
    known_ids: set[str] = set()
    if not isinstance(values, list):
        errors.append(f"{section} must be a list")
        return known_ids

    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            errors.append(f"{section} item at index {index} must be a mapping")
            continue
        item_id = value.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"{section} item at index {index} must have an id")
        elif item_id in known_ids:
            errors.append(f"duplicate {section} id: {item_id}")
        else:
            known_ids.add(item_id)
        if require_label:
            label = value.get("label")
            if not isinstance(label, str) or not label:
                errors.append(f"{section} {_format_id(item_id)} must have a label")
    return known_ids


def _validate_relations(
    lock: dict[str, Any],
    section: str,
    known_ids: set[str],
    errors: list[str],
    *,
    require_label: bool = True,
) -> set[str]:
    relation_ids = _validate_named_items(
        lock,
        section,
        errors,
        require_label=require_label,
    )
    values = lock.get(section, [])
    if not isinstance(values, list):
        return relation_ids
    for value in values:
        if not isinstance(value, Mapping):
            continue
        relation_id = _format_id(value.get("id"))
        for endpoint in ("from", "to"):
            endpoint_id = value.get(endpoint)
            if not isinstance(endpoint_id, str) or not endpoint_id:
                errors.append(f"{section} {relation_id} must have {endpoint}")
            elif endpoint_id not in known_ids:
                errors.append(
                    f"{section} {relation_id} references missing {endpoint} item {endpoint_id}"
                )
        kind = value.get("kind")
        if kind is not None and kind not in _EDGE_KINDS:
            errors.append(
                f"{section} {relation_id} kind must be one of {sorted(_EDGE_KINDS)}"
            )
    return relation_ids


def _validate_groups(
    lock: dict[str, Any],
    section: str,
    known_ids: set[str],
    errors: list[str],
) -> set[str]:
    group_ids = _validate_named_items(lock, section, errors)
    values = lock.get(section, [])
    if not isinstance(values, list):
        return group_ids
    memberships: list[str] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        group_id = _format_id(value.get("id"))
        members = value.get("members")
        if not isinstance(members, list) or not members:
            errors.append(f"{section} {group_id} must have a non-empty members list")
            continue
        for member in members:
            if not isinstance(member, str) or not member:
                errors.append(f"{section} {group_id} has an invalid member")
            elif member not in known_ids:
                errors.append(f"{section} {group_id} references missing member {member}")
            else:
                memberships.append(member)
    if section == "lanes":
        counts = Counter(memberships)
        duplicate_members = sorted(member for member, count in counts.items() if count > 1)
        if duplicate_members:
            errors.append(f"lane members must be unique: {duplicate_members}")
        missing_members = sorted(known_ids - set(memberships))
        if missing_members:
            errors.append(f"swimlane nodes missing lane ownership: {missing_members}")
    return group_ids


def _validate_canvas(canvas: Any, errors: list[str], warnings: list[str]) -> None:
    if not isinstance(canvas, Mapping):
        errors.append("canvas must be a mapping")
        return
    mode = canvas.get("mode", "fixed")
    if "mode" not in canvas:
        warnings.append("canvas.mode missing; treating canvas as fixed")
    if mode not in {"fixed", "auto"}:
        errors.append("canvas.mode must be fixed or auto")
        return
    if mode == "fixed":
        for dimension in ("width", "height"):
            if not _is_int(canvas.get(dimension)) or canvas[dimension] <= 0:
                errors.append(f"canvas.{dimension} must be a positive int")
        parsed = parse_viewbox(canvas.get("viewBox"))
        if parsed is None:
            errors.append("canvas.viewBox must contain four positive-space numbers")
        elif _is_int(canvas.get("width")) and _is_int(canvas.get("height")):
            expected = (0.0, 0.0, float(canvas["width"]), float(canvas["height"]))
            if parsed != expected:
                errors.append(f"canvas.viewBox must equal 0 0 {canvas['width']} {canvas['height']}")
    else:
        for dimension in ("max_width", "max_height"):
            value = canvas.get(dimension)
            if value is not None and (not _is_int(value) or value <= 0):
                errors.append(f"canvas.{dimension} must be a positive int when provided")
        margin = canvas.get("margin")
        if margin is not None and (not _is_number(margin) or margin < 0):
            errors.append("canvas.margin must be a non-negative number")


def _validate_delivery_target(target: Any, errors: list[str]) -> None:
    if not isinstance(target, Mapping):
        errors.append("delivery_target must be a mapping")
        return
    width = target.get("width_px")
    if not _is_int(width) or width <= 0:
        errors.append("delivery_target.width_px must be a positive int")
    height = target.get("height_px")
    if height is not None and (not _is_int(height) or height <= 0):
        errors.append("delivery_target.height_px must be a positive int when provided")
    if target.get("fit") != "contain":
        errors.append("delivery_target.fit must be contain")

    minimum_effective = target.get("min_effective_font_px")
    if not _is_number(minimum_effective) or minimum_effective < 12:
        errors.append("delivery_target.min_effective_font_px must be at least 12")
    contrast = target.get("min_contrast_ratio")
    if not _is_number(contrast) or not 1 <= contrast <= 21:
        errors.append("delivery_target.min_contrast_ratio must be between 1 and 21")
    padding = target.get("min_text_padding_px")
    if not _is_number(padding) or padding < 0:
        errors.append("delivery_target.min_text_padding_px must be a non-negative number")
    label_distance = target.get("max_edge_label_distance_px")
    if not _is_number(label_distance) or label_distance <= 0:
        errors.append("delivery_target.max_edge_label_distance_px must be a positive number")
    unmeasurable = target.get("max_unmeasurable_text_fraction")
    if not _is_number(unmeasurable) or not 0 <= unmeasurable <= 0.2:
        errors.append(
            "delivery_target.max_unmeasurable_text_fraction must be between 0 and 0.2"
        )


def _validate_visual_style(
    visual_style: Any,
    profile: dict[str, Any],
    profiles_data: dict[str, Any],
    errors: list[str],
) -> None:
    if not isinstance(visual_style, Mapping):
        errors.append("visual_style must be a mapping")
        return
    style_id = visual_style.get("style_id")
    if not isinstance(style_id, str) or not style_id:
        errors.append("visual_style.style_id must be a non-empty string")
    level = visual_style.get("enhancement_level")
    actual_rank = enhancement_rank(level, profiles_data)
    minimum = profile.get("minimum_enhancement")
    minimum_rank = enhancement_rank(minimum, profiles_data)
    if actual_rank is None:
        errors.append("visual_style.enhancement_level must be light, medium, or strong")
    elif minimum_rank is not None and actual_rank < minimum_rank:
        errors.append(
            f"enhancement level {level} is below the {minimum} minimum for this diagram type"
        )


def _validate_style_tokens(style_tokens: Any, errors: list[str]) -> None:
    if not isinstance(style_tokens, Mapping) or not style_tokens:
        errors.append("style_tokens must be a non-empty mapping")
        return
    colors = style_tokens.get("colors")
    color_source = colors if isinstance(colors, Mapping) else style_tokens
    for name in ("background", "surface", "primary", "text", "muted", "line"):
        value = color_source.get(name) if isinstance(color_source, Mapping) else None
        if not isinstance(value, str) or not value:
            errors.append(f"style_tokens color {name} must be defined")
    typography = style_tokens.get("typography")
    if not isinstance(typography, Mapping):
        errors.append("style_tokens.typography must be a mapping")
    else:
        if not isinstance(typography.get("font_family"), str) or not typography["font_family"]:
            errors.append("style_tokens.typography.font_family must be defined")
        sizes: dict[str, float] = {}
        for role in _TYPOGRAPHY_ROLES:
            value = typography.get(role)
            if not _is_number(value) or value <= 0:
                errors.append(f"style_tokens.typography.{role} must be a positive number")
            else:
                sizes[role] = float(value)
        if len(sizes) == len(_TYPOGRAPHY_ROLES) and not (
            sizes["diagram_title_size"]
            >= sizes["group_title_size"]
            >= sizes["node_title_size"]
            >= sizes["node_body_size"]
            >= sizes["edge_label_size"]
            >= sizes["annotation_size"]
            >= sizes["min_font_size"]
        ):
            errors.append(
                "style_tokens typography sizes must satisfy "
                "diagram_title_size >= group_title_size >= node_title_size >= "
                "node_body_size >= edge_label_size >= annotation_size >= min_font_size"
            )


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _approved_complexity_exception(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("user_approved") is True
        and _non_empty_text(value.get("reason"))
    )


def _validate_layout_plan(
    lock: dict[str, Any],
    profile: dict[str, Any],
    layouts_data: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    plan = lock.get("layout_plan")
    if not isinstance(plan, Mapping):
        errors.append("layout_plan must be a mapping")
        return

    diagram_type = lock.get("type")
    pattern = plan.get("pattern")
    layout = layout_for(pattern, layouts_data)
    allowed_patterns = profile.get("allowed_layout_patterns", [])
    preferred_patterns = profile.get("preferred_layout_patterns", [])
    if layout is None:
        errors.append(f"unknown layout_plan.pattern: {pattern!r}")
        layout = {}
    elif pattern not in allowed_patterns:
        errors.append(
            f"layout pattern {pattern!r} is not allowed for diagram type {diagram_type!r}"
        )
    else:
        supports = layout.get("supports", [])
        if diagram_type not in supports:
            errors.append(
                f"layout pattern {pattern!r} does not support diagram type {diagram_type!r}"
            )
        if pattern not in preferred_patterns and not _non_empty_text(plan.get("reason")):
            errors.append(
                f"non-preferred layout pattern {pattern!r} requires layout_plan.reason"
            )

    if not _non_empty_text(plan.get("selection_reason")):
        errors.append("layout_plan.selection_reason must be a source-grounded non-empty string")

    direction = plan.get("direction")
    directions = layout.get("directions", []) if isinstance(layout, Mapping) else []
    if not isinstance(direction, str) or direction not in directions:
        errors.append(
            f"layout_plan.direction {direction!r} is not allowed for pattern {pattern!r}"
        )
    if plan.get("density") not in _DENSITIES:
        errors.append(f"layout_plan.density must be one of {sorted(_DENSITIES)}")
    if plan.get("view_role") not in _VIEW_ROLES:
        errors.append(f"layout_plan.view_role must be one of {sorted(_VIEW_ROLES)}")
    if plan.get("density") == "dense" and plan.get("view_role") == "overview":
        errors.append("layout_plan density dense is incompatible with view_role overview")

    items = semantic_items(lock)
    edge_ids = {
        item["id"] for item in items if item["kind"] in _EDGE_LIKE_SEMANTIC_KINDS
    }
    plannable_ids = {
        item["id"]
        for item in items
        if item["kind"] not in _EDGE_LIKE_SEMANTIC_KINDS | _CONTAINER_SEMANTIC_KINDS
    }

    primary = plan.get("primary_items")
    primary_ids: list[str] = []
    if not isinstance(primary, list) or not primary:
        errors.append("layout_plan.primary_items must be a non-empty list")
    else:
        for item_id in primary:
            if not isinstance(item_id, str) or not item_id:
                errors.append("layout_plan.primary_items contains an invalid id")
            elif item_id not in plannable_ids:
                errors.append(f"layout_plan.primary_items references unknown item {item_id}")
            else:
                primary_ids.append(item_id)
        duplicates = sorted(
            item_id for item_id, count in Counter(primary_ids).items() if count > 1
        )
        if duplicates:
            errors.append(f"layout_plan.primary_items contains duplicates: {duplicates}")

    regions = plan.get("regions")
    region_members: list[str] = []
    region_ids: set[str] = set()
    if not isinstance(regions, list):
        errors.append("layout_plan.regions must be a list")
        regions = []
    for index, region in enumerate(regions):
        if not isinstance(region, Mapping):
            errors.append(f"layout_plan.regions item at index {index} must be a mapping")
            continue
        region_id = region.get("id")
        if not _non_empty_text(region_id):
            errors.append(f"layout_plan.regions item at index {index} must have an id")
        elif region_id in region_ids:
            errors.append(f"duplicate layout region id: {region_id}")
        else:
            region_ids.add(region_id)
        if region.get("placement") not in _REGION_PLACEMENTS:
            errors.append(
                f"layout region {_format_id(region_id)} placement must be one of "
                f"{sorted(_REGION_PLACEMENTS)}"
            )
        members = region.get("members")
        if not isinstance(members, list) or not members:
            errors.append(f"layout region {_format_id(region_id)} must have non-empty members")
            continue
        for member in members:
            if not isinstance(member, str) or not member:
                errors.append(f"layout region {_format_id(region_id)} has an invalid member")
            elif member not in plannable_ids:
                errors.append(
                    f"layout region {_format_id(region_id)} references unknown item {member}"
                )
            else:
                region_members.append(member)

    planned_counts = Counter(primary_ids + region_members)
    duplicate_planned = sorted(
        item_id for item_id, count in planned_counts.items() if count > 1
    )
    if duplicate_planned:
        errors.append(f"layout items must appear exactly once: duplicates {duplicate_planned}")
    unplanned = sorted(plannable_ids - set(planned_counts))
    if unplanned:
        errors.append(f"layout_plan leaves semantic items unplanned: {unplanned}")

    edge_roles = plan.get("edge_roles")
    planned_edges: list[str] = []
    if not isinstance(edge_roles, Mapping):
        errors.append("layout_plan.edge_roles must be a mapping")
    else:
        extra_roles = sorted(set(edge_roles) - set(_EDGE_ROLES))
        if extra_roles:
            errors.append(f"layout_plan.edge_roles has unsupported roles: {extra_roles}")
        for role in _EDGE_ROLES:
            if role not in edge_roles:
                errors.append(f"layout_plan.edge_roles must define {role}")
                continue
            values = edge_roles.get(role)
            if not isinstance(values, list):
                errors.append(f"layout_plan.edge_roles.{role} must be a list")
                continue
            for edge_id in values:
                if not isinstance(edge_id, str) or not edge_id:
                    errors.append(f"layout_plan.edge_roles.{role} contains an invalid id")
                elif edge_id not in edge_ids:
                    errors.append(
                        f"layout_plan.edge_roles.{role} references unknown edge {edge_id}"
                    )
                else:
                    planned_edges.append(edge_id)
    edge_counts = Counter(planned_edges)
    duplicate_edges = sorted(
        edge_id for edge_id, count in edge_counts.items() if count > 1
    )
    if duplicate_edges:
        errors.append(f"layout edges must appear exactly once: duplicates {duplicate_edges}")
    missing_edges = sorted(edge_ids - set(edge_counts))
    if missing_edges:
        errors.append(f"layout_plan.edge_roles leaves edges unclassified: {missing_edges}")

    limit_failures: list[str] = []
    section_limits = layout.get("section_limits", {}) if isinstance(layout, Mapping) else {}
    if isinstance(section_limits, Mapping):
        for section, maximum in section_limits.items():
            values = lock.get(section, [])
            count = len(values) if isinstance(values, list) else 0
            if _is_int(maximum) and count > maximum:
                limit_failures.append(f"{section}={count} exceeds {maximum}")
    max_total = layout.get("max_total_items") if isinstance(layout, Mapping) else None
    if _is_int(max_total) and len(items) > max_total:
        limit_failures.append(f"total_items={len(items)} exceeds {max_total}")

    exception = plan.get("complexity_exception")
    if limit_failures:
        message = f"layout pattern {pattern!r} complexity exceeded: " + "; ".join(limit_failures)
        if _approved_complexity_exception(exception):
            warnings.append(
                message
                + f"; user-approved exception: {str(exception.get('reason')).strip()}"
            )
        else:
            errors.append(message + "; split the diagram or obtain explicit user approval")
    elif exception is not None and not _approved_complexity_exception(exception):
        errors.append(
            "layout_plan.complexity_exception requires user_approved: true and a non-empty reason"
        )


def _validate_type_semantics(
    lock: dict[str, Any],
    diagram_type: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    if diagram_type == "sequence":
        participants = _validate_named_items(lock, "participants", errors)
        _validate_relations(lock, "messages", participants, errors)
        messages = lock.get("messages", [])
        if isinstance(messages, list):
            orders = [message.get("order") for message in messages if isinstance(message, Mapping)]
            if any(not _is_int(order) or order < 1 for order in orders):
                errors.append("sequence messages must have positive integer order values")
            elif len(set(orders)) != len(orders):
                errors.append("sequence message order values must be unique")
        return

    if diagram_type == "er":
        entities = _validate_named_items(lock, "entities", errors)
        for entity in lock.get("entities", []):
            if not isinstance(entity, Mapping):
                continue
            fields = entity.get("fields")
            if not isinstance(fields, list) or not fields:
                errors.append(f"entity {_format_id(entity.get('id'))} must define fields")
                continue
            has_primary_key = any(
                isinstance(field, Mapping)
                and (field.get("primary_key") is True or field.get("key") == "primary")
                for field in fields
            )
            if not has_primary_key:
                errors.append(f"entity {_format_id(entity.get('id'))} must define a primary key")
        _validate_relations(lock, "relationships", entities, errors, require_label=False)
        for relation in lock.get("relationships", []):
            if not isinstance(relation, Mapping):
                continue
            relation_id = _format_id(relation.get("id"))
            for field in ("from_cardinality", "to_cardinality"):
                if not isinstance(relation.get(field), str) or not relation[field]:
                    errors.append(f"relationship {relation_id} must define {field}")
        return

    if diagram_type == "state":
        states = _validate_named_items(lock, "states", errors)
        _validate_relations(lock, "transitions", states, errors)
        if not any(
            isinstance(state, Mapping) and state.get("initial") is True
            for state in lock.get("states", [])
        ):
            warnings.append("state diagram has no initial state")
        return

    nodes = _validate_named_items(lock, "nodes", errors)
    _validate_relations(lock, "edges", nodes, errors)
    if "groups" in lock:
        _validate_groups(lock, "groups", nodes, errors)
    if diagram_type == "swimlane":
        _validate_groups(lock, "lanes", nodes, errors)


def validate_lock(
    lock: dict[str, Any],
    *,
    profiles_data: dict[str, Any] | None = None,
    layouts_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(lock, Mapping):
        return {"status": "failed", "errors": ["lock must be a mapping"], "warnings": warnings}

    profiles_data = profiles_data or load_profiles()
    layouts_data = layouts_data or load_layouts()
    for key in _REQUIRED_TOP_LEVEL_KEYS:
        if key not in lock:
            errors.append(f"missing required top-level key: {key}")

    diagram_type = lock.get("type")
    profile = profile_for(diagram_type, profiles_data)
    if profile is None:
        errors.append(f"unknown diagram type: {_format_id(diagram_type)}")
        profile = {}

    source_format = lock.get("source_format")
    allowed_formats = profile.get("allowed_source_formats", [])
    preferred_formats = profile.get("preferred_source_formats", [])
    if source_format not in allowed_formats:
        errors.append(
            f"source_format {source_format!r} is not allowed for diagram type {diagram_type!r}"
        )
    elif source_format not in preferred_formats:
        reason = lock.get("renderer_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(
                f"non-preferred source_format {source_format!r} requires renderer_reason"
            )
        else:
            warnings.append(
                f"using non-preferred source_format {source_format!r}: {reason.strip()}"
            )

    for section in profile.get("required_sections", []):
        value = lock.get(section)
        if not isinstance(value, list):
            errors.append(f"required semantic section {section} must be a list")
    for section in profile.get("non_empty_sections", []):
        value = lock.get(section)
        if not isinstance(value, list) or not value:
            errors.append(f"semantic section {section} must be a non-empty list")

    _validate_canvas(lock.get("canvas"), errors, warnings)
    _validate_delivery_target(lock.get("delivery_target"), errors)
    _validate_visual_style(lock.get("visual_style"), profile, profiles_data, errors)
    _validate_style_tokens(lock.get("style_tokens"), errors)
    if isinstance(diagram_type, str):
        _validate_type_semantics(lock, diagram_type, errors, warnings)
    _validate_layout_plan(lock, profile, layouts_data, errors, warnings)

    semantic_id_counts = Counter(item["id"] for item in semantic_items(lock))
    duplicate_semantic_ids = sorted(
        item_id for item_id, count in semantic_id_counts.items() if count > 1
    )
    if duplicate_semantic_ids:
        errors.append(f"semantic ids must be globally unique: {duplicate_semantic_ids}")

    return {"status": "failed" if errors else "passed", "errors": errors, "warnings": warnings}


def validate_lock_file(
    path: Path,
    *,
    profiles_path: Path | None = None,
    layouts_path: Path | None = None,
) -> dict[str, Any]:
    return validate_lock(
        read_yaml(path),
        profiles_data=load_profiles(profiles_path),
        layouts_data=load_layouts(layouts_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a starry diagram lock file.")
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--layouts", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_lock_file(
        args.lock_file,
        profiles_path=args.profiles,
        layouts_path=args.layouts,
    )
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
