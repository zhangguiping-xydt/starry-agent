from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, write_json
    from render_delivery_raster import validate_delivery_raster
    from validate_diagram_manifest import validate_manifest_file
    from validate_preview_review import validate_preview_review
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, write_json
    from render_delivery_raster import validate_delivery_raster
    from validate_diagram_manifest import validate_manifest_file
    from validate_preview_review import validate_preview_review


def source_filename(source_format: str) -> str:
    if source_format == "graphviz":
        return "source.dot"
    if source_format == "plantuml":
        return "source.puml"
    if source_format == "svg":
        return "source.svg"
    return "source.mmd"


def _diagram_directory(entry: dict[str, Any]) -> str:
    directory = entry.get("directory") or entry.get("id")
    if not isinstance(directory, str) or not directory:
        raise ValueError("generated diagram entry must include directory or id")
    return directory


def _safe_diagram_dir(root: Path, directory: str) -> Path:
    directory_path = Path(directory)
    if (
        directory_path.is_absolute()
        or ".." in directory_path.parts
        or any(part == "" for part in directory.split("/"))
    ):
        raise ValueError(f"unsafe diagram directory: {directory}")

    resolved_root = root.resolve()
    resolved_dir = (root / directory_path).resolve()
    try:
        resolved_dir.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"unsafe diagram directory: {directory}") from exc
    return resolved_dir


def _diagram_title(entry: dict[str, Any]) -> str:
    title = entry.get("title") or entry.get("id") or "图表"
    return str(title)


def _diagram_source_file(entry: dict[str, Any]) -> str:
    source = entry.get("source") or entry.get("source_file")
    if isinstance(source, str) and source:
        return source
    source_format = entry.get("source_format")
    return source_filename(str(source_format or ""))


def _manifest_entries(diagrams_root: Path) -> list[dict[str, Any]]:
    root_manifest = diagrams_root / "diagram_manifest.yaml"
    if root_manifest.exists():
        manifest = read_yaml(root_manifest)
        entries = manifest.get("diagrams", [])
        if not isinstance(entries, list):
            raise ValueError(f"{root_manifest} diagrams must be a list")
        return [entry for entry in entries if isinstance(entry, dict)]

    entries: list[dict[str, Any]] = []
    for manifest_path in sorted(diagrams_root.glob("*/diagram_manifest.yaml")):
        entry = read_yaml(manifest_path)
        if not isinstance(entry.get("directory"), str):
            entry["directory"] = manifest_path.parent.name
        entries.append(entry)
    return entries


