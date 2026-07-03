from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from repo_to_skill import __version__
from repo_to_skill.evals.runner import run_eval
from repo_to_skill.reverse.callable_capabilities import build_callable_capabilities
from repo_to_skill.reverse.capability_evidence import build_capability_evidence
from repo_to_skill.reverse.capability_graph import build_capability_graph
from repo_to_skill.reverse.confidence_report import build_confidence_report
from repo_to_skill.reverse.project_profile import build_project_profile
from repo_to_skill.reverse.skill_spec import build_skill_spec
from repo_to_skill.reverse.verification import verify_static_outputs
from repo_to_skill.scanner.filesystem import scan_repository
from repo_to_skill.skillgen.installer import install_skill
from repo_to_skill.skillgen.planner import (
    plan_callable_bundle,
    plan_callable_composite,
    plan_callable_skills,
    plan_skill,
)
from repo_to_skill.skillgen.renderer import (
    render_callable_bundle,
    render_callable_composite,
    render_callable_skills,
    render_skill,
    render_task_workflow,
)
from repo_to_skill.skillgen.validator import SkillValidationReport, validate_skill
from repo_to_skill.skillgen.workflow_hints import WorkflowHints, load_workflow_hints
from repo_to_skill.skillgen.workflow_planner import plan_task_workflow
from repo_to_skill.workspace.paths import resolve_target_and_output
from repo_to_skill.workspace.store import ArtifactStore

app = typer.Typer(help="Local-first repository-to-skill tooling.")
console = Console()


@app.callback()
def cli() -> None:
    """Local-first repository-to-skill tooling."""


def _run_analysis(target: Path, output: Path) -> tuple[Path, str]:
    store = ArtifactStore(target, output)
    scan = scan_repository(store.target_root)
    profile = build_project_profile(scan, store.target_root)
    evidence = build_capability_evidence(profile, scan)
    graph = build_capability_graph(evidence)
    spec = build_skill_spec(profile, graph)
    verification = verify_static_outputs(evidence, graph, spec)
    confidence_report = build_confidence_report(profile, evidence, verification)
    callable_capabilities = build_callable_capabilities(scan, store.target_root)

    store.write_json("scan.json", scan)
    store.write_json("profile.json", profile)
    store.write_json("capability_evidence.json", evidence)
    store.write_json("capability_graph.json", graph)
    store.write_yaml("skill_spec.yaml", spec)
    store.write_json("verification_report.json", verification)
    store.write_markdown("confidence-report.md", confidence_report)
    store.write_json("callable_capabilities.json", callable_capabilities)
    return store.output_root, verification.status


SUPPORTED_CALLABLE_FRAMEWORKS = (
    ".NET — ASP.NET IHttpHandler (.ashx), Web API controllers ([ApiController]/[Http*])",
    "Java — Spring (@RestController/@Controller), JAX-RS (@Path/@GET/@POST)",
    "Python — FastAPI (@app.get/post), Flask (@app.route)",
)
_SUPPORTED_CALLABLE_LANGUAGES = {"Python", "Java", "C#", "ASP.NET"}


def _no_interface_guidance(languages: list[str]) -> str:
    """Explain WHY nothing was detected and what to do, instead of a dead end."""
    detected = [str(language) for language in languages if str(language)]
    supported_present = sorted(set(detected) & _SUPPORTED_CALLABLE_LANGUAGES)
    lines = ["No callable HTTP interfaces were detected."]
    if detected:
        lines += ["", "Detected languages: " + ", ".join(detected)]
    lines += ["", "Callable detection currently supports:"]
    lines += [f"  - {framework}" for framework in SUPPORTED_CALLABLE_FRAMEWORKS]
    lines.append("")
    if supported_present:
        lines.append(
            "Supported languages are present (" + ", ".join(supported_present) + ") but no routes "
            "were recognized. Check that the HTTP layer uses a framework above, and that route files "
            "were not skipped (binary, larger than 1 MiB, or under an ignored directory)."
        )
    else:
        lines.append(
            "This stack is not recognized yet (Node/Express, Go, Ruby, and others are not supported). "
            "Issues and contributions are welcome."
        )
    return "\n".join(lines)


def _print_validation(report: SkillValidationReport) -> None:
    console.print(f"Validation: {report.status}")
    for finding in report.findings:
        console.print(f"- {finding}")


