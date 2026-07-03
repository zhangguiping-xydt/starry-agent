---
name: starry-diagram
description: Use when creating design diagrams, diagram packs, architecture diagrams, ER diagrams, sequence diagrams, swimlane diagrams, business flows, data flows, deployment diagrams, state machines, event flows, or polished SVG diagrams from requirements, PRDs, technical designs, architecture notes, or design documents.
---

# Starry Diagram

## Overview

Create trustworthy diagram packs from source material. The semantic source is truth, enhanced SVG is presentation. Every visual output must preserve the semantic contract recorded in locks and reports.

## Mandatory Pipeline

Source intake → Diagram Strategist → `diagram_manifest.yaml` → `diagram_spec.md`/`diagram_lock.yaml` → Semantic track before visual track → Semantic quality gate → Visual track → Visual quality gate → `embed.md` and reports.

## Default diagram-pack mode

When the user does not specify a diagram type, evaluate architecture/business-architecture/flow/swimlane/sequence/er/state/data-flow/deployment/component/event-flow/concept. Each candidate status must be one of generated/skipped/needs_clarification with a source-grounded reason.

## Fact gate

Do not invent services, roles, fields, relationships, states, calls, events, or cardinalities. If a required fact is absent from source material, mark the diagram as skipped or needs_clarification instead of filling gaps.

## Required Artifacts

Each generated diagram directory must contain `diagram_spec.md`, `diagram_lock.yaml`, `source.*`, `semantic.svg` or `render_unavailable`, `visual.svg` or `visual_failed`, `embed.md`, and `check_report.json`. The pack root must contain `diagram_manifest.yaml` and `diagram_pack_report.json`. Diagrams marked `skipped` or `needs_clarification` only require a manifest entry; do not create semantic source, SVG files, or a diagram directory for them unless the user explicitly asks for a diagnostic directory.

## Semantic track before visual track

Build and validate the source representation first, then render semantic output, and only then enhance presentation. The semantic track owns nodes, edges, labels, participants, entities, states, messages, cardinalities, and required grouping.

## Visual track rule

Visual enhancement may improve layout, spacing, hierarchy, color, typography, and polish. visual.svg must not change semantics. Any visual result that adds, removes, renames, or re-wires semantic elements must fail the visual quality gate.

## References

- `references/strategist.md` for diagram pack planning and locks.
- `references/semantic-executor.md` for Mermaid/PlantUML/Graphviz/source routing.
- `references/visual-executor.md` for allowed visual enhancement.
- `references/quality-gate.md` for validation and failure handling.
- `references/output-contract.md` for artifact layout and embed blocks.

## Common Mistakes

- Starting from a polished SVG before creating `diagram_lock.yaml`.
- Generating an ER diagram when fields, keys, or cardinalities are missing.
- Naming the same node differently across diagrams, such as `Auth Service` in one diagram and `Authentication API` in another without a glossary mapping; use one canonical label/id from the pack glossary.
- Treating `visual.svg` as a place to add unstated relationships.
- Omitting `check_report.json` when a renderer is unavailable.
- Collapsing skipped and needs_clarification into the same state.
