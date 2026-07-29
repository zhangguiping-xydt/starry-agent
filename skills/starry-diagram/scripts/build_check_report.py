from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, write_json
    from render_delivery_raster import validate_delivery_raster
    from render_preview import validate_preview
    from validate_diagram_lock import validate_lock_file
    from validate_preview_review import validate_preview_review
    from validate_semantic_source import validate_semantic_source
    from validate_visual_svg import validate_visual_svg
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, write_json
    from render_delivery_raster import validate_delivery_raster
    from render_preview import validate_preview
    from validate_diagram_lock import validate_lock_file
    from validate_preview_review import validate_preview_review
    from validate_semantic_source import validate_semantic_source
    from validate_visual_svg import validate_visual_svg


def source_filename(source_format: Any) -> str:
    return {
        "graphviz": "source.dot",
        "mermaid": "source.mmd",
        "plantuml": "source.puml",
        "svg": "source.svg",
    }.get(str(source_format), "source.txt")


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _missing_report(name: str, path: Path) -> dict[str, Any]:
    return {"status": "failed", "errors": [f"missing {name}: {path.name}"]}


def build_check_report(
    diagram_dir: Path,
    *,
    profiles_path: Path | None = None,
    layouts_path: Path | None = None,
) -> dict[str, Any]:
    lock_path = diagram_dir / "diagram_lock.yaml"
    semantic_path = diagram_dir / "semantic.svg"
    visual_path = diagram_dir / "visual.svg"
    preview_path = diagram_dir / "preview.png"
    delivery_path = diagram_dir / "delivery.png"
    delivery_render_report_path = diagram_dir / "delivery_render_report.json"
    preview_review_path = diagram_dir / "preview_review.yaml"

    if lock_path.exists():
        lock = read_yaml(lock_path)
        lock_report = validate_lock_file(
            lock_path,
            profiles_path=profiles_path,
            layouts_path=layouts_path,
        )
        source_path = diagram_dir / source_filename(lock.get("source_format"))
    else:
        lock = {}
        lock_report = _missing_report("diagram lock", lock_path)
        source_path = diagram_dir / "source.txt"

    semantic_report = (
        validate_semantic_source(lock_path, source_path)
        if lock_path.exists() and source_path.exists()
        else _missing_report("semantic source", source_path)
    )
    visual_report = (
        validate_visual_svg(
            lock_path,
            visual_path,
            semantic_path=semantic_path,
            profiles_path=profiles_path,
            layouts_path=layouts_path,
        )
        if lock_path.exists() and semantic_path.exists() and visual_path.exists()
        else _missing_report("semantic.svg or visual.svg", visual_path)
    )
    preview_report = (
        validate_preview(lock, visual_path, preview_path)
        if lock_path.exists() and visual_path.exists()
        else _missing_report("visual.svg or preview.png", preview_path)
    )
    preview_review_report = validate_preview_review(
        preview_path,
        preview_review_path,
        visual_path=visual_path,
    )
    delivery_report = None
    if isinstance(lock.get("raster_delivery"), dict):
        delivery_report = (
            validate_delivery_raster(
                lock,
                visual_path,
                delivery_path,
                render_report_path=delivery_render_report_path,
            )
            if lock_path.exists() and visual_path.exists()
            else _missing_report("visual.svg or delivery.png", delivery_path)
        )
    renderer_report = _read_json(diagram_dir / "render_report.json")
    if renderer_report is None:
        renderer_report = {
            "status": "failed",
            "errors": ["missing or invalid render_report.json"],
        }

    reports = {
        "lock": lock_report,
        "semantic_source": semantic_report,
        "renderer": renderer_report,
        "visual": visual_report,
        "preview": preview_report,
        "preview_review": preview_review_report,
    }
    if delivery_report is not None:
        reports["raster_delivery"] = delivery_report
    failed_checks = sorted(
        name for name, report in reports.items() if report.get("status") != "passed"
    )
    visual_details = visual_report.get("visual", {})
    identity = visual_details.get("semantic_identity", {}) if isinstance(visual_details, dict) else {}
    visual_change = visual_details.get("visual_change", {}) if isinstance(visual_details, dict) else {}
    report = {
        "status": "failed" if failed_checks else "passed",
        "diagram_id": lock.get("id", diagram_dir.name),
        "failed_checks": failed_checks,
        "checks": reports,
        "semantic_drift": identity.get("valid") is False,
        "visual_changed": visual_change.get("changed"),
        "hashes": {
            "source": _sha256(source_path),
            "semantic_svg": _sha256(semantic_path),
            "visual_svg": _sha256(visual_path),
            "preview_png": _sha256(preview_path),
            "delivery_png": _sha256(delivery_path),
            "preview_review": _sha256(preview_review_path),
        },
    }

    write_json(diagram_dir / "lock_report.json", lock_report)
    write_json(diagram_dir / "semantic_report.json", semantic_report)
    write_json(diagram_dir / "visual_report.json", visual_report)
    write_json(diagram_dir / "preview_report.json", preview_report)
    write_json(diagram_dir / "preview_review_report.json", preview_review_report)
    if delivery_report is not None:
        write_json(diagram_dir / "delivery_report.json", delivery_report)
    write_json(diagram_dir / "check_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build reports for one starry diagram directory.")
    parser.add_argument("diagram_dir", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--layouts", type=Path)
    args = parser.parse_args(argv)

    report = build_check_report(
        args.diagram_dir,
        profiles_path=args.profiles,
        layouts_path=args.layouts,
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
