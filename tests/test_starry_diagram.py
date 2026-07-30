from __future__ import annotations

import json
import hashlib
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "starry-diagram"
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_check_report import build_check_report  # noqa: E402
from build_embed_blocks import analyze_pack_visual_identity, build_embed_blocks  # noqa: E402
import font_resolution  # noqa: E402
from font_resolution import parse_font_stack, validate_font_resolution  # noqa: E402
from profiles import load_layouts, load_notations, load_profiles  # noqa: E402
from render_delivery_raster import raster_dimensions, validate_delivery_raster  # noqa: E402
from render_preview import png_dimensions, render_preview, target_dimensions  # noqa: E402
from render_svg import render_svg  # noqa: E402
from stamp_visual_metadata import stamp_visual_metadata  # noqa: E402
from validate_diagram_lock import validate_lock  # noqa: E402
from validate_diagram_manifest import validate_manifest, validate_manifest_file  # noqa: E402
from validate_preview_review import (  # noqa: E402
    REQUIRED_CHECKS,
    V5_REQUIRED_CHECKS,
    validate_preview_review,
)
from validate_semantic_source import validate_semantic_source  # noqa: E402
from validate_visual_svg import validate_visual_svg  # noqa: E402
from visual_geometry import analyze_visual_geometry  # noqa: E402
from visual_identity import validate_pack_identity  # noqa: E402
from visual_legibility import _contrast_ratio  # noqa: E402


def _style_tokens() -> dict[str, object]:
    return {
        "colors": {
            "background": "#f8fafc",
            "surface": "#ffffff",
            "primary": "#2563eb",
            "accent": "#14b8a6",
            "text": "#0f172a",
            "muted": "#64748b",
            "line": "#94a3b8",
        },
        "typography": {
            "font_family": "Noto Sans CJK SC",
            "diagram_title_size": 28,
            "group_title_size": 18,
            "node_title_size": 16,
            "node_body_size": 14,
            "edge_label_size": 14,
            "annotation_size": 13,
            "min_font_size": 12,
        },
        "geometry": {
            "node_padding_x": 24,
            "node_padding_y": 16,
            "cluster_padding": 28,
            "node_gap": 40,
            "rank_gap": 68,
            "corner_radius": 8,
        },
        "connectors": {"width": 1.6, "arrow_size": 7, "routing": "orthogonal"},
    }


def _pack_identity(*, mode: str = "custom") -> dict[str, object]:
    behavior: dict[str, object] = {
        "mode": mode,
        "description": "Precise industrial technical language without slide decoration.",
        "shape_language": "Low-radius geometry with type-native technical symbols.",
        "whitespace_rhythm": "Compact primary path with clear boundary gaps.",
        "decoration": "Semantic annotations only.",
        "elevation": "Flat hierarchy expressed through strokes and luminance.",
    }
    if mode == "preset":
        behavior["preset_id"] = "clean-technical"
    tokens = _style_tokens()
    strokes = {
        "node_width": 1.4,
        "boundary_width": 1.2,
        "connector_width": 1.6,
        "emphasis_width": 2.4,
        "linecap": "round",
        "linejoin": "round",
    }
    return {
        "id": "precise-industrial",
        "visual_behavior": behavior,
        "palette": tokens["colors"],
        "typography": tokens["typography"],
        "stroke_language": strokes,
        "texture": {
            "mode": "none",
            "description": "Solid field without grain, grid, glow, or paper texture.",
        },
    }


def _v4_architecture_lock() -> dict[str, object]:
    lock = _architecture_lock()
    lock.update(
        {
            "contract_version": 4,
            "viewpoint_family": "structure",
            "reading_question": "Which components and boundaries handle the request?",
            "notation_profile": "architecture-structure",
            "pack_identity": _pack_identity(),
            "diagram_treatment": {
                "renderer_family": "architecture",
                "composition_rhythm": "focal",
                "emphasis": "Runtime boundary and primary call path.",
                "boundary_style": "Explicit containment boundary.",
                "connector_style": "Orthogonal dependency line.",
            },
        }
    )
    lock["visual_style"] = {"enhancement_level": "strong"}
    lock["nodes"][0]["notation_role"] = "external-system"
    lock["nodes"][1]["notation_role"] = "service"
    lock["groups"][0]["notation_role"] = "boundary"
    lock["style_tokens"]["strokes"] = dict(
        lock["pack_identity"]["stroke_language"]
    )
    return lock


def _v5_architecture_lock() -> dict[str, object]:
    lock = _v4_architecture_lock()
    lock["contract_version"] = 5
    lock["style_tokens"]["connectors"]["routing"] = "adaptive"
    lock["diagram_treatment"].update(
        {
            "focal_item": "node-b",
            "hierarchy_strategy": "Node B is focal; Node A and the call path are primary.",
            "spacing_strategy": "Use the full runtime span without stranded outer margins.",
            "differentiation_strategy": "Use architecture containment and component geometry.",
        }
    )
    return lock


def _layout_plan(
    pattern: str,
    direction: str,
    primary_items: list[str],
    primary_edges: list[str],
    *,
    secondary_edges: list[str] | None = None,
    control_edges: list[str] | None = None,
    regions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "pattern": pattern,
        "selection_reason": f"Source semantics match the {pattern} selection contract.",
        "direction": direction,
        "density": "balanced",
        "view_role": "standalone",
        "primary_items": primary_items,
        "regions": regions or [],
        "edge_roles": {
            "primary": primary_edges,
            "secondary": secondary_edges or [],
            "control": control_edges or [],
        },
    }


def _delivery_target(width: int = 1200, height: int | None = None) -> dict[str, object]:
    target: dict[str, object] = {
        "width_px": width,
        "fit": "contain",
        "min_effective_font_px": 12,
        "min_contrast_ratio": 4.5,
        "min_text_padding_px": 4,
        "max_edge_label_distance_px": 28,
        "max_unmeasurable_text_fraction": 0,
    }
    if height is not None:
        target["height_px"] = height
    return target


def _architecture_lock(
    *,
    enhancement: str = "strong",
    source_format: str = "graphviz",
) -> dict[str, object]:
    return {
        "id": "architecture-overview",
        "title": "Architecture Overview",
        "type": "architecture",
        "source_format": source_format,
        "visual_style": {
            "style_id": "clean-technical",
            "enhancement_level": enhancement,
        },
        "layout_plan": _layout_plan(
            "layered-system",
            "left-to-right",
            ["node-a", "node-b"],
            ["a-to-b"],
        ),
        "canvas": {"mode": "fixed", "width": 260, "height": 120, "viewBox": "0 0 260 120"},
        "delivery_target": _delivery_target(260, 120),
        "nodes": [
            {"id": "node-a", "label": "Node A", "required": True},
            {"id": "node-b", "label": "Node B", "required": True},
        ],
        "edges": [
            {
                "id": "a-to-b",
                "from": "node-a",
                "to": "node-b",
                "label": "Calls",
                "kind": "call",
                "required": True,
            }
        ],
        "groups": [
            {
                "id": "runtime",
                "label": "Runtime",
                "members": ["node-a", "node-b"],
            }
        ],
        "style_tokens": _style_tokens(),
    }


def _base_lock(diagram_type: str, source_format: str, enhancement: str) -> dict[str, object]:
    return {
        "id": f"{diagram_type}-example",
        "title": f"{diagram_type} example",
        "type": diagram_type,
        "source_format": source_format,
        "visual_style": {
            "style_id": "clean-technical",
            "enhancement_level": enhancement,
        },
        "canvas": {"mode": "auto", "max_width": 1200, "max_height": 900, "margin": 24},
        "delivery_target": _delivery_target(),
        "style_tokens": _style_tokens(),
    }


def _svg(*, width: int = 260, shifted: bool = False, include_edge_endpoints: bool = True) -> str:
    edge_metadata = ' data-from="node-a" data-to="node-b"' if include_edge_endpoints else ""
    node_b_x = 180 if shifted else 170
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 120">
  <rect width="{width}" height="120" fill="#f8fafc"/>
  <g data-diagram-id="runtime" data-diagram-kind="group" data-members="node-a,node-b">
    <text x="8" y="22" font-family="Noto Sans CJK SC" font-size="18" data-text-role="group-title" fill="#0f172a">Runtime</text>
  </g>
  <g data-diagram-id="node-a" data-diagram-kind="node">
    <rect x="20" y="45" width="70" height="40" fill="#ffffff" stroke="#2563eb"/>
    <text x="30" y="70" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Node A</text>
  </g>
  <g data-diagram-id="node-b" data-diagram-kind="node">
    <rect x="{node_b_x}" y="45" width="70" height="40" fill="#ffffff" stroke="#2563eb"/>
    <text x="{node_b_x + 10}" y="70" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Node B</text>
  </g>
  <g data-diagram-id="a-to-b" data-diagram-kind="edge"{edge_metadata}>
    <path d="M90 65 H{node_b_x}" fill="none" stroke="#94a3b8"/>
    <text x="117" y="58" font-family="Noto Sans CJK SC" font-size="14" data-text-role="edge-label" fill="#64748b">Calls</text>
  </g>