def _install_and_report(skill_root: Path) -> None:
    for destination in install_skill(skill_root):
        console.print(f"Installed skill: {destination}", soft_wrap=True)


def _generate_skill(
    target: Path, analysis: Path, output: Path, *, install: bool = False, language: str = "auto"
) -> SkillValidationReport:
    target_root, output_root = resolve_target_and_output(target, output)
    plan = plan_skill(target_root, analysis, language=language)
    skill_root = render_skill(plan, output_root)
    report = validate_skill(skill_root)
    console.print(f"Generated skill: {skill_root}", soft_wrap=True)
    _print_validation(report)
    if install and report.status == "PASS":
        _install_and_report(skill_root)
    return report


def _generate_callable_skills(
    target: Path, analysis: Path, output: Path, *, install: bool = False, language: str = "auto"
) -> bool:
    target_root, output_root = resolve_target_and_output(target, output)
    plan = plan_callable_skills(target_root, analysis, language=language)
    if not plan.interfaces:
        console.print(_no_interface_guidance(plan.profile.get("languages") or []))
        return True
    all_pass = True
    for pack in render_callable_skills(plan, output_root):
        report = validate_skill(pack)
        console.print(f"Generated callable skill: {pack}", soft_wrap=True)
        _print_validation(report)
        if report.status != "PASS":
            all_pass = False
        elif install:
            _install_and_report(pack)
    return all_pass