def build_embed_for_diagram(root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    directory = _diagram_directory(entry)
    diagram_dir = _safe_diagram_dir(root, directory)
    title = _diagram_title(entry)
    source_file = Path(_diagram_source_file(entry)).name
    visual_svg = diagram_dir / "visual.svg"
    semantic_svg = diagram_dir / "semantic.svg"
    preview_png = diagram_dir / "preview.png"
    delivery_png = diagram_dir / "delivery.png"
    preview_review = diagram_dir / "preview_review.yaml"
    warnings: list[str] = []
    check_report_path = diagram_dir / "check_report.json"
    check_status = "missing"
    raster_delivery_required = False
    lock_path = diagram_dir / "diagram_lock.yaml"
    if lock_path.exists():
        try:
            lock = read_yaml(lock_path)
            raster_delivery_required = isinstance(lock.get("raster_delivery"), dict)
        except (OSError, ValueError):
            warnings.append(f"{directory}: diagram_lock.yaml could not be read")
    if check_report_path.exists():
        try:
            check_report = json.loads(check_report_path.read_text(encoding="utf-8"))
            if isinstance(check_report, dict):
                check_status = str(check_report.get("status", "unknown"))
        except (OSError, json.JSONDecodeError):
            check_status = "invalid"

    if visual_svg.exists():
        image_file = "visual.svg"
    elif semantic_svg.exists():
        image_file = "semantic.svg"
        warnings.append(f"{directory}: visual.svg missing; embedded semantic.svg")
    else:
        image_file = None
        warnings.append(f"{directory}: visual.svg and semantic.svg missing")

    lines = [f"# {title}", ""]
    if image_file is None:
        lines.append("[render_unavailable](./render_unavailable)：视觉版本和语义版本均不可用，请查看 [check_report.json](./check_report.json)。")
    else:
        if image_file == "semantic.svg":
            lines.extend(["视觉版本不可用，当前嵌入语义版本。", ""])
        lines.append(f"![{title}](./{image_file})")
    lines.append("")
    if preview_png.exists():
        lines.extend(["目标尺寸预览：[preview.png](./preview.png)", ""])
    else:
        warnings.append(f"{directory}: preview.png missing")
    review_report = validate_preview_review(
        preview_png,
        preview_review,
        visual_path=visual_svg,
    )
    if review_report["status"] != "passed":
        warnings.append(f"{directory}: preview review missing, stale, or failed")
    delivery_status = "not_requested"
    if raster_delivery_required:
        if not visual_svg.exists():
            delivery_status = "failed"
            warnings.append(f"{directory}: visual.svg missing for raster delivery validation")
        elif delivery_png.exists():
            delivery_report = validate_delivery_raster(
                lock,
                visual_svg,
                delivery_png,
                render_report_path=diagram_dir / "delivery_render_report.json",
            )
            delivery_status = delivery_report["status"]
            if delivery_status == "passed":
                lines.extend(["高像素密度交付图：[delivery.png](./delivery.png)", ""])
            else:
                warnings.append(f"{directory}: delivery.png is stale or invalid")
        else:
            delivery_status = "missing"
            warnings.append(f"{directory}: delivery.png missing for raster delivery target")
    lines.extend([f"源码：[{source_file}](./{source_file})", ""])

    diagram_dir.mkdir(parents=True, exist_ok=True)
    (diagram_dir / "embed.md").write_text("\n".join(lines), encoding="utf-8")

    return {
        "id": entry.get("id", directory),
        "directory": directory,
        "embed": str(diagram_dir / "embed.md"),
        "image": image_file,
        "preview": "preview.png" if preview_png.exists() else None,
        "preview_review_status": review_report["status"],
        "delivery": "delivery.png" if delivery_png.exists() else None,
        "delivery_status": delivery_status,
        "source": source_file,
        "check_status": check_status,
        "warnings": warnings,
    }


def build_embed_blocks(diagrams_root: Path) -> dict[str, Any]:
    manifest_path = diagrams_root / "diagram_manifest.yaml"
    manifest_report = (
        validate_manifest_file(manifest_path, root=diagrams_root)
        if manifest_path.exists()
        else {"status": "failed", "errors": ["missing diagram_manifest.yaml"], "warnings": []}
    )
    write_json(diagrams_root / "manifest_report.json", manifest_report)
    entries = _manifest_entries(diagrams_root)
    generated_entries = [entry for entry in entries if entry.get("status") == "generated"]
    diagrams = [build_embed_for_diagram(diagrams_root, entry) for entry in generated_entries]
    warnings = list(manifest_report.get("warnings", []))
    warnings.extend(warning for diagram in diagrams for warning in diagram["warnings"])
    failed_diagrams = [
        diagram["id"]
        for diagram in diagrams
        if diagram["check_status"] != "passed"
        or diagram["preview"] is None
        or diagram["preview_review_status"] != "passed"
        or diagram["delivery_status"] in {"missing", "failed"}
    ]
    if failed_diagrams:
        warnings.append("diagram quality checks not passed: " + ", ".join(failed_diagrams))
    pack_failed = bool(failed_diagrams) or manifest_report["status"] != "passed"
    report = {
        "status": "failed" if pack_failed else ("passed_with_warnings" if warnings else "passed"),
        "manifest": manifest_report,
        "diversity": manifest_report.get("diversity", {}),
        "diagrams": diagrams,
        "warnings": warnings,
    }
    write_json(diagrams_root / "diagram_pack_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build starry diagram embed blocks and pack report.")
    parser.add_argument("diagrams_root", type=Path)
    args = parser.parse_args(argv)

    report = build_embed_blocks(args.diagrams_root)
    return 0 if report["status"] in {"passed", "passed_with_warnings"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