</svg>'''


def _write_png(path: Path, width: int, height: int) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    row = b"\x00" + b"\xff\xff\xff" * width
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(row * height))
    payload += chunk(b"IEND", b"")
    path.write_bytes(payload)


def _write_preview_review(diagram_dir: Path) -> None:
    preview_path = diagram_dir / "preview.png"
    review = {
        "preview_sha256": hashlib.sha256(preview_path.read_bytes()).hexdigest(),
        "visual_svg_sha256": hashlib.sha256((diagram_dir / "visual.svg").read_bytes()).hexdigest(),
        "reviewed_at_target_size": True,
        "status": "passed",
        "checks": {
            "diagram_type_recognizable": "passed",
            "primary_path_clear": "passed",
            "grouping_and_boundaries": "passed",
            "edge_label_ownership": "passed",
            "emphasis_matches_view_role": "passed",
            "technical_notation_fidelity": "passed",
            "semantic_roles_readable": "passed",
            "density_and_whitespace": "passed",
            "no_slide_chrome": "passed",
        },
        "findings": [],
    }
    (diagram_dir / "preview_review.yaml").write_text(
        yaml.safe_dump(review, sort_keys=False), encoding="utf-8"
    )


def _write_delivery_render_report(diagram_dir: Path) -> None:
    delivery = diagram_dir / "delivery.png"
    visual = diagram_dir / "visual.svg"
    report = {
        "status": "passed",
        "backend": "test",
        "pixel_ratio": 2,
        "logical_dimensions": [260, 120],
        "expected_dimensions": [520, 240],
        "actual_dimensions": [520, 240],
        "visual_svg_sha256": hashlib.sha256(visual.read_bytes()).hexdigest(),
        "delivery_png_sha256": hashlib.sha256(delivery.read_bytes()).hexdigest(),
        "font_resolution": {
            "status": "passed",
            "resolver": "test",
            "declared_families": ["Noto Sans CJK SC"],
            "resolved_families": ["Noto Sans CJK SC"],
            "matched_family": "Noto Sans CJK SC",
            "errors": [],
        },
        "errors": [],
    }
    (diagram_dir / "delivery_render_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


def _write_diagram(tmp_path: Path, *, visual_shifted: bool = True) -> Path:
    diagram_dir = tmp_path / "architecture-overview"
    diagram_dir.mkdir()
    lock = _architecture_lock()
    (diagram_dir / "diagram_lock.yaml").write_text(
        yaml.safe_dump(lock, sort_keys=False), encoding="utf-8"
    )
    (diagram_dir / "source.dot").write_text(
        '''digraph architecture_overview {
  graph [id="runtime", label="Runtime"];
  node_a [id="node-a", label="Node A"];
  node_b [id="node-b", label="Node B"];
  node_a -> node_b [id="a-to-b", label="Calls"];
}
''',
        encoding="utf-8",
    )
    (diagram_dir / "semantic.svg").write_text(_svg(), encoding="utf-8")
    (diagram_dir / "visual.svg").write_text(
        _svg(shifted=visual_shifted), encoding="utf-8"
    )
    _write_png(diagram_dir / "preview.png", 260, 120)
    _write_preview_review(diagram_dir)
    (diagram_dir / "render_report.json").write_text(
        json.dumps({"status": "passed", "renderer": "dot"}), encoding="utf-8"
    )
    return diagram_dir


def _write_manifest(tmp_path: Path, *, source_format: str = "graphviz") -> Path:
    manifest_path = tmp_path / "diagram_manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "project": "Example",
                "mode": "diagram-pack",
                "source_summary": "Example architecture source.",
                "diagrams": [
                    {
                        "id": "architecture-overview",
                        "title": "Architecture Overview",
                        "type": "architecture",
                        "status": "generated",
                        "reason": "The source defines nodes, a boundary, and a call.",
                        "source_refs": ["architecture.md#overview"],
                        "style_id": "clean-technical",
                        "source_format": source_format,
                        "enhancement_level": "strong",
                        "layout_pattern": "layered-system",
                        "directory": "architecture-overview",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_profiles_cover_every_diagram_type_reference() -> None:
    profile_types = set(load_profiles()["profiles"])
    reference_types = {
        path.stem for path in (SKILL_DIR / "references" / "diagram-types").glob("*.md")
    }
    assert profile_types == reference_types
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "references/diagram-types/<type>.md" in skill_text
    layouts = load_layouts()["patterns"]
    for diagram_type, profile in load_profiles()["profiles"].items():
        assert profile["pick_when"]
        assert profile["skip_when"]
        assert profile["alternatives"]
        for pattern in profile["allowed_layout_patterns"]:
            assert diagram_type in layouts[pattern]["supports"]
    for layout in layouts.values():
        assert layout["pick_when"]
        assert layout["skip_when"]
        assert layout["alternatives"]


def test_profiles_reference_valid_notation_contracts() -> None:
    notations = load_notations()
    notation_profiles = notations["notation_profiles"]
    viewpoint_families = set(notations["viewpoint_families"])
    for diagram_type, profile in load_profiles()["profiles"].items():
        assert set(profile["allowed_viewpoint_families"]) <= viewpoint_families
        for notation_name in profile["allowed_notation_profiles"]:
            notation = notation_profiles[notation_name]
            assert diagram_type in notation["supports"]
            assert set(notation["viewpoint_families"]) <= viewpoint_families


def test_preview_review_template_matches_validator_contract() -> None:
    template = yaml.safe_load(
        (SKILL_DIR / "templates" / "locks" / "preview_review_reference.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert template["contract_version"] == 5
    assert tuple(template["checks"]) == V5_REQUIRED_CHECKS


def test_reference_typography_meets_reference_delivery_target() -> None:
    lock = yaml.safe_load(
        (SKILL_DIR / "templates" / "locks" / "diagram_lock_reference.yaml").read_text(
            encoding="utf-8"
        )
    )
    canvas = lock["canvas"]
    target = lock["delivery_target"]
    scale = min(target["width_px"] / canvas["width"], target["height_px"] / canvas["height"])
    typography = lock["style_tokens"]["typography"]
    role_sizes = [value for key, value in typography.items() if key.endswith("_size") and key != "min_font_size"]
    assert min(role_sizes) * scale >= target["min_effective_font_px"]


def test_style_text_tokens_meet_default_contrast() -> None:
    for style_path in (SKILL_DIR / "templates" / "styles").glob("*.yaml"):
        style = yaml.safe_load(style_path.read_text(encoding="utf-8"))
        colors = style["palette"]
        assert _contrast_ratio(colors["text"], colors["background"]) >= 4.5
        assert _contrast_ratio(colors["muted"], colors["background"]) >= 4.5
        assert _contrast_ratio(colors["muted"], colors["surface"]) >= 4.5


def test_style_presets_define_behavior_independently_from_palette() -> None:
    behaviors = set()
    radii = set()
    for style_path in (SKILL_DIR / "templates" / "styles").glob("*.yaml"):
        style = yaml.safe_load(style_path.read_text(encoding="utf-8"))
        behavior = style["visual_behavior"]
        assert behavior["mode"] == "preset"
        assert behavior["preset_id"] == style["id"]
        for field in (
            "description",
            "shape_language",
            "whitespace_rhythm",
            "decoration",
            "elevation",
        ):
            assert behavior[field]
        assert style["stroke_language"]["connector_width"] == style["connectors"]["width"]
        behaviors.add(behavior["shape_language"])
        radii.add(style["geometry"]["corner_radius"])
        identity = {
            "id": style["id"],
            "visual_behavior": behavior,
            "palette": style["palette"],
            "typography": style["typography"],
            "stroke_language": style["stroke_language"],
            "texture": style["texture"],
        }
        tokens = {
            "colors": style["palette"],
            "typography": style["typography"],
            "geometry": style["geometry"],
            "connectors": style["connectors"],
            "strokes": style["stroke_language"],
        }
        _, errors, _ = validate_pack_identity(identity, style_tokens=tokens)
        assert errors == []
    assert len(behaviors) > 1
    assert len(radii) > 1


def test_lock_rejects_enhancement_below_type_minimum() -> None:
    report = validate_lock(_architecture_lock(enhancement="light"))
    assert report["status"] == "failed"
    assert any("below the strong minimum" in error for error in report["errors"])


def test_lock_rejects_renderer_outside_type_profile() -> None:
    report = validate_lock(_architecture_lock(source_format="mermaid"))
    assert report["status"] == "failed"
    assert any("is not allowed" in error for error in report["errors"])


def test_lock_enforces_typography_role_hierarchy() -> None:
    lock = _architecture_lock()
    lock["style_tokens"]["typography"]["edge_label_size"] = 9
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("diagram_title_size >= group_title_size" in error for error in report["errors"])


def test_architecture_allows_empty_groups_without_inventing_boundaries() -> None:
    lock = _architecture_lock()
    lock["groups"] = []
    assert validate_lock(lock)["status"] == "passed"


def test_sequence_profile_validates_participants_and_message_order() -> None:
    lock = _base_lock("sequence", "plantuml", "light")
    lock["participants"] = [
        {"id": "client", "label": "Client"},
        {"id": "service", "label": "Service"},
    ]
    lock["messages"] = [
        {
            "id": "request",
            "from": "client",
            "to": "service",
            "label": "Request",
            "kind": "call",
            "order": 1,
        }
    ]
    lock["layout_plan"] = _layout_plan(
        "sequence-lifelines",
        "top-to-bottom",
        ["client", "service"],
        ["request"],
    )
    assert validate_lock(lock)["status"] == "passed"


def test_er_profile_requires_fields_primary_keys_and_cardinalities() -> None:
    lock = _base_lock("er", "mermaid", "light")
    lock["entities"] = [
        {"id": "user", "label": "User", "fields": [{"name": "id", "type": "uuid"}]},
        {
            "id": "order",
            "label": "Order",
            "fields": [{"name": "id", "type": "uuid", "primary_key": True}],
        },
    ]
    lock["relationships"] = [
        {
            "id": "user-orders",
            "from": "user",
            "to": "order",
            "from_cardinality": "1",
            "to_cardinality": "many",
        }
    ]
    lock["layout_plan"] = _layout_plan(
        "er-domain-grid",
        "left-to-right",
        ["user", "order"],
        ["user-orders"],
    )
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("user must define a primary key" in error for error in report["errors"])


def test_swimlane_fallback_renderer_requires_reason_and_lane_ownership() -> None:
    lock = _base_lock("swimlane", "graphviz", "medium")
    lock["nodes"] = [
        {"id": "submit", "label": "Submit"},
        {"id": "review", "label": "Review"},
    ]
    lock["edges"] = [
        {
            "id": "submit-review",
            "from": "submit",
            "to": "review",
            "label": "Handoff",
            "kind": "command",
        }
    ]
    lock["lanes"] = [
        {"id": "requester", "label": "Requester", "members": ["submit"]},
        {"id": "reviewer", "label": "Reviewer", "members": ["review"]},
    ]
    lock["layout_plan"] = _layout_plan(
        "swimlane-flow",
        "left-to-right",
        ["submit", "review"],
        ["submit-review"],
    )
    without_reason = validate_lock(lock)
    assert without_reason["status"] == "failed"
    assert any("requires renderer_reason" in error for error in without_reason["errors"])

    lock["renderer_reason"] = "PlantUML is unavailable in the target environment."
    with_reason = validate_lock(lock)
    assert with_reason["status"] == "passed"
    assert any("non-preferred" in warning for warning in with_reason["warnings"])


def test_lock_requires_complete_layout_plan() -> None:
    lock = _architecture_lock()
    del lock["layout_plan"]
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("layout_plan" in error for error in report["errors"])


def test_lock_requires_delivery_target_and_layout_selection_reason() -> None:
    lock = _architecture_lock()
    del lock["delivery_target"]
    del lock["layout_plan"]["selection_reason"]
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("delivery_target" in error for error in report["errors"])
    assert any("selection_reason" in error for error in report["errors"])


def test_lock_validates_high_density_raster_contract() -> None:
    lock = _architecture_lock()
    lock["raster_delivery"] = {"format": "png", "pixel_ratio": 1}
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("pixel_ratio" in error for error in report["errors"])

    lock["raster_delivery"]["pixel_ratio"] = 2
    assert validate_lock(lock)["status"] == "passed"


def test_v3_lock_enforces_notation_roles_and_layout_signature() -> None:
    lock = _architecture_lock()
    lock.update(
        {
            "contract_version": 3,
            "viewpoint_family": "structure",
            "reading_question": "Which components and boundaries handle a request?",
            "notation_profile": "architecture-structure",
        }
    )
    lock["nodes"][0]["notation_role"] = "external-system"
    lock["nodes"][1]["notation_role"] = "service"
    lock["groups"][0]["notation_role"] = "boundary"
    report = validate_lock(lock)
    assert report["status"] == "passed"
    assert report["notation"]["role_counts"] == {
        "boundary": 1,
        "external-system": 1,
        "service": 1,
    }

    del lock["groups"][0]["notation_role"]
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("must define notation_role" in error for error in report["errors"])


def test_v4_lock_accepts_custom_behavior_without_fixed_style_id() -> None:
    lock = _v4_architecture_lock()
    report = validate_lock(lock)
    assert report["status"] == "passed"
    assert report["pack_identity"]["behavior_mode"] == "custom"
    assert report["diagram_treatment"]["renderer_family"] == "architecture"


def test_v4_lock_rejects_identity_token_drift() -> None:
    lock = _v4_architecture_lock()
    lock["style_tokens"]["colors"]["primary"] = "#dc2626"
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any(
        "style_tokens.colors must exactly match pack_identity.palette" in error
        for error in report["errors"]
    )


def test_v4_lock_rejects_generic_renderer_family() -> None:
    lock = _v4_architecture_lock()
    lock["diagram_treatment"]["renderer_family"] = "generic-card"
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("must equal the locked diagram type" in error for error in report["errors"])


def test_v5_lock_requires_executable_treatment_and_primary_focal_item() -> None:
    lock = _v5_architecture_lock()
    assert validate_lock(lock)["status"] == "passed"

    del lock["diagram_treatment"]["hierarchy_strategy"]
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("hierarchy_strategy" in error for error in report["errors"])

    lock = _v5_architecture_lock()
    lock["diagram_treatment"]["focal_item"] = "runtime"
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("layout_plan.primary_items" in error for error in report["errors"])


def test_v5_lock_requires_adaptive_connector_routing() -> None:
    lock = _v5_architecture_lock()
    lock["style_tokens"]["connectors"]["routing"] = "orthogonal"
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("must be adaptive" in error for error in report["errors"])


def test_v3_branching_flow_requires_decision_role() -> None:
    lock = _base_lock("flow", "mermaid", "medium")
    lock.update(
        {
            "contract_version": 3,
            "viewpoint_family": "decision",
            "reading_question": "Which branch is taken?",
            "notation_profile": "activity-flow",
        }
    )
    lock["nodes"] = [
        {"id": "entry", "label": "Entry", "notation_role": "process"},
        {"id": "accepted", "label": "Accepted", "notation_role": "process"},
        {"id": "rejected", "label": "Rejected", "notation_role": "process"},
    ]
    lock["edges"] = [
        {"id": "yes", "from": "entry", "to": "accepted", "label": "Yes"},
        {"id": "no", "from": "entry", "to": "rejected", "label": "No"},
    ]
    lock["layout_plan"] = _layout_plan(
        "branching-flow",
        "left-to-right",
        ["entry", "accepted", "rejected"],
        ["yes"],
        secondary_edges=["no"],
    )
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("requires at least one role" in error for error in report["errors"])

    lock["nodes"][0]["notation_role"] = "decision"
    assert validate_lock(lock)["status"] == "passed"


def _v4_flow_lock_with_data_object() -> dict[str, object]:
    lock = _base_lock("flow", "mermaid", "medium")
    lock.update(
        {
            "contract_version": 4,
            "viewpoint_family": "decision",
            "reading_question": "How does validation converge while preserving its data contract?",
            "notation_profile": "activity-flow",
            "pack_identity": _pack_identity(),
            "diagram_treatment": {
                "renderer_family": "flow",
                "composition_rhythm": "explanatory",
                "emphasis": "Decision convergence and the storage contract sidecar.",
                "boundary_style": "Type-native terminals, actions, merge, and data object.",
                "connector_style": "Straight happy path with a separate data-association rail.",
            },
        }
    )
    lock["style_tokens"]["strokes"] = dict(lock["pack_identity"]["stroke_language"])
    lock["nodes"] = [
        {"id": "start", "label": "Start", "notation_role": "start"},
        {"id": "check", "label": "Allowed?", "notation_role": "decision"},
        {"id": "yes", "label": "Validate", "notation_role": "process"},
        {"id": "no", "label": "Clear", "notation_role": "process"},
        {"id": "merge", "label": "Converge", "notation_role": "merge"},
        {"id": "finish", "label": "Persist", "notation_role": "end"},
        {
            "id": "schema",
            "label": "city_code VARCHAR(64)",
            "notation_role": "data-object",
        },
    ]
    lock["edges"] = [
        {"id": "start-check", "from": "start", "to": "check", "label": "next"},
        {"id": "check-yes", "from": "check", "to": "yes", "label": "yes"},
        {"id": "check-no", "from": "check", "to": "no", "label": "no"},
        {"id": "yes-merge", "from": "yes", "to": "merge", "label": "valid"},
        {"id": "no-merge", "from": "no", "to": "merge", "label": "normalized"},
        {"id": "merge-finish", "from": "merge", "to": "finish", "label": "persist"},
        {
            "id": "schema-finish",
            "from": "schema",
            "to": "finish",
            "label": "capacity",
            "kind": "data",
        },
    ]
    lock["layout_plan"] = _layout_plan(
        "branching-flow",
        "left-to-right",
        ["start", "check", "yes", "merge", "finish"],
        ["start-check", "check-yes", "yes-merge", "merge-finish"],
        secondary_edges=["check-no", "no-merge"],
        control_edges=["schema-finish"],
        regions=[
            {"id": "exceptions", "placement": "bottom", "members": ["no"]},
            {"id": "contracts", "placement": "top", "members": ["schema"]},
        ],
    )
    return lock


def test_v4_flow_keeps_data_objects_off_the_primary_process_path() -> None:
    lock = _v4_flow_lock_with_data_object()
    assert validate_lock(lock)["status"] == "passed"

    lock["layout_plan"]["regions"][1]["members"] = []
    lock["layout_plan"]["primary_items"].append("schema")
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("FLOW_DATA_OBJECT_ON_PRIMARY_PATH" in error for error in report["errors"])


def test_v4_state_requires_standard_unlabeled_pseudostates() -> None:
    lock = _base_lock("state", "mermaid", "light")
    lock.update(
        {
            "contract_version": 4,
            "viewpoint_family": "state",
            "reading_question": "Which lifecycle transitions lead to acceptance?",
            "notation_profile": "state-machine",
            "pack_identity": _pack_identity(),
            "diagram_treatment": {
                "renderer_family": "state",
                "composition_rhythm": "focal",
                "emphasis": "Lifecycle progression and terminal acceptance.",
                "boundary_style": "Standard UML pseudo-states and named states.",
                "connector_style": "Guarded lifecycle transitions.",
            },
        }
    )
    lock["style_tokens"]["strokes"] = dict(lock["pack_identity"]["stroke_language"])
    lock["states"] = [
        {"id": "initial", "notation_role": "initial"},
        {"id": "pending", "label": "Pending", "notation_role": "state"},
        {"id": "final", "notation_role": "final"},
    ]
    lock["transitions"] = [
        {"id": "begin", "from": "initial", "to": "pending", "label": "submit"},
        {"id": "accept", "from": "pending", "to": "final", "label": "approve"},
    ]
    lock["layout_plan"] = _layout_plan(
        "state-transition",
        "left-to-right",
        ["initial", "pending", "final"],
        ["begin", "accept"],
    )
    assert validate_lock(lock)["status"] == "passed"

    lock["states"][0]["label"] = "Start"
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("STATE_PSEUDOSTATE_LABEL" in error for error in report["errors"])


def test_legacy_state_still_requires_labels_on_every_state() -> None:
    lock = _base_lock("state", "mermaid", "light")
    lock["states"] = [
        {"id": "start", "label": "Start", "initial": True},
        {"id": "done", "label": "Done"},
    ]
    lock["transitions"] = [
        {"id": "finish", "from": "start", "to": "done", "label": "complete"},
    ]
    lock["layout_plan"] = _layout_plan(
        "state-transition",
        "left-to-right",
        ["start", "done"],
        ["finish"],
    )
    assert validate_lock(lock)["status"] == "passed"

    del lock["states"][1]["label"]
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("states done must have a label" in error for error in report["errors"])


def _v4_dense_sequence_lock() -> dict[str, object]:
    lock = _base_lock("sequence", "plantuml", "light")
    lock.update(
        {
            "contract_version": 4,
            "viewpoint_family": "interaction",
            "reading_question": "How do participants exchange messages across two phases?",
            "notation_profile": "sequence-interaction",
            "pack_identity": _pack_identity(),
            "diagram_treatment": {
                "renderer_family": "sequence",
                "composition_rhythm": "dense",
                "emphasis": "Two ordered interaction phases.",
                "boundary_style": "Unboxed participants with phase fragments.",
                "connector_style": "Solid calls and dashed returns.",
            },
        }
    )
    lock["style_tokens"]["strokes"] = dict(lock["pack_identity"]["stroke_language"])
    lock["participants"] = [
        {"id": f"p{index}", "label": f"P{index}", "notation_role": "participant"}
        for index in range(8)
    ]
    lock["messages"] = [
        {
            "id": f"m{index:02d}",
            "from": f"p{index % 7}",
            "to": f"p{(index % 7) + 1}",
            "label": f"message {index}",
            "kind": "call",
            "order": index,
        }
        for index in range(1, 20)
    ]
    message_ids = [message["id"] for message in lock["messages"]]
    lock["layout_plan"] = _layout_plan(
        "sequence-lifelines",
        "top-to-bottom",
        [participant["id"] for participant in lock["participants"]],
        message_ids,
    )
    return lock


def test_v4_dense_sequence_requires_contiguous_phase_fragments() -> None:
    lock = _v4_dense_sequence_lock()
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("SEQUENCE_DENSITY_UNMITIGATED" in error for error in report["errors"])

    lock["fragments"] = [
        {
            "id": "phase-a",
            "label": "Phase A",
            "notation_role": "phase",
            "members": [f"m{index:02d}" for index in range(1, 11)],
        },
        {
            "id": "phase-b",
            "label": "Phase B",
            "notation_role": "phase",
            "members": [f"m{index:02d}" for index in range(11, 20)],
        },
    ]
    assert validate_lock(lock)["status"] == "passed"


def test_font_stack_parser_and_resolution_reject_silent_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert parse_font_stack(
        '"Source Han Sans CN", Noto Sans CJK SC, sans-serif'
    ) == ["Source Han Sans CN", "Noto Sans CJK SC", "sans-serif"]

    lock = _architecture_lock()
    lock["style_tokens"]["typography"]["font_family"] = (
        "Source Han Sans CN, Noto Sans CJK SC, Microsoft YaHei, sans-serif"
    )
    monkeypatch.setattr(
        font_resolution.shutil, "which", lambda _: "/usr/bin/fc-match"
    )
    monkeypatch.setattr(
        font_resolution,
        "run_command",
        lambda _: subprocess.CompletedProcess(
            [], 0, "Source Han Sans CN,思源黑体 CN\n", ""
        ),
    )
    report = validate_font_resolution(lock)
    assert report["status"] == "passed"
    assert report["matched_family"] == "Source Han Sans CN"

    monkeypatch.setattr(
        font_resolution,
        "run_command",
        lambda _: subprocess.CompletedProcess([], 0, "DejaVu Sans\n", ""),
    )
    report = validate_font_resolution(lock)
    assert report["status"] == "failed"
    assert report["matched_family"] is None


def test_lock_rejects_dense_overview_layout() -> None:
    lock = _architecture_lock()
    lock["layout_plan"]["density"] = "dense"
    lock["layout_plan"]["view_role"] = "overview"
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("dense is incompatible" in error for error in report["errors"])


def test_lock_requires_explicit_layout_regions_and_edge_roles() -> None:
    lock = _architecture_lock()
    del lock["layout_plan"]["regions"]
    del lock["layout_plan"]["edge_roles"]["secondary"]
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("layout_plan.regions must be a list" in error for error in report["errors"])
    assert any(
        "layout_plan.edge_roles must define secondary" in error
        for error in report["errors"]
    )


def test_lock_rejects_unplanned_items_and_edges() -> None:
    lock = _architecture_lock()
    lock["layout_plan"] = _layout_plan(
        "layered-system",
        "left-to-right",
        ["node-a"],
        [],
    )
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("unplanned" in error for error in report["errors"])
    assert any("unclassified" in error for error in report["errors"])


def test_non_preferred_layout_requires_reason() -> None:
    lock = _architecture_lock()
    lock["layout_plan"]["pattern"] = "dependency-map"
    report = validate_lock(lock)
    assert report["status"] == "failed"
    assert any("requires layout_plan.reason" in error for error in report["errors"])

    lock["layout_plan"]["reason"] = "The source is dependency-centric and has no runtime tiers."
    assert validate_lock(lock)["status"] == "passed"


def _linear_flow_lock(node_count: int) -> dict[str, object]:
    lock = _base_lock("flow", "mermaid", "medium")
    node_ids = [f"step-{index}" for index in range(node_count)]
    edge_ids = [f"edge-{index}" for index in range(node_count - 1)]
    lock["nodes"] = [{"id": item_id, "label": item_id} for item_id in node_ids]
    lock["edges"] = [
        {
            "id": edge_id,
            "from": node_ids[index],
            "to": node_ids[index + 1],
            "label": "next",
            "kind": "command",
        }
        for index, edge_id in enumerate(edge_ids)
    ]
    lock["layout_plan"] = _layout_plan(
        "linear-flow",
        "left-to-right",
        node_ids,
        edge_ids,
    )
    return lock


def test_lock_rejects_layout_over_complexity_budget() -> None:
    report = validate_lock(_linear_flow_lock(9))
    assert report["status"] == "failed"
    assert any("complexity exceeded" in error for error in report["errors"])


def test_lock_allows_only_user_approved_complexity_exception() -> None:
    lock = _linear_flow_lock(9)
    lock["layout_plan"]["complexity_exception"] = {
        "user_approved": True,
        "reason": "The user explicitly requires one printable end-to-end flow.",
    }
    report = validate_lock(lock)
    assert report["status"] == "passed"
    assert any("user-approved exception" in warning for warning in report["warnings"])


def test_visual_rejects_medium_or_strong_noop(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path, visual_shifted=False)
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        diagram_dir / "visual.svg",
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert any("visual stage was a no-op" in error for error in report["visual"]["errors"])


def test_visual_rejects_crossing_edges(tmp_path: Path) -> None:
    lock = _base_lock("flow", "mermaid", "medium")
    lock["nodes"] = [
        {"id": "a", "label": "A"},
        {"id": "b", "label": "B"},
        {"id": "c", "label": "C"},
        {"id": "d", "label": "D"},
    ]
    lock["edges"] = [
        {"id": "a-b", "from": "a", "to": "b", "label": "AB", "kind": "command"},
        {"id": "c-d", "from": "c", "to": "d", "label": "CD", "kind": "command"},
    ]
    lock["layout_plan"] = _layout_plan(
        "branching-flow",
        "left-to-right",
        ["a", "b", "c", "d"],
        ["a-b", "c-d"],
    )
    lock_path = tmp_path / "diagram_lock.yaml"
    svg_path = tmp_path / "visual.svg"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    svg_path.write_text(
        '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120">
  <rect width="200" height="120" fill="#f8fafc"/>
  <g data-diagram-id="a" data-diagram-kind="node"><rect x="10" y="6" width="40" height="30" fill="#ffffff" stroke="#2563eb"/><text x="30" y="21" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">A</text></g>
  <g data-diagram-id="b" data-diagram-kind="node"><rect x="150" y="84" width="40" height="30" fill="#ffffff" stroke="#2563eb"/><text x="170" y="99" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">B</text></g>
  <g data-diagram-id="c" data-diagram-kind="node"><rect x="10" y="84" width="40" height="30" fill="#ffffff" stroke="#2563eb"/><text x="30" y="99" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">C</text></g>
  <g data-diagram-id="d" data-diagram-kind="node"><rect x="150" y="6" width="40" height="30" fill="#ffffff" stroke="#2563eb"/><text x="170" y="21" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">D</text></g>
  <g data-diagram-id="a-b" data-diagram-kind="edge" data-from="a" data-to="b"><line x1="50" y1="36" x2="150" y2="84" stroke="#94a3b8"/><text x="75" y="48" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="14" data-text-role="edge-label" fill="#64748b">AB</text></g>
  <g data-diagram-id="c-d" data-diagram-kind="edge" data-from="c" data-to="d"><line x1="50" y1="84" x2="150" y2="36" stroke="#94a3b8"/><text x="125" y="48" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="14" data-text-role="edge-label" fill="#64748b">CD</text></g>
</svg>''',
        encoding="utf-8",
    )
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "failed"
    assert len(report["visual"]["geometry"]["edge_crossings"]) == 1
    assert any("edge crossing" in error for error in report["visual"]["errors"])