def _parse_slugs(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _generate_callable_bundle(
    target: Path,
    analysis: Path,
    output: Path,
    *,
    need: str,
    max_interfaces: int,
    selected_slugs: str | None,
    selection_json: Path | None,
    install: bool = False,
    language: str = "auto",
) -> bool:
    target_root, output_root = resolve_target_and_output(target, output)
    base = plan_callable_skills(target_root, analysis, language=language)
    if not base.interfaces:
        console.print(_no_interface_guidance(base.profile.get("languages") or []))
        return True
    plan = plan_callable_bundle(
        target_root,
        analysis,
        need=need,
        selected_slugs=_parse_slugs(selected_slugs),
        selection_json=selection_json,
        max_interfaces=max_interfaces,
        language=language,
    )
    bundle = render_callable_bundle(plan, output_root)
    report = validate_skill(bundle)
    console.print(f"Generated callable bundle: {bundle}", soft_wrap=True)
    _print_validation(report)
    if install and report.status == "PASS":
        _install_and_report(bundle)
    return report.status == "PASS"


def _generate_callable_composite(
    target: Path,
    analysis: Path,
    output: Path,
    *,
    goal: str,
    max_interfaces: int,
    selected_slugs: str | None,
    selection_json: Path | None,
    install: bool = False,
    language: str = "auto",
) -> bool:
    target_root, output_root = resolve_target_and_output(target, output)
    base = plan_callable_skills(target_root, analysis, language=language)
    if not base.interfaces:
        console.print(_no_interface_guidance(base.profile.get("languages") or []))
        return True
    plan = plan_callable_composite(
        target_root,
        analysis,
        goal=goal,
        selected_slugs=_parse_slugs(selected_slugs),
        selection_json=selection_json,
        max_interfaces=max_interfaces,
        language=language,
    )
    composite = render_callable_composite(plan, output_root)
    report = validate_skill(composite)
    console.print(f"Generated callable composite: {composite}", soft_wrap=True)
    _print_validation(report)
    if install and report.status == "PASS":
        _install_and_report(composite)
    return report.status == "PASS"


def _analysis_with_hinted_unknown_interfaces_as_read(
    analysis: Path,
    hints: WorkflowHints | None,
) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if hints is None:
        return analysis, None

    analysis_root = analysis.expanduser().resolve()
    if analysis_root.is_file():
        analysis_root = analysis_root.parent
    capabilities_path = analysis_root / "callable_capabilities.json"
    if not capabilities_path.is_file():
        return analysis, None

    hinted_slugs = {step.slug for workflow in hints.workflows for step in workflow.steps}
    capabilities = json.loads(capabilities_path.read_text(encoding="utf-8"))
    changed = False
    for interface in capabilities.get("interfaces") or []:
        if not isinstance(interface, dict) or interface.get("slug") not in hinted_slugs:
            continue
        if str(interface.get("side_effects") or "unknown").lower() == "unknown":
            interface["side_effects"] = "read"
            changed = True

    if not changed:
        return analysis, None

    temporary = tempfile.TemporaryDirectory()
    temporary_root = Path(temporary.name)
    shutil.copytree(analysis_root, temporary_root, dirs_exist_ok=True)
    (temporary_root / "callable_capabilities.json").write_text(
        json.dumps(capabilities, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return temporary_root, temporary


def _generate_task_workflow(
    target: Path,
    analysis: Path,
    output: Path,
    *,
    need: str,
    workflow_hints: Path | None,
    install: bool = False,
    language: str = "auto",
) -> bool:
    target_root, output_root = resolve_target_and_output(target, output)
    base = plan_callable_skills(target_root, analysis, language=language)
    if not base.interfaces:
        console.print(_no_interface_guidance(base.profile.get("languages") or []))
        return True

    hints = load_workflow_hints(workflow_hints) if workflow_hints else None
    workflow_analysis, temporary_analysis = _analysis_with_hinted_unknown_interfaces_as_read(analysis, hints)

    try:
        try:
            plan = plan_task_workflow(
                target_root,
                workflow_analysis,
                hints=hints,
                need_summary=need,
                language=language,
            )
        except ValueError as exc:
            console.print(f"cannot generate task-workflow: {exc}")
            return False
    finally:
        if temporary_analysis is not None:
            temporary_analysis.cleanup()

    skill = render_task_workflow(plan, output_root)
    report = validate_skill(skill)
    console.print(f"Generated task-workflow skill: {skill}", soft_wrap=True)
    _print_validation(report)
    if install and report.status == "PASS":
        _install_and_report(skill)
    return report.status == "PASS"


@app.command()
def analyze(
    target: Path = typer.Argument(..., help="Local repository to analyze."),
    output: Path = typer.Option(..., "--output", "-o", help="Directory for generated artifacts."),
) -> None:
    """Analyze a local repository and write local-first skill artifacts."""
    try:
        output_root, status = _run_analysis(target, output)
    except ValueError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    console.print(f"Analysis complete: {output_root}")
    if status != "PASS":
        raise typer.Exit(code=1)


@app.command()
def generate(
    target: Path = typer.Argument(..., help="Local repository the analysis describes."),
    analysis: Path = typer.Option(..., "--analysis", help="Analysis run directory or profile.json."),
    output: Path = typer.Option(..., "--output", "-o", help="Skill output directory."),
    mode: str = typer.Option(
        "repo-map",
        "--mode",
        help="Skill kind to generate: 'repo-map', 'callable', 'callable-bundle', 'callable-composite', or 'task-workflow'.",
    ),
    need: str = typer.Option("", "--need", help="User goal for callable-bundle interface selection."),
    workflow_hints: Path | None = typer.Option(
        None,
        "--workflow-hints",
        help="JSON file with predefined workflows for --mode task-workflow.",
    ),
    goal: str = typer.Option(
        "",
        "--goal",
        help="Business goal for callable-composite (A->B->... chain). Required for callable-composite mode.",
    ),
    max_interfaces: int = typer.Option(12, "--max-interfaces", help="Maximum callable interfaces in a bundle or composite."),
    selected_slugs: str | None = typer.Option(
        None,
        "--selected-slugs",
        help="Comma-separated callable interface slugs selected by an agent or user.",
    ),
    selection_json: Path | None = typer.Option(
        None,
        "--selection-json",
        help="JSON file with need_summary, selected_slugs, and selection_source.",
    ),
    install: bool = typer.Option(
        False,
        "--install",
        help="After a PASS, copy the skill into ~/.claude/skills and ~/.agents/skills for immediate agent use.",
    ),
    language: str = typer.Option(
        "auto",
        "--language",
        help="Output language for generated skill prose: 'auto' (detect from goal/need), 'en', or 'zh-CN'.",
    ),
) -> None:
    """Generate a reviewable local AI coding agent skill pack from existing analysis artifacts."""
    if mode not in {"repo-map", "callable", "callable-bundle", "callable-composite", "task-workflow"}:
        console.print(
            f"Unknown mode: {mode}; expected 'repo-map', 'callable', 'callable-bundle', "
            "'callable-composite', or 'task-workflow'."
        )
        raise typer.Exit(code=1)
    try:
        if mode == "callable":
            all_pass = _generate_callable_skills(target, analysis, output, install=install, language=language)
        elif mode == "callable-bundle":
            all_pass = _generate_callable_bundle(
                target,
                analysis,
                output,
                need=need,
                max_interfaces=max_interfaces,
                selected_slugs=selected_slugs,
                selection_json=selection_json,
                install=install,
                language=language,
            )
        elif mode == "callable-composite":
            if not goal.strip():
                console.print("--goal is required for --mode callable-composite.")
                raise typer.Exit(code=1)
            all_pass = _generate_callable_composite(
                target,
                analysis,
                output,
                goal=goal,
                max_interfaces=max_interfaces if max_interfaces >= 2 else 2,
                selected_slugs=selected_slugs,
                selection_json=selection_json,
                install=install,
                language=language,
            )
        elif mode == "task-workflow":
            if not need.strip():
                console.print("--need is required for --mode task-workflow.")
                raise typer.Exit(code=1)
            all_pass = _generate_task_workflow(
                target,
                analysis,
                output,
                need=need,
                workflow_hints=workflow_hints,
                install=install,
                language=language,
            )
        else:
            all_pass = _generate_skill(target, analysis, output, install=install, language=language).status == "PASS"
    except ValueError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc
    if not all_pass:
        raise typer.Exit(code=1)


@app.command(name="validate")
def validate_command(
    skill_path: Path = typer.Argument(..., help="Skill directory to validate."),
) -> None:
    """Validate a generated skill directory for required shape and safety boundaries."""
    report = validate_skill(skill_path)
    _print_validation(report)
    if report.status != "PASS":
        raise typer.Exit(code=1)


@app.command()
def compose(
    target: Path = typer.Argument(..., help="Local repository to analyze and turn into a skill."),
    output: Path = typer.Option(..., "--output", "-o", help="Skill output directory."),
    workdir: Path = typer.Option(..., "--workdir", help="Analysis work directory."),
    language: str = typer.Option(
        "auto",
        "--language",
        help="Output language for generated skill prose: 'auto' (detect from goal/need), 'en', or 'zh-CN'.",
    ),
) -> None:
    """Run local analyze -> generate -> validate without runtime registration or network use."""
    try:
        analysis_root, status = _run_analysis(target, workdir)
        console.print(f"Analysis complete: {analysis_root}")
        if status != "PASS":
            raise typer.Exit(code=1)
        report = _generate_skill(target, analysis_root, output, language=language)
    except ValueError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc
    if report.status != "PASS":
        raise typer.Exit(code=1)


@app.command(name="eval")
def eval_command(
    case: str = typer.Option(..., "--case", help="Evaluation case name to run."),
    workspace: Path | None = typer.Option(
        None,
        "--workspace",
        help="Optional workspace for eval outputs; defaults to a temporary directory.",
    ),
) -> None:
    """Run deterministic local evals without network, installs, or runtime registration."""
    try:
        result = run_eval(case, workspace)
    except ValueError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    console.print(f"Eval case: {result.case_name}")
    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        console.print(f"- {check.name}: {status} — {check.detail}")
    console.print(f"Eval result: {result.status}")
    if not result.passed:
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Report local environment checks without network or repository writes."""
    python_ok = sys.version_info >= (3, 11)
    package_dir = Path(__file__).resolve().parent
    package_files_ok = package_dir.exists() and package_dir.is_dir()

    try:
        importlib.import_module("repo_to_skill")
    except ImportError as exc:
        package_import_ok = False
        package_import_detail = str(exc)
    else:
        package_import_ok = True
        package_import_detail = "repo_to_skill"

    table = Table(title=f"repo-to-skill doctor {__version__}")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    table.add_row(
        "Python version",
        "ok" if python_ok else "unsupported",
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )
    table.add_row(
        "Package import",
        "ok" if package_import_ok else "failed",
        package_import_detail,
    )
    table.add_row(
        "Package files",
        "ok" if package_files_ok else "missing",
        str(package_dir),
    )
    table.add_row(
        "Network access",
        "disabled",
        "doctor performs local checks only",
    )
    table.add_row(
        "Repository writes",
        "disabled",
        "doctor does not write target repositories",
    )

    console.print(table)

    if not python_ok or not package_import_ok or not package_files_ok:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
