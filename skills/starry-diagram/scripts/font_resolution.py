from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import run_command
except ModuleNotFoundError:
    import sys

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import run_command


_GENERIC_FAMILIES = {
    "cursive",
    "fantasy",
    "monospace",
    "sans-serif",
    "serif",
    "system-ui",
}


def parse_font_stack(value: str) -> list[str]:
    return [
        part.strip().strip("\"'")
        for part in value.split(",")
        if part.strip().strip("\"'")
    ]


def validate_font_resolution(lock: Mapping[str, Any]) -> dict[str, Any]:
    tokens = lock.get("style_tokens", {})
    typography = tokens.get("typography", {}) if isinstance(tokens, Mapping) else {}
    family_stack = typography.get("font_family") if isinstance(typography, Mapping) else None
    if not isinstance(family_stack, str) or not family_stack.strip():
        return {
            "status": "failed",
            "resolver": None,
            "errors": ["style_tokens.typography.font_family must be defined"],
        }

    declared = parse_font_stack(family_stack)
    explicit = [family for family in declared if family.casefold() not in _GENERIC_FAMILIES]
    if not explicit:
        return {
            "status": "failed",
            "resolver": None,
            "declared_families": declared,
            "errors": ["font stack must declare at least one non-generic font family"],
        }

    fc_match = shutil.which("fc-match")
    if fc_match is None:
        return {
            "status": "failed",
            "resolver": None,
            "declared_families": declared,
            "errors": [
                "fontconfig fc-match is unavailable; exact raster font resolution cannot be proven"
            ],
        }

    result = run_command([fc_match, "-f", "%{family}\n", family_stack])
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown fontconfig failure"
        return {
            "status": "failed",
            "resolver": "fontconfig",
            "declared_families": declared,
            "errors": [f"font resolution failed: {detail}"],
        }

    resolved = [family.strip() for family in result.stdout.strip().split(",") if family.strip()]
    explicit_keys = {family.casefold() for family in explicit}
    matched = next(
        (family for family in resolved if family.casefold() in explicit_keys),
        None,
    )
    errors = [] if matched else [
        "font stack resolved outside its declared non-generic families: "
        + (", ".join(resolved) or "<none>")
    ]
    return {
        "status": "failed" if errors else "passed",
        "resolver": "fontconfig",
        "declared_families": declared,
        "resolved_families": resolved,
        "matched_family": matched,
        "errors": errors,
    }