def test_visual_rejects_edge_through_nonendpoint_node(tmp_path: Path) -> None:
    lock = _base_lock("flow", "mermaid", "medium")
    lock["nodes"] = [
        {"id": "a", "label": "A"},
        {"id": "middle", "label": "Middle"},
        {"id": "b", "label": "B"},
    ]
    lock["edges"] = [
        {"id": "a-b", "from": "a", "to": "b", "label": "AB", "kind": "command"}
    ]
    lock["layout_plan"] = _layout_plan(
        "linear-flow",
        "left-to-right",
        ["a", "middle", "b"],
        ["a-b"],
    )
    lock_path = tmp_path / "diagram_lock.yaml"
    svg_path = tmp_path / "visual.svg"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    svg_path.write_text(
        '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
  <rect width="200" height="100" fill="#f8fafc"/>
  <g data-diagram-id="a" data-diagram-kind="node"><rect x="10" y="35" width="40" height="30" fill="#ffffff" stroke="#2563eb"/><text x="30" y="50" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">A</text></g>
  <g data-diagram-id="middle" data-diagram-kind="node"><rect x="80" y="28" width="40" height="44" fill="#ffffff" stroke="#2563eb"/><text x="100" y="50" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Middle</text></g>
  <g data-diagram-id="b" data-diagram-kind="node"><rect x="150" y="35" width="40" height="30" fill="#ffffff" stroke="#2563eb"/><text x="170" y="50" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">B</text></g>
  <g data-diagram-id="a-b" data-diagram-kind="edge" data-from="a" data-to="b"><line x1="50" y1="50" x2="150" y2="50" stroke="#94a3b8"/><text x="64" y="50" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="14" data-text-role="edge-label" fill="#64748b">AB</text></g>
</svg>''',
        encoding="utf-8",
    )
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "failed"
    assert report["visual"]["geometry"]["edge_node_intersections"] == [
        {"edge": "a-b", "node": "middle"}
    ]
    assert any("nonendpoint-node" in error for error in report["visual"]["errors"])


def _route_geometry_svg(path_data: str, *, obstacle: bool = False) -> ET.Element:
    middle = (
        '<g data-diagram-id="middle" data-diagram-kind="node">'
        '<rect x="80" y="28" width="40" height="44"/></g>'
        if obstacle
        else ""
    )
    return ET.fromstring(
        f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120">
  <g data-diagram-id="a" data-diagram-kind="node"><rect x="10" y="35" width="40" height="30"/></g>
  {middle}
  <g data-diagram-id="b" data-diagram-kind="node"><rect x="150" y="35" width="40" height="30"/></g>
  <g data-diagram-id="a-b" data-diagram-kind="edge" data-from="a" data-to="b"><path d="{path_data}"/></g>
</svg>'''
    )


