from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import read_yaml
except ModuleNotFoundError:
    import sys

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml


DEFAULT_PROFILES_PATH = (
    Path(__file__).resolve().parents[1] / "templates" / "profiles" / "diagram_profiles.yaml"
)
DEFAULT_LAYOUTS_PATH = (
    Path(__file__).resolve().parents[1] / "templates" / "layouts" / "technical_layouts.yaml"
)
DEFAULT_NOTATIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "notations"
    / "technical_notations.yaml"
)


def load_profiles(path: Path | None = None) -> dict[str, Any]:
    data = read_yaml(path or DEFAULT_PROFILES_PATH)
    profiles = data.get("profiles")
    levels = data.get("enhancement_levels")
    if not isinstance(profiles, Mapping) or not profiles:
        raise ValueError("diagram profiles must define a non-empty profiles mapping")
    if not isinstance(levels, Mapping) or not levels:
        raise ValueError("diagram profiles must define enhancement_levels")
    for name, value in profiles.items():
        if not isinstance(name, str) or not name or not isinstance(value, Mapping):
            raise ValueError("every diagram profile must have a name and mapping body")
        for field in ("pick_when", "skip_when", "alternatives"):
            entries = value.get(field)
            if not isinstance(entries, list) or not entries or not all(
                isinstance(entry, str) and entry.strip() for entry in entries
            ):
                raise ValueError(f"diagram profile {name} must define non-empty {field}")
        preferred_viewpoint = value.get("preferred_viewpoint_family")
        allowed_viewpoints = value.get("allowed_viewpoint_families")
        preferred_notations = value.get("preferred_notation_profiles")
        allowed_notations = value.get("allowed_notation_profiles")
        if not isinstance(preferred_viewpoint, str) or not preferred_viewpoint:
            raise ValueError(f"diagram profile {name} must define preferred_viewpoint_family")
        if not isinstance(allowed_viewpoints, list) or preferred_viewpoint not in allowed_viewpoints:
            raise ValueError(
                f"diagram profile {name} must allow its preferred viewpoint family"
            )
        if not isinstance(preferred_notations, list) or not preferred_notations:
            raise ValueError(f"diagram profile {name} must define preferred_notation_profiles")
        if not isinstance(allowed_notations, list) or not set(preferred_notations) <= set(
            allowed_notations
        ):
            raise ValueError(
                f"diagram profile {name} must allow every preferred notation profile"
            )
    return data


def load_layouts(path: Path | None = None) -> dict[str, Any]:
    data = read_yaml(path or DEFAULT_LAYOUTS_PATH)
    patterns = data.get("patterns")
    if not isinstance(patterns, Mapping) or not patterns:
        raise ValueError("technical layouts must define a non-empty patterns mapping")
    required_quality_limits = {
        "max_edge_crossings",
        "max_edge_node_intersections",
        "max_long_edge_ratio",
        "min_analyzable_edge_fraction",
    }
    route_economy = data.get("route_economy")
    if not isinstance(route_economy, Mapping):
        raise ValueError("technical layouts must define route_economy")
    if route_economy.get("direct_when_clear") is not True:
        raise ValueError("route_economy.direct_when_clear must be true")
    clearance = route_economy.get("direct_path_clearance_px")
    if (
        not isinstance(clearance, int | float)
        or isinstance(clearance, bool)
        or clearance < 0
    ):
        raise ValueError("route_economy.direct_path_clearance_px must be non-negative")
    alignment_tolerance = route_economy.get("axis_alignment_tolerance_px")
    if (
        not isinstance(alignment_tolerance, int | float)
        or isinstance(alignment_tolerance, bool)
        or alignment_tolerance < 0
    ):
        raise ValueError("route_economy.axis_alignment_tolerance_px must be non-negative")
    for field in (
        "max_axis_aligned_detour_ratio",
        "max_axis_aligned_bends",
        "max_clear_detour_ratio",
        "max_clear_bends",
        "max_total_detour_ratio",
        "max_total_bends",
    ):
        values = route_economy.get(field)
        if not isinstance(values, Mapping):
            raise ValueError(f"route_economy.{field} must be a mapping")
        if not {"primary", "secondary", "control"} <= set(values):
            raise ValueError(f"route_economy.{field} must define every edge role")
        if not all(
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and value >= 0
            for value in values.values()
        ):
            raise ValueError(f"route_economy.{field} values must be non-negative numbers")
    route_composition = data.get("route_composition")
    if not isinstance(route_composition, Mapping):
        raise ValueError("technical layouts must define route_composition")
    for field in ("corridor_tolerance_px", "min_orbit_detour_ratio"):
        value = route_composition.get(field)
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or value < 0
        ):
            raise ValueError(f"route_composition.{field} must be non-negative")
    route_patterns = {
        "direct",
        "axis",
        "spine",
        "bus",
        "rail",
        "port",
        "branch",
        "handoff",
        "message",
        "lifecycle",
        "spoke",
        "orbit",
        "feedback",
    }
    for name, value in patterns.items():
        if not isinstance(name, str) or not name or not isinstance(value, Mapping):
            raise ValueError("every technical layout must have a name and mapping body")
        routing_family = value.get("routing_family")
        if routing_family not in {
            "orthogonal",
            "axis",
            "branching",
            "sequence",
            "lifecycle",
            "radial",
            "loop",
        }:
            raise ValueError(
                f"technical layout {name} must define a supported routing_family"
            )
        routing_strategy = value.get("routing_strategy")
        if not isinstance(routing_strategy, str) or not routing_strategy.strip():
            raise ValueError(
                f"technical layout {name} must define a routing_strategy"
            )
        allowed_route_patterns = value.get("allowed_route_patterns")
        if (
            not isinstance(allowed_route_patterns, list)
            or not allowed_route_patterns
            or not all(pattern in route_patterns for pattern in allowed_route_patterns)
        ):
            raise ValueError(
                f"technical layout {name} must define supported allowed_route_patterns"
            )
        composition_gate = value.get("composition_gate")
        if not isinstance(composition_gate, Mapping):
            raise ValueError(
                f"technical layout {name} must define composition_gate"
            )
        for field in ("min_edges", "min_group_edges"):
            gate_value = composition_gate.get(field)
            if (
                not isinstance(gate_value, int)
                or isinstance(gate_value, bool)
                or gate_value < 1
            ):
                raise ValueError(
                    f"technical layout {name} composition_gate.{field} "
                    "must be a positive integer"
                )
        direct_ratio = composition_gate.get("max_independent_direct_ratio")
        if (
            not isinstance(direct_ratio, int | float)
            or isinstance(direct_ratio, bool)
            or not 0 <= direct_ratio <= 1
        ):
            raise ValueError(
                f"technical layout {name} composition_gate."
                "max_independent_direct_ratio must be between 0 and 1"
            )
        for field in ("required_patterns", "required_any"):
            required = composition_gate.get(field, [])
            if (
                not isinstance(required, list)
                or not all(pattern in allowed_route_patterns for pattern in required)
            ):
                raise ValueError(
                    f"technical layout {name} composition_gate.{field} "
                    "must use allowed route patterns"
                )
        if not composition_gate.get("required_patterns") and not composition_gate.get(
            "required_any"
        ):
            raise ValueError(
                f"technical layout {name} composition_gate must require a route pattern"
            )
        if not isinstance(value.get("summary"), str) or not value["summary"].strip():
            raise ValueError(f"technical layout {name} must define a summary")
        for field in ("supports", "directions", "pick_when", "skip_when", "alternatives", "rules"):
            entries = value.get(field)
            if not isinstance(entries, list) or not entries or not all(
                isinstance(entry, str) and entry for entry in entries
            ):
                raise ValueError(f"technical layout {name} must define non-empty {field}")
        section_limits = value.get("section_limits")
        if not isinstance(section_limits, Mapping) or not section_limits:
            raise ValueError(f"technical layout {name} must define section_limits")
        if not all(
            isinstance(limit, int) and not isinstance(limit, bool) and limit > 0
            for limit in section_limits.values()
        ):
            raise ValueError(f"technical layout {name} section limits must be positive ints")
        max_total = value.get("max_total_items")
        if not isinstance(max_total, int) or isinstance(max_total, bool) or max_total <= 0:
            raise ValueError(f"technical layout {name} must define max_total_items")
        quality_limits = value.get("quality_limits")
        if not isinstance(quality_limits, Mapping) or not required_quality_limits <= set(
            quality_limits
        ):
            raise ValueError(
                f"technical layout {name} must define every geometry quality limit"
            )
    return data


