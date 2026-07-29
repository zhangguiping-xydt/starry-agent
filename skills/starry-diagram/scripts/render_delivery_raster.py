from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, write_json
    from font_resolution import validate_font_resolution
    from render_preview import (
        _render_with_chrome,
        _render_with_imagemagick,
        png_dimensions,
        target_dimensions,
    )
except ModuleNotFoundError:
    import sys

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, write_json
    from font_resolution import validate_font_resolution
    from render_preview import (
        _render_with_chrome,
        _render_with_imagemagick,
        png_dimensions,
        target_dimensions,
    )


def raster_dimensions(lock: Mapping[str, Any], svg_path: Path) -> tuple[int, int, int]:
    delivery = lock.get("raster_delivery")
    if not isinstance(delivery, Mapping):
        raise ValueError("raster_delivery must be a mapping")
    if delivery.get("format") != "png":
        raise ValueError("raster_delivery.format must be png")
    pixel_ratio = delivery.get("pixel_ratio")
    if (
        not isinstance(pixel_ratio, int)
        or isinstance(pixel_ratio, bool)
        or not 2 <= pixel_ratio <= 4
    ):
        raise ValueError("raster_delivery.pixel_ratio must be an int between 2 and 4")
    logical_width, logical_height = target_dimensions(lock, svg_path)
    return logical_width * pixel_ratio, logical_height * pixel_ratio, pixel_ratio


def validate_delivery_raster(
    lock: Mapping[str, Any],
    svg_path: Path,
    delivery_path: Path,
    *,
    render_report_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        width, height, pixel_ratio = raster_dimensions(lock, svg_path)
        logical_width, logical_height = target_dimensions(lock, svg_path)
    except (OSError, ValueError) as exc:
        return {"status": "failed", "errors": [str(exc)]}
    if not delivery_path.exists():
        return {
            "status": "failed",
            "errors": [f"missing high-density raster delivery: {delivery_path.name}"],
            "pixel_ratio": pixel_ratio,
            "logical_dimensions": [logical_width, logical_height],
            "expected_dimensions": [width, height],
        }
    try:
        actual = png_dimensions(delivery_path)
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        actual = None
    if actual is not None and actual != (width, height):
        errors.append(
            "raster delivery dimensions must equal delivery target multiplied by "
            f"pixel_ratio: expected {(width, height)}, got {actual}"
        )
    try:
        visual_sha256 = hashlib.sha256(svg_path.read_bytes()).hexdigest()
    except OSError as exc:
        errors.append(f"unable to hash visual.svg: {exc}")
        visual_sha256 = None
    try:
        delivery_sha256 = hashlib.sha256(delivery_path.read_bytes()).hexdigest()
    except OSError as exc:
        errors.append(f"unable to hash delivery.png: {exc}")
        delivery_sha256 = None
    if render_report_path is not None:
        try:
            render_report = json.loads(render_report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"missing or invalid raster render report: {exc}")
            render_report = None
        if isinstance(render_report, dict):
            if render_report.get("status") != "passed":
                errors.append("raster render report status is not passed")
            if render_report.get("visual_svg_sha256") != visual_sha256:
                errors.append("raster render report visual hash does not match visual.svg")
            if render_report.get("delivery_png_sha256") != delivery_sha256:
                errors.append("raster render report delivery hash does not match delivery.png")
            font_resolution = render_report.get("font_resolution")
            if not isinstance(font_resolution, dict) or font_resolution.get("status") != "passed":
                errors.append("raster render report font resolution is missing or failed")
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "pixel_ratio": pixel_ratio,
        "logical_dimensions": [logical_width, logical_height],
        "expected_dimensions": [width, height],
        "actual_dimensions": list(actual) if actual is not None else None,
        "visual_svg_sha256": visual_sha256,
        "delivery_png_sha256": delivery_sha256,
    }


def render_delivery_raster(
    lock_path: Path,
    svg_path: Path,
    output_path: Path,
    *,
    report_path: Path | None = None,
    backend: str = "auto",
) -> dict[str, Any]:
    lock = read_yaml(lock_path)
    font_resolution = validate_font_resolution(lock)
    if font_resolution["status"] != "passed":
        report = {
            "status": "failed",
            "backend": None,
            "font_resolution": font_resolution,
            "errors": font_resolution["errors"],
        }
        if report_path is not None:
            write_json(report_path, report)
        return report
    try:
        width, height, _ = raster_dimensions(lock, svg_path)
    except (OSError, ValueError) as exc:
        report = {"status": "failed", "backend": None, "errors": [str(exc)]}
        if report_path is not None:
            write_json(report_path, report)
        return report

    renderers = {
        "chrome": _render_with_chrome,
        "imagemagick": _render_with_imagemagick,
    }
    choices = [backend] if backend != "auto" else ["chrome", "imagemagick"]
    failures: list[str] = []
    used_backend: str | None = None
    for choice in choices:
        renderer = renderers.get(choice)
        if renderer is None:
            failures.append(f"unknown raster backend: {choice}")
            continue
        success, detail = renderer(lock, svg_path, output_path, width, height)
        if success:
            used_backend = choice
            break
        failures.append(f"{choice}: {detail}")

    if used_backend is None:
        report = {
            "status": "failed",
            "backend": None,
            "errors": failures or ["no raster backend available"],
            "expected_dimensions": [width, height],
        }
    else:
        report = validate_delivery_raster(lock, svg_path, output_path)
        report["backend"] = used_backend
        report["font_resolution"] = font_resolution
        if failures:
            report["warnings"] = failures
    if report_path is not None:
        write_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a Starry Diagram high-density PNG delivery artifact."
    )
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("svg_file", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument("--backend", choices=("auto", "chrome", "imagemagick"), default="auto")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = render_delivery_raster(
        args.lock_file,
        args.svg_file,
        args.output_file,
        report_path=args.report,
        backend=args.backend,
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