def _route_limits() -> dict[str, object]:
    return {"route_economy": load_layouts()["route_economy"]}


def test_visual_geometry_rejects_clear_unnecessary_detour() -> None:
    root = _route_geometry_svg("M50 50 V80 H150 V50")
    report, errors, _ = analyze_visual_geometry(
        root,
        (0, 0, 200, 120),
        _route_limits(),
        edge_roles={"primary": ["a-b"], "secondary": [], "control": []},
        primary_items=["a", "b"],
    )
    assert any("UNNECESSARY_DETOUR" in error for error in errors)
    violation = report["route_economy"]["violations"][0]
    assert violation["edge"] == "a-b"
    assert violation["bend_count"] == 2
    assert violation["direct_clear"] is True


def test_visual_geometry_allows_detour_around_real_obstacle() -> None:
    root = _route_geometry_svg("M50 50 V85 H150 V50", obstacle=True)
    report, errors, _ = analyze_visual_geometry(
        root,
        (0, 0, 200, 120),
        _route_limits(),
        edge_roles={"primary": ["a-b"], "secondary": [], "control": []},
        primary_items=["a", "middle", "b"],
    )
    assert errors == []
    metric = report["route_economy"]["edges"][0]
    assert metric["direct_clear"] is False
    assert metric["direct_blockers"] == ["middle"]


