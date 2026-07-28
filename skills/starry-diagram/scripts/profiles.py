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
    for name, value in patterns.items():
        if not isinstance(name, str) or not name or not isinstance(value, Mapping):
            raise ValueError("every technical layout must have a name and mapping body")
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


def enhancement_rank(level: Any, profiles_data: dict[str, Any]) -> int | None:
    if not isinstance(level, str):
        return None
    levels = profiles_data.get("enhancement_levels", {})
    value = levels.get(level) if isinstance(levels, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None