def load_notations(path: Path | None = None) -> dict[str, Any]:
    data = read_yaml(path or DEFAULT_NOTATIONS_PATH)
    viewpoints = data.get("viewpoint_families")
    notations = data.get("notation_profiles")
    if not isinstance(viewpoints, Mapping) or not viewpoints:
        raise ValueError("technical notations must define viewpoint_families")
    if not isinstance(notations, Mapping) or not notations:
        raise ValueError("technical notations must define notation_profiles")
    for name, value in notations.items():
        if not isinstance(name, str) or not name or not isinstance(value, Mapping):
            raise ValueError("every notation profile must have a name and mapping body")
        for field in ("supports", "viewpoint_families", "section_roles", "visual_shapes"):
            field_value = value.get(field)
            expected_type = Mapping if field in {"section_roles", "visual_shapes"} else list
            if not isinstance(field_value, expected_type):
                raise ValueError(f"notation profile {name} must define {field}")
            if not field_value:
                raise ValueError(f"notation profile {name} must define non-empty {field}")
        if not all(
            isinstance(entry, str) and entry.strip()
            for entry in value["supports"] + value["viewpoint_families"]
        ):
            raise ValueError(
                f"notation profile {name} supports and viewpoint_families must contain strings"
            )
        for section, roles in value["section_roles"].items():
            if not isinstance(section, str) or not isinstance(roles, list) or not roles:
                raise ValueError(
                    f"notation profile {name} section_roles must map sections to role lists"
                )
        for role, shapes in value["visual_shapes"].items():
            if not isinstance(role, str) or not isinstance(shapes, list) or not shapes:
                raise ValueError(
                    f"notation profile {name} visual_shapes must map roles to shape lists"
                )
    return data


def profile_for(diagram_type: Any, profiles_data: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(diagram_type, str):
        return None
    profiles = profiles_data.get("profiles", {})
    profile = profiles.get(diagram_type) if isinstance(profiles, Mapping) else None
    return dict(profile) if isinstance(profile, Mapping) else None


def layout_for(pattern: Any, layouts_data: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(pattern, str):
        return None
    patterns = layouts_data.get("patterns", {})
    layout = patterns.get(pattern) if isinstance(patterns, Mapping) else None
    return dict(layout) if isinstance(layout, Mapping) else None


def notation_for(name: Any, notations_data: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(name, str):
        return None
    notations = notations_data.get("notation_profiles", {})
    notation = notations.get(name) if isinstance(notations, Mapping) else None
    return dict(notation) if isinstance(notation, Mapping) else None


def enhancement_rank(level: Any, profiles_data: dict[str, Any]) -> int | None:
    if not isinstance(level, str):
        return None
    levels = profiles_data.get("enhancement_levels", {})
    value = levels.get(level) if isinstance(levels, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None
