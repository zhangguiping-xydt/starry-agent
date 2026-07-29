from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

try:
    from common import svg_semantic_elements
    from profiles import notation_for
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import svg_semantic_elements
    from profiles import notation_for


_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")


def contract_version(document: Mapping[str, Any]) -> int:
    value = document.get("contract_version", document.get("version", 2))
    return value if isinstance(value, int) and not isinstance(value, bool) else 2


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _notation_records(lock: Mapping[str, Any], notation: Mapping[str, Any]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    section_roles = notation.get("section_roles", {})
    if not isinstance(section_roles, Mapping):
        return records
    for section in section_roles:
        values = lock.get(section, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, Mapping):
                continue
            item_id = value.get("id")
            role = value.get("notation_role")
            if isinstance(item_id, str) and item_id:
                records.append(
                    {
                        "id": item_id,
                        "section": str(section),
                        "role": role if isinstance(role, str) else "",
                    }
                )
    return records


def validate_lock_notation(
    lock: Mapping[str, Any],
    profile: Mapping[str, Any],
    notations_data: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    version = contract_version(lock)
    if version < 3:
        warnings.append(
            "legacy diagram contract does not enforce viewpoint and notation roles; "
            "use contract_version: 4 for new diagrams"
        )
        return {"checked": False, "contract_version": version}, errors, warnings

    viewpoint = lock.get("viewpoint_family")
    reading_question = lock.get("reading_question")
    notation_name = lock.get("notation_profile")
    if not _text(viewpoint):
        errors.append("viewpoint_family must be a non-empty string for contract v3+")
    if not _text(reading_question):
        errors.append("reading_question must be a non-empty string for contract v3+")
    if not _text(notation_name):
        errors.append("notation_profile must be a non-empty string for contract v3+")
        return {"checked": True, "contract_version": version}, errors, warnings

    allowed_viewpoints = profile.get("allowed_viewpoint_families", [])
    if viewpoint not in allowed_viewpoints:
        errors.append(
            f"viewpoint_family {viewpoint!r} is not allowed for diagram type {lock.get('type')!r}"
        )
    allowed_notations = profile.get("allowed_notation_profiles", [])
    if notation_name not in allowed_notations:
        errors.append(
            f"notation_profile {notation_name!r} is not allowed for diagram type {lock.get('type')!r}"
        )

    notation = notation_for(notation_name, notations_data)
    if notation is None:
        errors.append(f"unknown notation_profile: {notation_name!r}")
        return {
            "checked": True,
            "contract_version": version,
            "notation_profile": notation_name,
        }, errors, warnings
    if lock.get("type") not in notation.get("supports", []):
        errors.append(
            f"notation_profile {notation_name!r} does not support diagram type {lock.get('type')!r}"
        )
    if viewpoint not in notation.get("viewpoint_families", []):
        errors.append(
            f"notation_profile {notation_name!r} does not support viewpoint {viewpoint!r}"
        )

    section_roles = notation.get("section_roles", {})
    role_counts: Counter[str] = Counter()
    records = _notation_records(lock, notation)
    for record in records:
        allowed = section_roles.get(record["section"], [])
        role = record["role"]
        if not role:
            errors.append(
                f"{record['section']} {record['id']} must define notation_role for contract v3+"
            )
        elif role not in allowed:
            errors.append(
                f"{record['section']} {record['id']} notation_role {role!r} "
                f"must be one of {sorted(allowed)}"
            )
        else:
            role_counts[role] += 1

    for role in notation.get("required_roles", []):
        if role_counts[role] == 0:
            errors.append(f"notation_profile {notation_name!r} requires role {role!r}")

    layout_plan = lock.get("layout_plan", {})
    pattern = layout_plan.get("pattern") if isinstance(layout_plan, Mapping) else None
    layout_requirements = notation.get("layout_requirements", {})
    requirement = (
        layout_requirements.get(pattern)
        if isinstance(layout_requirements, Mapping) and isinstance(pattern, str)
        else None
    )
    if isinstance(requirement, Mapping):
        any_roles = requirement.get("any_roles", [])
        if isinstance(any_roles, list) and any_roles and not any(role_counts[r] for r in any_roles):
            errors.append(
                f"layout pattern {pattern!r} with notation {notation_name!r} requires "
                f"at least one role from {sorted(any_roles)}"
            )

    return {
        "checked": True,
        "contract_version": version,
        "viewpoint_family": viewpoint,
        "reading_question": reading_question,
        "notation_profile": notation_name,
        "role_counts": dict(sorted(role_counts.items())),
    }, errors, warnings


def _local_name(element: Any) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _number(value: str | None) -> float | None:
    if not isinstance(value, str):
        return None
    match = _NUMBER_RE.search(value)
    return float(match.group(0)) if match else None


def _descendants(element: Any, name: str) -> list[Any]:
    return [child for child in element.iter() if _local_name(child) == name]


def _is_diamond(element: Any) -> bool:
    for polygon in _descendants(element, "polygon"):
        values = [float(value) for value in _NUMBER_RE.findall(polygon.attrib.get("points", ""))]
        if len(values) == 8:
            points = list(zip(values[0::2], values[1::2]))
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            if len(set(xs)) >= 3 and len(set(ys)) >= 3:
                return True
    return any("rotate" in rect.attrib.get("transform", "") for rect in _descendants(element, "rect"))


def _is_terminal(element: Any) -> bool:
    if _descendants(element, "circle") or _descendants(element, "ellipse"):
        return True
    for rect in _descendants(element, "rect"):
        width = _number(rect.attrib.get("width"))
        height = _number(rect.attrib.get("height"))
        radius = _number(rect.attrib.get("rx"))
        if width and height and radius is not None and radius >= min(width, height) * 0.4:
            return True
    return False


def _has_lifeline(element: Any) -> bool:
    if not _descendants(element, "rect"):
        return False
    for line in _descendants(element, "line"):
        x1 = _number(line.attrib.get("x1"))
        x2 = _number(line.attrib.get("x2"))
        y1 = _number(line.attrib.get("y1"))
        y2 = _number(line.attrib.get("y2"))
        if None not in {x1, x2, y1, y2} and abs(x1 - x2) <= 1 and abs(y2 - y1) >= 20:
            return True
    return False


def _matches_shape(element: Any, shape: str) -> bool:
    if shape == "rect":
        return bool(_descendants(element, "rect"))
    if shape == "circle":
        return bool(_descendants(element, "circle") or _descendants(element, "ellipse"))
    if shape == "diamond":
        return _is_diamond(element)
    if shape == "terminal":
        return _is_terminal(element)
    if shape == "container":
        return bool(
            _descendants(element, "rect")
            or _descendants(element, "polygon")
            or _descendants(element, "path")
        )
    if shape == "datastore":
        return bool(_descendants(element, "ellipse")) and bool(
            _descendants(element, "rect") or _descendants(element, "path")
        )
    if shape == "entity":
        return bool(_descendants(element, "rect")) and bool(
            _descendants(element, "line") or _descendants(element, "path")
        )
    if shape == "lifeline":
        return _has_lifeline(element)
    if shape == "event-rail":
        return bool(_descendants(element, "line") or _descendants(element, "path"))
    return False


def validate_visual_notation(
    lock: Mapping[str, Any],
    root: Any,
    notations_data: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    version = contract_version(lock)
    if version < 3:
        return {"checked": False, "contract_version": version}, errors, warnings

    notation_name = lock.get("notation_profile")
    notation = notation_for(notation_name, notations_data)
    if notation is None:
        errors.append(f"unknown notation_profile: {notation_name!r}")
        return {"checked": True, "contract_version": version}, errors, warnings

    visual_shapes = notation.get("visual_shapes", {})
    elements = svg_semantic_elements(root)
    verified: list[str] = []
    for record in _notation_records(lock, notation):
        item_id = record["id"]
        role = record["role"]
        element = elements.get(item_id)
        if element is None or not role:
            continue
        actual_role = element.attrib.get("data-notation-role")
        if actual_role != role:
            errors.append(
                f"semantic element {item_id} data-notation-role must be {role!r}, "
                f"got {actual_role!r}"
            )
            continue
        allowed_shapes = visual_shapes.get(role, [])
        if not isinstance(allowed_shapes, list) or not allowed_shapes:
            errors.append(f"notation role {role!r} has no visual shape contract")
            continue
        if not any(_matches_shape(element, shape) for shape in allowed_shapes):
            errors.append(
                f"semantic element {item_id} notation role {role!r} must render as one of "
                f"{allowed_shapes}"
            )
            continue
        verified.append(item_id)

    return {
        "checked": True,
        "contract_version": version,
        "notation_profile": notation_name,
        "verified": sorted(verified),
    }, errors, warnings