def test_visual_geometry_allows_backward_feedback_outer_rail() -> None:
    root = _route_geometry_svg("M150 50 V85 H50 V50")
    report, errors, _ = analyze_visual_geometry(
        root,
        (0, 0, 200, 120),
        _route_limits(),
        edge_roles={"primary": [], "secondary": ["a-b"], "control": []},
        primary_items=["b", "a"],
        allow_backward_detours=True,
    )
    assert errors == []
    metric = report["route_economy"]["edges"][0]
    assert metric["backward_feedback"] is True
    assert metric["direct_rule_exempt"] is True


def test_v5_visual_gate_reports_route_economy_violations(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    lock = _v5_architecture_lock()
    (diagram_dir / "diagram_lock.yaml").write_text(
        yaml.safe_dump(lock, sort_keys=False), encoding="utf-8"
    )
    visual_path = diagram_dir / "visual.svg"
    visual_path.write_text(
        visual_path.read_text(encoding="utf-8").replace(
            'd="M90 65 H180"', 'd="M90 65 V100 H180 V65"'
        ),
        encoding="utf-8",
    )
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        visual_path,
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["visual"]["geometry"]["route_economy"]["checked"] is True
    assert any(
        "UNNECESSARY_DETOUR" in error for error in report["visual"]["errors"]
    )


def test_v3_visual_rejects_decision_rendered_as_process_box(tmp_path: Path) -> None:
    lock = _base_lock("flow", "mermaid", "medium")
    lock.update(
        {
            "contract_version": 3,
            "viewpoint_family": "decision",
            "reading_question": "Which outcome follows the check?",
            "notation_profile": "activity-flow",
            "canvas": {
                "mode": "fixed",
                "width": 420,
                "height": 220,
                "viewBox": "0 0 420 220",
            },
            "delivery_target": _delivery_target(420, 220),
        }
    )
    lock["nodes"] = [
        {"id": "check", "label": "Check?", "notation_role": "decision"},
        {"id": "accepted", "label": "Accepted", "notation_role": "process"},
        {"id": "rejected", "label": "Rejected", "notation_role": "process"},
    ]
    lock["edges"] = [
        {"id": "yes", "from": "check", "to": "accepted", "label": "Yes"},
        {"id": "no", "from": "check", "to": "rejected", "label": "No"},
    ]
    lock["layout_plan"] = _layout_plan(
        "branching-flow",
        "left-to-right",
        ["check", "accepted", "rejected"],
        ["yes"],
        secondary_edges=["no"],
    )
    lock_path = tmp_path / "diagram_lock.yaml"
    svg_path = tmp_path / "visual.svg"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 220">
  <rect width="420" height="220" fill="#f8fafc"/>
  <g data-diagram-id="check" data-diagram-kind="node" data-notation-role="decision">
    <rect x="40" y="70" width="120" height="80" fill="#ffffff" stroke="#2563eb"/>
    <text x="100" y="110" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Check?</text>
  </g>
  <g data-diagram-id="accepted" data-diagram-kind="node" data-notation-role="process">
    <rect x="280" y="45" width="110" height="50" fill="#ffffff" stroke="#2563eb"/>
    <text x="335" y="70" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Accepted</text>
  </g>
  <g data-diagram-id="rejected" data-diagram-kind="node" data-notation-role="process">
    <rect x="280" y="135" width="110" height="50" fill="#ffffff" stroke="#2563eb"/>
    <text x="335" y="160" text-anchor="middle" dominant-baseline="middle" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Rejected</text>
  </g>
  <g data-diagram-id="yes" data-diagram-kind="edge" data-from="check" data-to="accepted">
    <path d="M160 95 H220 V70 H280" fill="none" stroke="#94a3b8"/>
    <text x="220" y="62" text-anchor="middle" font-family="Noto Sans CJK SC" font-size="14" data-text-role="edge-label" fill="#64748b">Yes</text>
  </g>
  <g data-diagram-id="no" data-diagram-kind="edge" data-from="check" data-to="rejected">
    <path d="M160 125 H220 V160 H280" fill="none" stroke="#94a3b8"/>
    <text x="220" y="178" text-anchor="middle" font-family="Noto Sans CJK SC" font-size="14" data-text-role="edge-label" fill="#64748b">No</text>
  </g>
</svg>'''
    svg_path.write_text(svg, encoding="utf-8")
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "failed"
    assert any("must render as one of ['diamond']" in error for error in report["visual"]["errors"])

    svg_path.write_text(
        svg.replace(
            '<rect x="40" y="70" width="120" height="80" fill="#ffffff" stroke="#2563eb"/>',
            '<polygon points="100,70 160,110 100,150 40,110" fill="#ffffff" stroke="#2563eb"/>',
        ),
        encoding="utf-8",
    )
    passed = validate_visual_svg(lock_path, svg_path)
    assert passed["status"] == "passed"
    assert passed["visual"]["notation"]["verified"] == [
        "accepted",
        "check",
        "rejected",
    ]


def test_v4_visual_binds_identity_to_actual_svg_geometry(tmp_path: Path) -> None:
    lock = _v4_architecture_lock()
    lock_path = tmp_path / "diagram_lock.yaml"
    svg_path = tmp_path / "visual.svg"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120" data-pack-identity="precise-industrial" data-renderer-family="architecture" data-composition-rhythm="focal">
  <rect width="260" height="120" fill="#f8fafc"/>
  <g data-diagram-id="runtime" data-diagram-kind="group" data-members="node-a,node-b" data-notation-role="boundary">
    <rect x="4" y="4" width="252" height="112" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.2"/>
    <text x="10" y="28" font-family="Noto Sans CJK SC" font-size="18" data-text-role="group-title" fill="#0f172a">Runtime</text>
  </g>
  <g data-diagram-id="node-a" data-diagram-kind="node" data-notation-role="external-system">
    <rect x="20" y="45" width="70" height="40" fill="#ffffff" stroke="#2563eb" stroke-width="1.4"/>
    <text x="30" y="70" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Node A</text>
  </g>
  <g data-diagram-id="node-b" data-diagram-kind="node" data-notation-role="service">
    <rect x="170" y="45" width="70" height="40" fill="#ffffff" stroke="#2563eb" stroke-width="1.4"/>
    <text x="180" y="70" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Node B</text>
  </g>
  <g data-diagram-id="a-to-b" data-diagram-kind="edge" data-from="node-a" data-to="node-b">
    <path d="M90 65 H170" fill="none" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="117" y="58" font-family="Noto Sans CJK SC" font-size="14" data-text-role="edge-label" fill="#64748b">Calls</text>
  </g>
</svg>'''
    svg_path.write_text(svg, encoding="utf-8")
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "passed"
    identity = report["visual"]["visual_identity"]
    assert identity["pack_identity"] == "precise-industrial"
    assert identity["renderer_family"] == "architecture"
    assert identity["stroke_language"]["seen_widths"] == [1.2, 1.4, 1.6]

    svg_path.write_text(
        svg.replace('data-renderer-family="architecture"', 'data-renderer-family="generic-card"')
        .replace('stroke-width="1.6"', 'stroke-width="3.7"'),
        encoding="utf-8",
    )
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "failed"
    assert any("data-renderer-family" in error for error in report["visual"]["errors"])
    assert any("stroke-width 3.7" in error for error in report["visual"]["errors"])


def test_v5_visual_binds_treatment_to_hierarchy_and_composition(tmp_path: Path) -> None:
    lock = _v5_architecture_lock()
    lock_path = tmp_path / "diagram_lock.yaml"
    svg_path = tmp_path / "visual.svg"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120" data-pack-identity="precise-industrial" data-renderer-family="architecture" data-composition-rhythm="focal">
  <rect width="260" height="120" fill="#f8fafc"/>
  <g data-diagram-id="runtime" data-diagram-kind="group" data-members="node-a,node-b" data-notation-role="boundary" data-visual-tier="context">
    <rect x="4" y="4" width="252" height="112" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.2"/>
    <text x="10" y="28" font-family="Noto Sans CJK SC" font-size="18" data-text-role="group-title" fill="#0f172a">Runtime</text>
  </g>
  <g data-diagram-id="node-a" data-diagram-kind="node" data-notation-role="external-system" data-visual-tier="primary">
    <rect x="20" y="45" width="70" height="50" fill="#ffffff" stroke="#2563eb" stroke-width="1.4"/>
    <text x="30" y="70" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Node A</text>
  </g>
  <g data-diagram-id="node-b" data-diagram-kind="node" data-notation-role="service" data-visual-tier="focal">
    <rect x="170" y="45" width="70" height="50" fill="#ffffff" stroke="#2563eb" stroke-width="2.4"/>
    <text x="180" y="70" font-family="Noto Sans CJK SC" font-size="16" data-text-role="node-title" fill="#0f172a">Node B</text>
  </g>
  <g data-diagram-id="a-to-b" data-diagram-kind="edge" data-from="node-a" data-to="node-b" data-visual-tier="primary">
    <path d="M90 65 H170" fill="none" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="117" y="58" font-family="Noto Sans CJK SC" font-size="14" data-text-role="edge-label" fill="#64748b">Calls</text>
  </g>
</svg>'''
    svg_path.write_text(
        svg.replace('data-visual-tier="focal"', 'data-visual-tier="primary"'),
        encoding="utf-8",
    )
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "failed"
    assert any("data-visual-tier" in error for error in report["visual"]["errors"])

    svg_path.write_text(svg, encoding="utf-8")
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "passed", report["visual"]["errors"]
    identity = report["visual"]["visual_identity"]
    assert identity["visual_hierarchy"]["focal_item"] == "node-b"
    assert identity["composition"]["width_fraction"] > 0.8

    svg_path.write_text(svg.replace('stroke-width="2.4"', 'stroke-width="1.4"'), encoding="utf-8")
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "failed"
    assert any("focal_item" in error for error in report["visual"]["errors"])

    compact = svg.replace('x="170" y="45"', 'x="100" y="45"').replace(
        'd="M90 65 H170"', 'd="M90 65 H100"'
    )
    svg_path.write_text(compact, encoding="utf-8")
    report = validate_visual_svg(lock_path, svg_path)
    assert report["status"] == "failed"
    assert any("composition uses" in error for error in report["visual"]["errors"])


def test_visual_enforces_edge_label_role_size(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    lock_path = diagram_dir / "diagram_lock.yaml"
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    lock["style_tokens"]["typography"]["min_font_size"] = 10
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    visual_path = diagram_dir / "visual.svg"
    visual_path.write_text(
        visual_path.read_text(encoding="utf-8").replace(
            'font-size="14" data-text-role="edge-label" fill="#64748b">Calls',
            'font-size="12" data-text-role="edge-label" fill="#64748b">Calls',
        ),
        encoding="utf-8",
    )
    report = validate_visual_svg(
        lock_path,
        visual_path,
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert any("edge_label_size" in error for error in report["visual"]["errors"])


def test_visual_rejects_font_that_becomes_too_small_at_delivery_size(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    lock_path = diagram_dir / "diagram_lock.yaml"
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    lock["delivery_target"]["width_px"] = 130
    lock["delivery_target"]["height_px"] = 60
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    report = validate_visual_svg(
        lock_path,
        diagram_dir / "visual.svg",
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert report["visual"]["legibility"]["delivery_scale"] == 0.5
    assert any("effective font-size" in error for error in report["visual"]["errors"])


def test_visual_rejects_text_overflow_and_missing_role(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    visual_path = diagram_dir / "visual.svg"
    visual = visual_path.read_text(encoding="utf-8")
    visual = visual.replace('width="70" height="40"', 'width="38" height="40"', 1)
    visual = visual.replace(' data-text-role="node-title"', "", 1)
    visual_path.write_text(visual, encoding="utf-8")
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        visual_path,
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert report["visual"]["legibility"]["text"]["overflows"]
    assert any("data-text-role" in error for error in report["visual"]["errors"])


def test_visual_rejects_unanchored_edge_label_and_low_contrast(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    visual_path = diagram_dir / "visual.svg"
    visual = visual_path.read_text(encoding="utf-8")
    visual = visual.replace('x="117" y="58"', 'x="117" y="18"')
    visual = visual.replace('data-text-role="edge-label" fill="#64748b">Calls', 'data-text-role="edge-label" fill="#94a3b8">Calls')
    visual_path.write_text(visual, encoding="utf-8")
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        visual_path,
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    legibility = report["visual"]["legibility"]
    assert legibility["geometry"]["unanchored_edge_labels"]
    assert legibility["text"]["contrast_failures"]


def test_visual_rejects_unmeasurable_text_contrast(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    visual_path = diagram_dir / "visual.svg"
    visual = visual_path.read_text(encoding="utf-8").replace(
        'data-text-role="node-title" fill="#0f172a">Node A',
        'data-text-role="node-title">Node A',
    )
    visual_path.write_text(visual, encoding="utf-8")
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        visual_path,
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert report["visual"]["legibility"]["text"]["contrast_unmeasurable"] == ["Node A"]


def test_visual_rejects_fixed_canvas_mismatch(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    (diagram_dir / "visual.svg").write_text(_svg(width=220, shifted=True), encoding="utf-8")
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        diagram_dir / "visual.svg",
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert any("does not match fixed canvas" in error for error in report["visual"]["errors"])


def test_visual_rejects_missing_edge_endpoint_metadata(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    (diagram_dir / "visual.svg").write_text(
        _svg(shifted=True, include_edge_endpoints=False), encoding="utf-8"
    )
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        diagram_dir / "visual.svg",
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert any("data-from" in error for error in report["visual"]["errors"])


def test_visual_rejects_unlisted_identity_and_font_below_minimum(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    visual = _svg(shifted=True).replace(
        "</svg>",
        '''<g data-diagram-id="unexpected" data-diagram-kind="node">
  <text x="4" y="20" font-family="Noto Sans CJK SC" font-size="8" data-text-role="node-title" fill="#0f172a">Unexpected</text>
</g></svg>''',
    )
    (diagram_dir / "visual.svg").write_text(visual, encoding="utf-8")
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        diagram_dir / "visual.svg",
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert any("unlisted semantic id" in error for error in report["visual"]["errors"])
    assert any("below style_tokens" in error for error in report["visual"]["errors"])


def test_visual_rejects_duplicate_semantic_identity(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    visual = _svg(shifted=True).replace(
        "</svg>",
        '<g data-diagram-id="node-a" data-diagram-kind="node"><text>Node A</text></g></svg>',
    )
    (diagram_dir / "visual.svg").write_text(visual, encoding="utf-8")
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        diagram_dir / "visual.svg",
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert any("duplicate semantic id" in error for error in report["visual"]["errors"])


def test_semantic_source_requires_stable_ids(tmp_path: Path) -> None:
    lock_path = tmp_path / "diagram_lock.yaml"
    source_path = tmp_path / "source.dot"
    lock_path.write_text(
        yaml.safe_dump(_architecture_lock(), sort_keys=False), encoding="utf-8"
    )
    source_path.write_text(
        'digraph example { a [label="Node A"]; b [label="Node B"]; a -> b [label="Calls"]; }',
        encoding="utf-8",
    )
    report = validate_semantic_source(lock_path, source_path)
    assert report["status"] == "failed"
    assert report["semantic"]["verified_ids"] == 0
    assert any("missing stable semantic id" in error for error in report["semantic"]["errors"])


def test_build_check_report_generates_machine_derived_pass(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    report = build_check_report(diagram_dir)
    assert report["status"] == "passed"
    assert report["semantic_drift"] is False
    assert report["visual_changed"] is True
    stored = json.loads((diagram_dir / "check_report.json").read_text(encoding="utf-8"))
    assert stored["hashes"]["semantic_svg"]
    assert stored["hashes"]["visual_svg"]
    assert stored["hashes"]["preview_png"]


def test_build_check_report_requires_target_size_preview(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    (diagram_dir / "preview.png").unlink()
    report = build_check_report(diagram_dir)
    assert report["status"] == "failed"
    assert "preview" in report["failed_checks"]


def test_build_check_report_requires_declared_high_density_delivery(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    lock_path = diagram_dir / "diagram_lock.yaml"
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    lock["raster_delivery"] = {"format": "png", "pixel_ratio": 2}
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")

    report = build_check_report(diagram_dir)
    assert report["status"] == "failed"
    assert "raster_delivery" in report["failed_checks"]

    _write_png(diagram_dir / "delivery.png", 520, 240)
    _write_delivery_render_report(diagram_dir)
    delivery_report = validate_delivery_raster(
        lock,
        diagram_dir / "visual.svg",
        diagram_dir / "delivery.png",
        render_report_path=diagram_dir / "delivery_render_report.json",
    )
    assert delivery_report["status"] == "passed"
    assert raster_dimensions(lock, diagram_dir / "visual.svg") == (520, 240, 2)
    assert build_check_report(diagram_dir)["status"] == "passed"

    (diagram_dir / "delivery.png").write_bytes(
        (diagram_dir / "delivery.png").read_bytes() + b"stale"
    )
    assert build_check_report(diagram_dir)["status"] == "failed"


def test_preview_review_is_bound_to_current_preview(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    _write_png(diagram_dir / "preview.png", 260, 120)
    preview = diagram_dir / "preview.png"
    preview.write_bytes(preview.read_bytes() + b"stale")
    report = validate_preview_review(preview, diagram_dir / "preview_review.yaml")
    assert report["status"] == "failed"
    assert any("hash does not match" in error for error in report["errors"])


def test_preview_review_is_bound_to_current_visual_svg(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    visual_path = diagram_dir / "visual.svg"
    visual_path.write_text(
        visual_path.read_text(encoding="utf-8").replace("</svg>", "<!-- changed --></svg>"),
        encoding="utf-8",
    )
    report = validate_preview_review(
        diagram_dir / "preview.png",
        diagram_dir / "preview_review.yaml",
        visual_path=visual_path,
    )
    assert report["status"] == "failed"
    assert any("visual hash does not match" in error for error in report["errors"])


def test_v5_preview_review_requires_lock_version_and_new_checks(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    review_path = diagram_dir / "preview_review.yaml"
    report = validate_preview_review(
        diagram_dir / "preview.png",
        review_path,
        visual_path=diagram_dir / "visual.svg",
        expected_contract_version=5,
    )
    assert report["status"] == "failed"
    assert any("contract_version" in error for error in report["errors"])
    assert any("visual_hierarchy_clear" in error for error in report["errors"])

    review = yaml.safe_load(review_path.read_text(encoding="utf-8"))
    review["contract_version"] = 5
    review["checks"]["visual_hierarchy_clear"] = "passed"
    review["checks"]["composition_content_driven"] = "passed"
    review["checks"]["edge_route_economy"] = "passed"
    review_path.write_text(yaml.safe_dump(review, sort_keys=False), encoding="utf-8")
    assert (
        validate_preview_review(
            diagram_dir / "preview.png",
            review_path,
            visual_path=diagram_dir / "visual.svg",
            expected_contract_version=5,
        )["status"]
        == "passed"
    )


def test_build_report_uses_lock_version_for_preview_review(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    (diagram_dir / "diagram_lock.yaml").write_text(
        yaml.safe_dump(_v5_architecture_lock(), sort_keys=False), encoding="utf-8"
    )
    report = build_check_report(diagram_dir)
    assert report["status"] == "failed"
    assert "preview_review" in report["failed_checks"]
    assert any(
        "contract_version" in error
        for error in report["checks"]["preview_review"]["errors"]
    )


def test_preview_dimension_helpers_and_renderer(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    lock_path = diagram_dir / "diagram_lock.yaml"
    visual_path = diagram_dir / "visual.svg"
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    del lock["delivery_target"]["height_px"]
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    assert target_dimensions(lock, visual_path) == (260, 120)
    assert png_dimensions(diagram_dir / "preview.png") == (260, 120)

    if not any(shutil.which(name) for name in ("google-chrome", "chromium", "convert", "magick")):
        pytest.skip("no supported SVG preview renderer installed")
    rendered = diagram_dir / "preview.png"
    report = render_preview(lock_path, visual_path, rendered)
    assert report["status"] == "passed"
    assert png_dimensions(rendered) == (260, 120)
    _write_preview_review(diagram_dir)
    assert build_check_report(diagram_dir)["status"] == "passed"


def test_stamp_visual_metadata_adds_endpoints_and_members(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    unstamped = diagram_dir / "unstamped.svg"
    unstamped.write_text(
        '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
  <g id="runtime"><text>Runtime</text></g>
  <g id="node-a"><text>Node A</text></g>
  <g id="node-b"><text>Node B</text></g>
  <g id="a-to-b"><text>Calls</text></g>
</svg>''',
        encoding="utf-8",
    )
    result = stamp_visual_metadata(
        diagram_dir / "diagram_lock.yaml",
        unstamped,
        unstamped,
    )
    assert result["status"] == "passed"
    stamped = unstamped.read_text(encoding="utf-8")
    assert 'data-from="node-a"' in stamped
    assert 'data-to="node-b"' in stamped
    assert 'data-members="node-a,node-b"' in stamped


