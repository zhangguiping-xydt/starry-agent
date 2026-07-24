from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "starry-diagram"
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_check_report import build_check_report  # noqa: E402
from build_embed_blocks import build_embed_blocks  # noqa: E402
from profiles import load_profiles  # noqa: E402
from render_svg import render_svg  # noqa: E402
from stamp_visual_metadata import stamp_visual_metadata  # noqa: E402
from validate_diagram_lock import validate_lock  # noqa: E402
from validate_diagram_manifest import validate_manifest_file  # noqa: E402
from validate_semantic_source import validate_semantic_source  # noqa: E402
from validate_visual_svg import validate_visual_svg  # noqa: E402


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
            "title_size": 22,
            "node_size": 13,
            "edge_label_size": 11,
            "min_font_size": 10,
        },
        "geometry": {
            "node_padding_x": 18,
            "node_padding_y": 12,
            "cluster_padding": 24,
            "node_gap": 32,
            "rank_gap": 56,
            "corner_radius": 8,
        },
        "connectors": {"width": 1.6, "arrow_size": 7, "routing": "orthogonal"},
    }


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
        "canvas": {"mode": "fixed", "width": 200, "height": 100, "viewBox": "0 0 200 100"},
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
        "style_tokens": _style_tokens(),
    }


def _svg(*, width: int = 200, shifted: bool = False, include_edge_endpoints: bool = True) -> str:
    edge_metadata = ' data-from="node-a" data-to="node-b"' if include_edge_endpoints else ""
    node_b_x = 130 if shifted else 120
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 100">
  <rect width="{width}" height="100" fill="#f8fafc"/>
  <g data-diagram-id="runtime" data-diagram-kind="group" data-members="node-a,node-b">
    <text x="8" y="14" font-family="Noto Sans CJK SC" font-size="10" fill="#0f172a">Runtime</text>
  </g>
  <g data-diagram-id="node-a" data-diagram-kind="node">
    <rect x="20" y="30" width="50" height="30" fill="#ffffff" stroke="#2563eb"/>
    <text x="25" y="49" font-family="Noto Sans CJK SC" font-size="13" fill="#0f172a">Node A</text>
  </g>
  <g data-diagram-id="node-b" data-diagram-kind="node">
    <rect x="{node_b_x}" y="30" width="50" height="30" fill="#ffffff" stroke="#2563eb"/>
    <text x="{node_b_x + 5}" y="49" font-family="Noto Sans CJK SC" font-size="13" fill="#0f172a">Node B</text>
  </g>
  <g data-diagram-id="a-to-b" data-diagram-kind="edge"{edge_metadata}>
    <path d="M70 45 H{node_b_x}" fill="none" stroke="#94a3b8"/>
    <text x="86" y="40" font-family="Noto Sans CJK SC" font-size="11" fill="#64748b">Calls</text>
  </g>
</svg>'''


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


def test_lock_rejects_enhancement_below_type_minimum() -> None:
    report = validate_lock(_architecture_lock(enhancement="light"))
    assert report["status"] == "failed"
    assert any("below the strong minimum" in error for error in report["errors"])


def test_lock_rejects_renderer_outside_type_profile() -> None:
    report = validate_lock(_architecture_lock(source_format="mermaid"))
    assert report["status"] == "failed"
    assert any("is not allowed" in error for error in report["errors"])


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
    without_reason = validate_lock(lock)
    assert without_reason["status"] == "failed"
    assert any("requires renderer_reason" in error for error in without_reason["errors"])

    lock["renderer_reason"] = "PlantUML is unavailable in the target environment."
    with_reason = validate_lock(lock)
    assert with_reason["status"] == "passed"
    assert any("non-preferred" in warning for warning in with_reason["warnings"])


def test_visual_rejects_medium_or_strong_noop(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path, visual_shifted=False)
    report = validate_visual_svg(
        diagram_dir / "diagram_lock.yaml",
        diagram_dir / "visual.svg",
        semantic_path=diagram_dir / "semantic.svg",
    )
    assert report["status"] == "failed"
    assert any("visual stage was a no-op" in error for error in report["visual"]["errors"])


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
  <text font-family="Noto Sans CJK SC" font-size="8" fill="#0f172a">Unexpected</text>
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


def test_manifest_and_pack_report_pass_only_when_lock_contract_matches(tmp_path: Path) -> None:
    diagram_dir = _write_diagram(tmp_path)
    build_check_report(diagram_dir)
    manifest_path = _write_manifest(tmp_path)

    manifest_report = validate_manifest_file(manifest_path, root=tmp_path)
    assert manifest_report["status"] == "passed"
    assert build_embed_blocks(tmp_path)["status"] == "passed"

    _write_manifest(tmp_path, source_format="mermaid")
    mismatch_report = validate_manifest_file(manifest_path, root=tmp_path)
    assert mismatch_report["status"] == "failed"
    assert any("does not match lock" in error for error in mismatch_report["errors"])


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
