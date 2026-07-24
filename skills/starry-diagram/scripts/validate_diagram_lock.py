from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import parse_viewbox, read_yaml, semantic_items, write_json
    from profiles import enhancement_rank, load_profiles, profile_for
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import parse_viewbox, read_yaml, semantic_items, write_json
    from profiles import enhancement_rank, load_profiles, profile_for


_REQUIRED_TOP_LEVEL_KEYS = (
    "id",
    "title",
    "type",
    "source_format",
    "visual_style",
    "canvas",
    "style_tokens",
)
_EDGE_KINDS = {"command", "event", "data", "projection", "call"}


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
        minimum = typography.get("min_font_size")
        if not _is_number(minimum) or minimum <= 0:
            errors.append("style_tokens.typography.min_font_size must be a positive number")


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
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(lock, Mapping):
        return {"status": "failed", "errors": ["lock must be a mapping"], "warnings": warnings}

    profiles_data = profiles_data or load_profiles()
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
    _validate_visual_style(lock.get("visual_style"), profile, profiles_data, errors)
    _validate_style_tokens(lock.get("style_tokens"), errors)
    if isinstance(diagram_type, str):
        _validate_type_semantics(lock, diagram_type, errors, warnings)

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
) -> dict[str, Any]:
    return validate_lock(read_yaml(path), profiles_data=load_profiles(profiles_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a starry diagram lock file.")
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_lock_file(args.lock_file, profiles_path=args.profiles)
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