def test_stamp_visual_metadata_adds_locked_notation_roles(tmp_path: Path) -> None:
    lock = _architecture_lock()
    lock.update(
        {
            "contract_version": 3,
            "viewpoint_family": "structure",
            "reading_question": "Which components handle the request?",
            "notation_profile": "architecture-structure",
        }
    )
    lock["nodes"][0]["notation_role"] = "external-system"
    lock["nodes"][1]["notation_role"] = "service"
    lock["groups"][0]["notation_role"] = "boundary"
    lock_path = tmp_path / "diagram_lock.yaml"
    svg_path = tmp_path / "visual.svg"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    svg_path.write_text(
        '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120">
  <g id="runtime"><rect x="5" y="5" width="250" height="110"/></g>
  <g id="node-a"><rect x="20" y="45" width="70" height="40"/></g>
  <g id="node-b"><rect x="170" y="45" width="70" height="40"/></g>
  <g id="a-to-b"><path d="M90 65 H170"/></g>
</svg>''',
        encoding="utf-8",
    )
    result = stamp_visual_metadata(lock_path, svg_path, svg_path)
    assert result["status"] == "passed"
    stamped = svg_path.read_text(encoding="utf-8")
    assert 'data-notation-role="boundary"' in stamped
    assert 'data-notation-role="external-system"' in stamped
    assert 'data-notation-role="service"' in stamped


def test_stamp_visual_metadata_adds_v4_root_identity(tmp_path: Path) -> None:
    lock = _v4_architecture_lock()
    lock_path = tmp_path / "diagram_lock.yaml"
    svg_path = tmp_path / "visual.svg"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    svg_path.write_text(
        '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120">
  <g id="runtime"><rect x="5" y="5" width="250" height="110"/></g>
  <g id="node-a"><rect x="20" y="45" width="70" height="40"/></g>
  <g id="node-b"><rect x="170" y="45" width="70" height="40"/></g>
  <g id="a-to-b"><path d="M90 65 H170"/></g>
</svg>''',
        encoding="utf-8",
    )
    result = stamp_visual_metadata(lock_path, svg_path, svg_path)
    assert result["status"] == "passed"
    assert result["root_metadata"] == {
        "data-pack-identity": "precise-industrial",
        "data-renderer-family": "architecture",
        "data-composition-rhythm": "focal",
    }
    stamped = svg_path.read_text(encoding="utf-8")
    assert 'data-pack-identity="precise-industrial"' in stamped
    assert 'data-renderer-family="architecture"' in stamped


