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


def load_profiles(path: Path | None = None) -> dict[str, Any]:
    data = read_yaml(path or DEFAULT_PROFILES_PATH)
    profiles = data.get("profiles")
    levels = data.get("enhancement_levels")
    if not isinstance(profiles, Mapping) or not profiles:
        raise ValueError("diagram profiles must define a non-empty profiles mapping")
    if not isinstance(levels, Mapping) or not levels:
        raise ValueError("diagram profiles must define enhancement_levels")
    return data


def profile_for(diagram_type: Any, profiles_data: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(diagram_type, str):
        return None
    profiles = profiles_data.get("profiles", {})
    profile = profiles.get(diagram_type) if isinstance(profiles, Mapping) else None
    return dict(profile) if isinstance(profile, Mapping) else None


def enhancement_rank(level: Any, profiles_data: dict[str, Any]) -> int | None:
    if not isinstance(level, str):
        return None
    levels = profiles_data.get("enhancement_levels", {})
    value = levels.get(level) if isinstance(levels, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None
