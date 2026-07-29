from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, write_json
    from notation import contract_version
    from profiles import (
        enhancement_rank,
        layout_for,
        load_layouts,
        load_notations,
        load_profiles,
        notation_for,
        profile_for,
    )
    from visual_identity import (
        treatment_signature,
        validate_diagram_treatment,
        validate_pack_identity,
    )
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, write_json
    from notation import contract_version
    from profiles import (
        enhancement_rank,
        layout_for,
        load_layouts,
        load_notations,
        load_profiles,
        notation_for,
        profile_for,
    )
    from visual_identity import (
        treatment_signature,
        validate_diagram_treatment,
        validate_pack_identity,
    )


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
    layouts_data: dict[str, Any],
    notations_data: dict[str, Any],
    version: int,
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

    layout_pattern = entry.get("layout_pattern")
    layout = layout_for(layout_pattern, layouts_data)
    if layout is None:
        errors.append(f"diagram {entry_id} has unknown layout_pattern {layout_pattern!r}")
    elif layout_pattern not in profile.get("allowed_layout_patterns", []):
        errors.append(
            f"diagram {entry_id} layout_pattern {layout_pattern!r} is not allowed"
        )
    elif layout_pattern not in profile.get("preferred_layout_patterns", []):
        if not _text(entry.get("layout_reason")):
            errors.append(
                f"diagram {entry_id} non-preferred layout requires layout_reason"
            )

    if version >= 3:
        viewpoint = entry.get("viewpoint_family")
        reading_question = entry.get("reading_question")
        notation_name = entry.get("notation_profile")
        if not _text(viewpoint):
            errors.append(f"diagram {entry_id} must define viewpoint_family")
        elif viewpoint not in profile.get("allowed_viewpoint_families", []):
            errors.append(
                f"diagram {entry_id} viewpoint_family {viewpoint!r} is not allowed"
            )
        elif viewpoint != profile.get("preferred_viewpoint_family") and not _text(
            entry.get("viewpoint_reason")
        ):
            errors.append(
                f"diagram {entry_id} non-preferred viewpoint requires viewpoint_reason"
            )
        if not _text(reading_question):
            errors.append(f"diagram {entry_id} must define reading_question")
        if not _text(notation_name):
            errors.append(f"diagram {entry_id} must define notation_profile")
        elif notation_name not in profile.get("allowed_notation_profiles", []):
            errors.append(
                f"diagram {entry_id} notation_profile {notation_name!r} is not allowed"
            )
        else:
            notation = notation_for(notation_name, notations_data)
            if notation is None:
                errors.append(
                    f"diagram {entry_id} has unknown notation_profile {notation_name!r}"
                )
            elif entry.get("type") not in notation.get("supports", []):
                errors.append(
                    f"diagram {entry_id} notation_profile {notation_name!r} "
                    f"does not support type {entry.get('type')!r}"
                )
            elif viewpoint not in notation.get("viewpoint_families", []):
                errors.append(
                    f"diagram {entry_id} notation_profile {notation_name!r} "
                    f"does not support viewpoint {viewpoint!r}"
                )
    if version >= 4:
        _, treatment_errors, _ = validate_diagram_treatment(
            entry.get("diagram_treatment"), entry.get("type")
        )
        errors.extend(f"diagram {entry_id} {error}" for error in treatment_errors)