def test_stamp_visual_metadata_adds_v5_visual_tiers(tmp_path: Path) -> None:
    lock = _v5_architecture_lock()
    lock_path = tmp_path / "diagram_lock.yaml"
    svg_path = tmp_path / "visual.svg"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    svg_path.write_text(
        '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120">
  <g id="runtime"><rect x="5" y="5" width="250" height="110"/></g>
  <g id="node-a"><rect x="20" y="45" width="70" height="40"/></g>
  <g id="node-b"><rect x="170" y="45" width="70" height="40"/></g>
  <g id="a-to-b"><path d="M90 65 H170"/></g>
</svg>''',
        encoding="utf-8",
    )
    assert stamp_visual_metadata(lock_path, svg_path, svg_path)["status"] == "passed"
    stamped = svg_path.read_text(encoding="utf-8")
    assert 'data-diagram-id="runtime"' in stamped and 'data-visual-tier="context"' in stamped
    assert 'data-diagram-id="node-a"' in stamped and 'data-visual-tier="primary"' in stamped
    assert 'data-diagram-id="node-b"' in stamped and 'data-visual-tier="focal"' in stamped


def test_metadata_reserialization_does_not_bypass_noop_gate(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path, visual_shifted=False)
    result = stamp_visual_metadata(
        diagram_dir / "diagram_lock.yaml",
        diagram_dir / "visual.svg",
        diagram_dir / "visual.svg",
    )
    assert result["status"] == "passed"
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        diagram_dir / "visual.svg",
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert any("visual stage was a no-op" in error for error in report["visual"]["errors"])


def test_pack_report_fails_when_generated_diagram_check_is_missing(tmp_path: Path) -> None:
    (tmp_path / "diagram_manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "project": "Example",
                "mode": "diagram-pack",
                "source_summary": "Example",
                "diagrams": [
                    {
                        "id": "architecture-overview",
                        "title": "Architecture Overview",
                        "type": "architecture",
                        "status": "generated",
                        "source_format": "graphviz",
                        "directory": "architecture-overview",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    diagram_dir = tmp_path / "architecture-overview"
    diagram_dir.mkdir()
    (diagram_dir / "visual.svg").write_text(_svg(), encoding="utf-8")
    (diagram_dir / "source.dot").write_text("digraph example {}", encoding="utf-8")

    report = build_embed_blocks(tmp_path)
    assert report["status"] == "failed"
    assert report["diagrams"][0]["check_status"] == "missing"


def test_pack_report_rejects_missing_preview_even_with_stale_pass_report(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    build_check_report(diagram_dir)
    _write_manifest(tmp_path)
    (diagram_dir / "preview.png").unlink()
    report = build_embed_blocks(tmp_path)
    assert report["status"] == "failed"
    assert report["diagrams"][0]["preview"] is None


def test_manifest_and_pack_report_pass_only_when_lock_contract_matches(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    build_check_report(diagram_dir)
    manifest_path = _write_manifest(tmp_path)

    manifest_report = validate_manifest_file(manifest_path, root=tmp_path)
    assert manifest_report["status"] == "passed"
    pack_report = build_embed_blocks(tmp_path)
    assert pack_report["status"] == "passed_with_warnings"
    assert pack_report["diversity"]["generated_count"] == 1

    _write_manifest(tmp_path, source_format="mermaid")
    mismatch_report = validate_manifest_file(manifest_path, root=tmp_path)
    assert mismatch_report["status"] == "failed"
    assert any("does not match lock" in error for error in mismatch_report["errors"])


def test_v3_manifest_rejects_legacy_lock_even_when_view_fields_match(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    lock_path = diagram_dir / "diagram_lock.yaml"
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    lock.update(
        {
            "viewpoint_family": "structure",
            "reading_question": "Which components handle the request?",
            "notation_profile": "architecture-structure",
        }
    )
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    manifest_path = _write_manifest(tmp_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["contract_version"] = 3
    manifest["diagrams"][0].update(
        {
            "viewpoint_family": "structure",
            "reading_question": "Which components handle the request?",
            "notation_profile": "architecture-structure",
        }
    )
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    report = validate_manifest_file(manifest_path, root=tmp_path)
    assert report["status"] == "failed"
    assert any("requires a v3 lock" in error for error in report["errors"])


def test_v3_manifest_enforces_distinct_questions_and_pack_diversity() -> None:
    diagrams = []
    for index in range(4):
        diagrams.append(
            {
                "id": f"flow-{index}",
                "title": f"Flow {index}",
                "type": "flow",
                "viewpoint_family": "behavior",
                "reading_question": f"How does flow {index} progress?",
                "notation_profile": "activity-flow",
                "status": "generated",
                "reason": "The source defines ordered work.",
                "source_refs": [f"source.md#{index}"],
                "style_id": "clean-technical",
                "source_format": "mermaid",
                "enhancement_level": "medium",
                "layout_pattern": "linear-flow",
                "directory": f"flow-{index}",
            }
        )
    manifest = {
        "contract_version": 3,
        "project": "Diversity example",
        "mode": "diagram-pack",
        "source_summary": "Four source-grounded procedures.",
        "diagrams": diagrams,
    }
    without_reason = validate_manifest(manifest)
    assert without_reason["status"] == "failed"
    assert without_reason["diversity"]["viewpoint_counts"] == {"behavior": 4}
    assert any("diversity_reason" in error for error in without_reason["errors"])

    manifest["diversity_reason"] = (
        "The source contains four independent procedures and no fact-complete alternate view."
    )
    assert validate_manifest(manifest)["status"] == "passed"

    diagrams[1]["reading_question"] = diagrams[0]["reading_question"]
    duplicate = validate_manifest(manifest)
    assert duplicate["status"] == "failed"
    assert any("distinct reading questions" in error for error in duplicate["errors"])


def test_v4_manifest_carries_custom_pack_identity_and_type_treatment() -> None:
    manifest = {
        "contract_version": 4,
        "project": "Identity example",
        "mode": "diagram-pack",
        "source_summary": "One source-grounded architecture view.",
        "pack_identity": _pack_identity(),
        "diagrams": [
            {
                "id": "architecture-overview",
                "title": "Architecture Overview",
                "type": "architecture",
                "viewpoint_family": "structure",
                "reading_question": "Which components handle the request?",
                "notation_profile": "architecture-structure",
                "status": "generated",
                "reason": "The source defines components and runtime boundaries.",
                "source_refs": ["architecture.md#overview"],
                "source_format": "graphviz",
                "enhancement_level": "strong",
                "layout_pattern": "layered-system",
                "directory": "architecture-overview",
                "diagram_treatment": {
                    "renderer_family": "architecture",
                    "composition_rhythm": "focal",
                    "emphasis": "Runtime boundary and primary path.",
                    "boundary_style": "Explicit containment boundary.",
                    "connector_style": "Orthogonal dependency line.",
                },
            }
        ],
    }
    report = validate_manifest(manifest)
    assert report["status"] == "passed"
    assert report["pack_identity"]["behavior_mode"] == "custom"
    assert report["diversity"]["treatment_counts"]

    manifest["diagrams"][0]["diagram_treatment"]["renderer_family"] = "generic-card"
    report = validate_manifest(manifest)
    assert report["status"] == "failed"
    assert any("must equal the locked diagram type" in error for error in report["errors"])


def test_v4_pack_gate_rejects_cross_type_rounded_card_collapse() -> None:
    signature = "rounded-rect|rounded-rect|orthogonal|dense"
    diagrams = [
        {
            "id": f"diagram-{index}",
            "type": diagram_type,
            "visual_identity": {
                "checked": True,
                "pack_identity": "precise-industrial",
                "signature": signature,
                "card_like": True,
            },
        }
        for index, diagram_type in enumerate(
            ("architecture", "flow", "state", "sequence")
        )
    ]
    manifest = {"contract_version": 4}
    report = analyze_pack_visual_identity(diagrams, manifest)
    assert report["errors"]
    assert report["suspicious_card_signatures"][signature]["count"] == 4

    manifest["visual_diversity_reason"] = (
        "The source contains only equivalent rectangular boundary facts across these views."
    )
    assert analyze_pack_visual_identity(diagrams, manifest)["errors"] == []


def test_render_svg_copies_valid_source_and_rejects_invalid_xml(tmp_path: Path) -> None:
    valid_source = tmp_path / "source.svg"
    valid_output = tmp_path / "semantic.svg"
    valid_source.write_text(_svg(), encoding="utf-8")
    valid_report = render_svg(valid_source, valid_output)
    assert valid_report["status"] == "passed"
    assert valid_output.read_text(encoding="utf-8") == valid_source.read_text(encoding="utf-8")

    invalid_source = tmp_path / "invalid.svg"
    invalid_source.write_text("<svg>", encoding="utf-8")
    invalid_report = render_svg(invalid_source, tmp_path / "invalid-output.svg")
    assert invalid_report["status"] == "failed"
