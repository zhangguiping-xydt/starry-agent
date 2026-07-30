from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, write_json


REQUIRED_CHECKS = (
    "diagram_type_recognizable",
    "primary_path_clear",
    "grouping_and_boundaries",
    "edge_label_ownership",
    "emphasis_matches_view_role",
    "technical_notation_fidelity",
    "semantic_roles_readable",
    "density_and_whitespace",
    "no_slide_chrome",
)
V5_REQUIRED_CHECKS = REQUIRED_CHECKS + (
    "visual_hierarchy_clear",
    "composition_content_driven",
    "edge_route_economy",
)


def preview_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_preview_review(
    preview_path: Path,
    review_path: Path,
    *,
    visual_path: Path | None = None,
    expected_contract_version: int | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if not preview_path.exists():
        return {"status": "failed", "errors": [f"missing preview: {preview_path.name}"]}
    if not review_path.exists():
        return {"status": "failed", "errors": [f"missing preview review: {review_path.name}"]}
    try:
        review = read_yaml(review_path)
    except (OSError, ValueError) as exc:
        return {"status": "failed", "errors": [str(exc)]}

    actual_hash = preview_sha256(preview_path)
    if review.get("preview_sha256") != actual_hash:
        errors.append(
            "preview_review.yaml hash does not match preview.png; review the current image"
        )
    actual_visual_hash: str | None = None
    if visual_path is not None:
        if not visual_path.exists():
            errors.append(f"missing visual SVG: {visual_path.name}")
        else:
            actual_visual_hash = preview_sha256(visual_path)
            if review.get("visual_svg_sha256") != actual_visual_hash:
                errors.append(
                    "preview_review.yaml visual hash does not match visual.svg; rerender and review"
                )
    if review.get("reviewed_at_target_size") is not True:
        errors.append("preview review must set reviewed_at_target_size: true")
    if review.get("status") != "passed":
        errors.append("preview review status must be passed after all revisions")

    declared_version = review.get("contract_version")
    if isinstance(declared_version, bool) or not isinstance(declared_version, int):
        if declared_version is not None:
            errors.append("preview review contract_version must be an integer")
        declared_version = None
    effective_version = declared_version or 4
    if expected_contract_version is not None:
        if expected_contract_version >= 5 and declared_version != expected_contract_version:
            errors.append(
                "preview review contract_version must match the v5+ diagram lock"
            )
        elif declared_version is not None and declared_version != expected_contract_version:
            errors.append("preview review contract_version does not match diagram lock")
        effective_version = expected_contract_version

    checks = review.get("checks")
    required_checks = V5_REQUIRED_CHECKS if effective_version >= 5 else REQUIRED_CHECKS
    check_results: dict[str, Any] = {}
    if not isinstance(checks, Mapping):
        errors.append("preview review checks must be a mapping")
    else:
        extra = sorted(set(checks) - set(required_checks))
        if extra:
            errors.append(f"preview review has unsupported checks: {extra}")
        for name in required_checks:
            result = checks.get(name)
            check_results[name] = result
            if result != "passed":
                errors.append(f"preview review check {name} must be passed")

    findings = review.get("findings")
    if not isinstance(findings, list):
        errors.append("preview review findings must be a list")
        findings = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, Mapping):
            errors.append(f"preview review finding at index {index} must be a mapping")
            continue
        if not isinstance(finding.get("issue"), str) or not finding["issue"].strip():
            errors.append(f"preview review finding at index {index} must describe issue")
        if finding.get("resolved") is not True:
            errors.append(f"preview review finding at index {index} must be resolved")

    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "preview_sha256": actual_hash,
        "visual_svg_sha256": actual_visual_hash,
        "contract_version": declared_version,
        "expected_contract_version": expected_contract_version,
        "checks": check_results,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a target-size technical visual review.")
    parser.add_argument("preview_file", type=Path)
    parser.add_argument("review_file", type=Path)
    parser.add_argument("--visual-svg", type=Path)
    parser.add_argument("--contract-version", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_preview_review(
        args.preview_file,
        args.review_file,
        visual_path=args.visual_svg,
        expected_contract_version=args.contract_version,
    )
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