def _validate_lock_consistency(
    entry: Mapping[str, Any],
    root: Path,
    manifest_version: int,
    manifest_identity: Any,
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
    lock_version = contract_version(lock)
    if manifest_version >= 3 and lock_version < 3:
        errors.append(
            f"diagram {entry_id} manifest contract_version {manifest_version} "
            f"requires a v3 lock, got {lock_version}"
        )
    if manifest_version >= 4 and lock_version < 4:
        errors.append(
            f"diagram {entry_id} manifest contract_version {manifest_version} "
            f"requires a v4 lock, got {lock_version}"
        )
    comparisons = {
        "id": lock.get("id"),
        "type": lock.get("type"),
        "source_format": lock.get("source_format"),
    }
    if contract_version(lock) >= 3 or any(
        field in entry for field in ("viewpoint_family", "reading_question", "notation_profile")
    ):
        comparisons["viewpoint_family"] = lock.get("viewpoint_family")
        comparisons["reading_question"] = lock.get("reading_question")
        comparisons["notation_profile"] = lock.get("notation_profile")
    visual_style = lock.get("visual_style", {})
    if isinstance(visual_style, Mapping):
        comparisons["style_id"] = visual_style.get("style_id")
        comparisons["enhancement_level"] = visual_style.get("enhancement_level")
    layout_plan = lock.get("layout_plan", {})
    if isinstance(layout_plan, Mapping):
        comparisons["layout_pattern"] = layout_plan.get("pattern")
        if "layout_reason" in entry or layout_plan.get("reason") is not None:
            comparisons["layout_reason"] = layout_plan.get("reason")
    if manifest_version >= 4:
        comparisons["diagram_treatment"] = lock.get("diagram_treatment")
        if lock.get("pack_identity") != manifest_identity:
            errors.append(
                f"diagram {entry_id} lock pack_identity does not match manifest pack_identity"
            )
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
    layouts_data: dict[str, Any] | None = None,
    notations_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    profiles_data = profiles_data or load_profiles()
    layouts_data = layouts_data or load_layouts()
    notations_data = notations_data or load_notations()
    version = contract_version(manifest)
    raw_version = manifest.get("contract_version")
    if raw_version is not None and (
        not isinstance(raw_version, int) or isinstance(raw_version, bool) or raw_version < 2
    ):
        errors.append("manifest contract_version must be an integer of at least 2")
    if version < 3:
        warnings.append(
            "legacy diagram manifest does not enforce viewpoint diversity; "
            "use contract_version: 4 for new diagram packs"
        )
    elif version < 4:
        warnings.append(
            "contract v3 does not enforce pack identity or per-type renderer families; "
            "use contract_version: 4 for new diagram packs"
        )

    for field in ("project", "mode", "source_summary"):
        if not _text(manifest.get(field)):
            errors.append(f"manifest {field} must be a non-empty string")
    if manifest.get("mode") != "diagram-pack":
        errors.append("manifest mode must be diagram-pack")
    identity_report: dict[str, Any] = {"checked": False, "contract_version": version}
    if version >= 4:
        identity_report, identity_errors, identity_warnings = validate_pack_identity(
            manifest.get("pack_identity")
        )
        errors.extend(identity_errors)
        warnings.extend(identity_warnings)

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

        required_entry_fields = ("title", "reason", "style_id") if version < 4 else (
            "title",
            "reason",
        )
        for field in required_entry_fields:
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
            _validate_generated_entry(
                entry,
                profile,
                profiles_data,
                layouts_data,
                notations_data,
                version,
                errors,
            )
            if root is not None:
                _validate_lock_consistency(
                    entry,
                    root,
                    version,
                    manifest.get("pack_identity"),
                    errors,
                )
        elif status in {"skipped", "needs_clarification"}:
            missing = entry.get("missing")
            if not isinstance(missing, list) or not missing:
                errors.append(f"diagram {entry_id} status {status} requires a missing list")

    generated = [
        entry
        for entry in diagrams
        if isinstance(entry, Mapping) and entry.get("status") == "generated"
    ]
    type_counts = Counter(str(entry.get("type")) for entry in generated)
    viewpoint_counts = Counter(
        str(entry.get("viewpoint_family"))
        for entry in generated
        if _text(entry.get("viewpoint_family"))
    )
    layout_counts = Counter(str(entry.get("layout_pattern")) for entry in generated)
    notation_counts = Counter(
        str(entry.get("notation_profile"))
        for entry in generated
        if _text(entry.get("notation_profile"))
    )
    treatment_counts = Counter(
        signature
        for entry in generated
        if (signature := treatment_signature(entry.get("diagram_treatment"))) is not None
    )
    signatures = Counter(
        "|".join(
            (
                str(entry.get("viewpoint_family")),
                str(entry.get("layout_pattern")),
                str(entry.get("notation_profile")),
            )
        )
        for entry in generated
        if _text(entry.get("viewpoint_family")) and _text(entry.get("notation_profile"))
    )
    repeated_signatures = {
        signature: count for signature, count in signatures.items() if count > 2
    }
    dominant_viewpoint = viewpoint_counts.most_common(1)[0] if viewpoint_counts else None
    if version >= 3:
        questions = [
            str(entry.get("reading_question")).strip().casefold()
            for entry in generated
            if _text(entry.get("reading_question"))
        ]
        duplicate_questions = sorted(
            question for question, count in Counter(questions).items() if count > 1
        )
        if duplicate_questions:
            errors.append(
                "generated diagrams must answer distinct reading questions: "
                + ", ".join(duplicate_questions)
            )
        diversity_exception_needed = bool(repeated_signatures)
        if dominant_viewpoint is not None and len(generated) >= 4:
            diversity_exception_needed = diversity_exception_needed or (
                dominant_viewpoint[1] > len(generated) / 2
            )
        if diversity_exception_needed and not _text(manifest.get("diversity_reason")):
            errors.append(
                "diagram pack repeats one viewpoint or visual signature; "
                "provide a source-grounded diversity_reason or select distinct eligible views"
            )

    diversity = {
        "generated_count": len(generated),
        "type_counts": dict(sorted(type_counts.items())),
        "viewpoint_counts": dict(sorted(viewpoint_counts.items())),
        "layout_counts": dict(sorted(layout_counts.items())),
        "notation_counts": dict(sorted(notation_counts.items())),
        "repeated_visual_signatures": repeated_signatures,
        "dominant_viewpoint": (
            {"name": dominant_viewpoint[0], "count": dominant_viewpoint[1]}
            if dominant_viewpoint
            else None
        ),
        "treatment_counts": dict(sorted(treatment_counts.items())),
    }
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": warnings,
        "contract_version": version,
        "pack_identity": identity_report,
        "diversity": diversity,
    }


def validate_manifest_file(
    path: Path,
    *,
    root: Path | None = None,
    profiles_path: Path | None = None,
    layouts_path: Path | None = None,
    notations_path: Path | None = None,
) -> dict[str, Any]:
    return validate_manifest(
        read_yaml(path),
        root=root,
        profiles_data=load_profiles(profiles_path),
        layouts_data=load_layouts(layouts_path),
        notations_data=load_notations(notations_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a starry diagram pack manifest.")
    parser.add_argument("manifest_file", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--layouts", type=Path)
    parser.add_argument("--notations", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_manifest_file(
        args.manifest_file,
        root=args.root,
        profiles_path=args.profiles,
        layouts_path=args.layouts,
        notations_path=args.notations,
    )
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
