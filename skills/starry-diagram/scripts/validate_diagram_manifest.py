from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, write_json
    from profiles import enhancement_rank, load_profiles, profile_for
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, write_json
    from profiles import enhancement_rank, load_profiles, profile_for


_STATUSES = {"generated", "skipped", "needs_clarification"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_directory(root: Path, directory: str) -> Path | None:
    path = Path(directory)
    if path.is_absolute() or ".." in path.parts:
        return None
    resolved_root = root.resolve()
    resolved_path = (root / path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return None
    return resolved_path


def _validate_generated_entry(
    entry: Mapping[str, Any],
    profile: dict[str, Any],
    profiles_data: dict[str, Any],
    errors: list[str],
) -> None:
    entry_id = entry.get("id", "<missing>")
    source_format = entry.get("source_format")
    if source_format not in profile.get("allowed_source_formats", []):
        errors.append(f"diagram {entry_id} has disallowed source_format {source_format!r}")
    elif source_format not in profile.get("preferred_source_formats", []):
        reason = entry.get("renderer_reason")
        if not _text(reason):
            errors.append(f"diagram {entry_id} non-preferred renderer requires renderer_reason")

    level = entry.get("enhancement_level")
    actual_rank = enhancement_rank(level, profiles_data)
    minimum = profile.get("minimum_enhancement")
    minimum_rank = enhancement_rank(minimum, profiles_data)
    if actual_rank is None:
        errors.append(f"diagram {entry_id} must define a valid enhancement_level")
    elif minimum_rank is not None and actual_rank < minimum_rank:
        errors.append(
            f"diagram {entry_id} enhancement level {level} is below {minimum}"
        )

    directory = entry.get("directory") or entry.get("output_dir") or entry.get("id")
    if not _text(directory):
        errors.append(f"diagram {entry_id} must define a directory")


def _validate_lock_consistency(
    entry: Mapping[str, Any],
    root: Path,
    errors: list[str],
) -> None:
    entry_id = str(entry.get("id", "<missing>"))
    directory = entry.get("directory") or entry.get("output_dir") or entry.get("id")
    if not isinstance(directory, str):
        return
    diagram_dir = _safe_directory(root, directory)
    if diagram_dir is None:
        errors.append(f"diagram {entry_id} has unsafe directory {directory!r}")
        return
    lock_path = diagram_dir / "diagram_lock.yaml"
    if not lock_path.exists():
        errors.append(f"diagram {entry_id} is missing {directory}/diagram_lock.yaml")
        return
    lock = read_yaml(lock_path)
    comparisons = {
        "id": lock.get("id"),
        "type": lock.get("type"),
        "source_format": lock.get("source_format"),
    }
    visual_style = lock.get("visual_style", {})
    if isinstance(visual_style, Mapping):
        comparisons["style_id"] = visual_style.get("style_id")
        comparisons["enhancement_level"] = visual_style.get("enhancement_level")
    for field, lock_value in comparisons.items():
        entry_value = entry.get(field)
        if entry_value != lock_value:
            errors.append(
                f"diagram {entry_id} manifest {field} {entry_value!r} "
                f"does not match lock {lock_value!r}"
            )


def validate_manifest(
    manifest: dict[str, Any],
    *,
    root: Path | None = None,
    profiles_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    profiles_data = profiles_data or load_profiles()

    for field in ("project", "mode", "source_summary"):
        if not _text(manifest.get(field)):
            errors.append(f"manifest {field} must be a non-empty string")
    if manifest.get("mode") != "diagram-pack":
        errors.append("manifest mode must be diagram-pack")

    diagrams = manifest.get("diagrams")
    if not isinstance(diagrams, list) or not diagrams:
        errors.append("manifest diagrams must be a non-empty list")
        diagrams = []

    seen_ids: set[str] = set()
    for index, entry in enumerate(diagrams):
        if not isinstance(entry, Mapping):
            errors.append(f"manifest diagram at index {index} must be a mapping")
            continue
        entry_id = entry.get("id")
        if not _text(entry_id):
            errors.append(f"manifest diagram at index {index} must have an id")
            continue
        if entry_id in seen_ids:
            errors.append(f"duplicate manifest diagram id: {entry_id}")
        seen_ids.add(entry_id)

        for field in ("title", "reason", "style_id"):
            if not _text(entry.get(field)):
                errors.append(f"diagram {entry_id} {field} must be a non-empty string")
        source_refs = entry.get("source_refs")
        if not isinstance(source_refs, list):
            errors.append(f"diagram {entry_id} source_refs must be a list")

        status = entry.get("status")
        if status not in _STATUSES:
            errors.append(f"diagram {entry_id} has invalid status {status!r}")
        diagram_type = entry.get("type")
        profile = profile_for(diagram_type, profiles_data)
        if profile is None:
            errors.append(f"diagram {entry_id} has unknown type {diagram_type!r}")
            continue

        if status == "generated":
            _validate_generated_entry(entry, profile, profiles_data, errors)
            if root is not None:
                _validate_lock_consistency(entry, root, errors)
        elif status in {"skipped", "needs_clarification"}:
            missing = entry.get("missing")
            if not isinstance(missing, list) or not missing:
                errors.append(f"diagram {entry_id} status {status} requires a missing list")

    return {"status": "failed" if errors else "passed", "errors": errors, "warnings": warnings}


def validate_manifest_file(
    path: Path,
    *,
    root: Path | None = None,
    profiles_path: Path | None = None,
) -> dict[str, Any]:
    return validate_manifest(
        read_yaml(path),
        root=root,
        profiles_data=load_profiles(profiles_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a starry diagram pack manifest.")
    parser.add_argument("manifest_file", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_manifest_file(
        args.manifest_file,
        root=args.root,
        profiles_path=args.profiles,
    )
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
