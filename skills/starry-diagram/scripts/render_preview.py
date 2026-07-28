from __future__ import annotations

import argparse
import html
import shutil
import struct
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import parse_svg, parse_viewbox, read_yaml, run_command, write_json
except ModuleNotFoundError:
    import sys

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import parse_svg, parse_viewbox, read_yaml, run_command, write_json


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def target_dimensions(lock: Mapping[str, Any], svg_path: Path) -> tuple[int, int]:
    target = lock.get("delivery_target")
    if not isinstance(target, Mapping):
        raise ValueError("delivery_target must be a mapping")
    width = target.get("width_px")
    height = target.get("height_px")
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise ValueError("delivery_target.width_px must be a positive int")
    if height is not None:
        if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
            raise ValueError("delivery_target.height_px must be a positive int when provided")
        return width, height

    root = parse_svg(svg_path)
    viewbox = parse_viewbox(root.attrib.get("viewBox"))
    if viewbox is None:
        raise ValueError("visual.svg must define a valid viewBox to derive preview height")
    derived_height = max(1, round(width * viewbox[3] / viewbox[2]))
    return width, derived_height


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()[:24]
    if len(payload) < 24 or payload[:8] != _PNG_SIGNATURE or payload[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a valid PNG with an IHDR header")
    return struct.unpack(">II", payload[16:24])


def validate_preview(lock: Mapping[str, Any], svg_path: Path, preview_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        expected = target_dimensions(lock, svg_path)
    except (OSError, ValueError) as exc:
        return {"status": "failed", "errors": [str(exc)]}
    if not preview_path.exists():
        return {
            "status": "failed",
            "errors": [f"missing target-size preview: {preview_path.name}"],
            "expected_dimensions": list(expected),
        }
    try:
        actual = png_dimensions(preview_path)
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        actual = None
    if actual is not None and actual != expected:
        errors.append(
            f"preview dimensions must match delivery target: expected {expected}, got {actual}"
        )
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "expected_dimensions": list(expected),
        "actual_dimensions": list(actual) if actual is not None else None,
    }


def _chrome_binary() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if path := shutil.which(name):
            return path
    return None


def _render_with_chrome(
    lock: Mapping[str, Any],
    svg_path: Path,
    output_path: Path,
    width: int,
    height: int,
) -> tuple[bool, str]:
    chrome = _chrome_binary()
    if chrome is None:
        return False, "Chrome/Chromium is unavailable"
    tokens = lock.get("style_tokens", {})
    colors = tokens.get("colors", {}) if isinstance(tokens, Mapping) else {}
    background = colors.get("background", "#ffffff") if isinstance(colors, Mapping) else "#ffffff"
    source_uri = html.escape(svg_path.resolve().as_uri(), quote=True)
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:{background};}}
img{{display:block;width:100vw;height:100vh;object-fit:contain;}}
</style></head><body><img src="{source_uri}" alt="diagram preview"></body></html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="starry-preview-") as temporary_directory:
        html_path = Path(temporary_directory) / "preview.html"
        html_path.write_text(document, encoding="utf-8")
        result = run_command(
            [
                chrome,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--hide-scrollbars",
                "--allow-file-access-from-files",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                f"--screenshot={output_path.resolve()}",
                html_path.resolve().as_uri(),
            ]
        )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Chrome failure"
        return False, detail
    if not output_path.exists():
        return False, "Chrome exited successfully without producing the preview"
    return True, ""


def _render_with_imagemagick(
    lock: Mapping[str, Any],
    svg_path: Path,
    output_path: Path,
    width: int,
    height: int,
) -> tuple[bool, str]:
    convert = shutil.which("magick") or shutil.which("convert")
    if convert is None:
        return False, "ImageMagick is unavailable"
    tokens = lock.get("style_tokens", {})
    colors = tokens.get("colors", {}) if isinstance(tokens, Mapping) else {}
    background = colors.get("background", "#ffffff") if isinstance(colors, Mapping) else "#ffffff"
    command = [convert]
    if Path(convert).name == "magick":
        command.append("convert")
    command.extend(
        [
            str(svg_path.resolve()),
            "-background",
            str(background),
            "-resize",
            f"{width}x{height}",
            "-gravity",
            "center",
            "-extent",
            f"{width}x{height}",
            str(output_path.resolve()),
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = run_command(command)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown ImageMagick failure"
        return False, detail
    if not output_path.exists():
        return False, "ImageMagick exited successfully without producing the preview"
    return True, ""


def render_preview(
    lock_path: Path,
    svg_path: Path,
    output_path: Path,
    *,
    report_path: Path | None = None,
    backend: str = "auto",
) -> dict[str, Any]:
    lock = read_yaml(lock_path)
    try:
        width, height = target_dimensions(lock, svg_path)
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
            failures.append(f"unknown preview backend: {choice}")
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
            "errors": failures or ["no preview backend available"],
            "expected_dimensions": [width, height],
        }
    else:
        report = validate_preview(lock, svg_path, output_path)
        report["backend"] = used_backend
        if failures:
            report["warnings"] = failures
    if report_path is not None:
        write_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Starry Diagram target-size PNG preview.")
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("svg_file", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument("--backend", choices=("auto", "chrome", "imagemagick"), default="auto")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = render_preview(
        args.lock_file,
        args.svg_file,
        args.output_file,
        report_path=args.report,
        backend=args.backend,
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
