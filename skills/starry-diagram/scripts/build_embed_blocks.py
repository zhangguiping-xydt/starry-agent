from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, write_json


def source_filename(source_format: str) -> str:
    if source_format == "graphviz":
        return "source.dot"
    if source_format == "plantuml":
        return "source.puml"
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
    warnings: list[str] = []

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
    lines.extend(["", f"源码：[{source_file}](./{source_file})", ""])

    diagram_dir.mkdir(parents=True, exist_ok=True)
    (diagram_dir / "embed.md").write_text("\n".join(lines), encoding="utf-8")

    return {
        "id": entry.get("id", directory),
        "directory": directory,
        "embed": str(diagram_dir / "embed.md"),
        "image": image_file,
        "source": source_file,
        "warnings": warnings,
    }


def build_embed_blocks(diagrams_root: Path) -> dict[str, Any]:
    entries = _manifest_entries(diagrams_root)
    generated_entries = [entry for entry in entries if entry.get("status") == "generated"]
    diagrams = [build_embed_for_diagram(diagrams_root, entry) for entry in generated_entries]
    warnings = [warning for diagram in diagrams for warning in diagram["warnings"]]
    report = {
        "status": "passed_with_warnings" if warnings else "passed",
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
