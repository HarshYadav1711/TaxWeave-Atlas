"""
Command-line entrypoint for TaxWeave Atlas.

Commands are thin wrappers over library functions; logging uses the stdlib only.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from taxweave_atlas.exceptions import TaxWeaveError


def _configure_logging(*, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s", force=True)


def _emit_delivery_report(report: object) -> None:
    click.echo(report.summary_line())
    for w in report.warnings:
        click.echo(f"  WARNING: {w}", err=True)
    for msg in report.errors:
        click.echo(f"  ERROR: {msg}", err=True)
    for slug, rec in sorted(report.per_dataset.items()):
        if not rec.ok:
            for err in rec.errors:
                click.echo(f"  [{slug}] {err}", err=True)


@click.group()
@click.version_option(package_name="taxweave-atlas")
@click.option("-v", "--verbose", is_flag=True, help="DEBUG logging to stderr")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Synthetic tax datasets: generate, validate, render PDFs (all local)."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _configure_logging(verbose=verbose)


def _run_plan_only(output: Path, master_seed: int, count: int, complexity: str | None) -> Path:
    from taxweave_atlas.orchestration.batch import write_foundation_batch_plan

    return write_foundation_batch_plan(
        output,
        master_seed=master_seed,
        count=count,
        complexity_level=complexity,
    )


def _run_generation(
    output: Path,
    master_seed: int,
    count: int,
    complexity: str | None,
    state: str | None,
    tax_year: int | None,
    *,
    write_pdfs: bool = True,
) -> None:
    from taxweave_atlas.generation.batch_runner import run_case_generation_batch

    run_case_generation_batch(
        output,
        master_seed=master_seed,
        count=count,
        complexity_override=complexity,
        state_override=state,
        tax_year_override=tax_year,
        write_pdfs=write_pdfs,
    )


@main.command("pilot")
@click.option("--count", type=int, default=10, show_default=True)
@click.option("--seed", type=int, default=42, show_default=True, help="Master RNG seed")
@click.option("--output", type=click.Path(path_type=Path), required=True, help="Output root")
@click.option("--complexity", type=str, default=None, help="easy | medium | moderately_complex")
@click.option("--state", type=str, default=None, help="CA | TX | NY | IL | FL")
@click.option("--tax-year", type=int, default=None, help="Must be in application.yaml active years")
@click.option("--plan-only", is_flag=True, help="Write batch plan only (no cases)")
@click.option("--no-pdfs", is_flag=True, help="Skip PDFs; write case.json + questionnaire.json only")
def cmd_pilot(
    count: int,
    seed: int,
    output: Path,
    complexity: str | None,
    state: str | None,
    tax_year: int | None,
    plan_only: bool,
    no_pdfs: bool,
) -> None:
    """Generate a small batch (default 10 datasets)."""
    try:
        if plan_only:
            path = _run_plan_only(output, seed, count, complexity)
            click.echo(f"Wrote batch plan ({count} slots) → {path}")
        else:
            _run_generation(
                output, seed, count, complexity, state, tax_year, write_pdfs=not no_pdfs
            )
            if no_pdfs:
                click.echo(f"Wrote {count} cases (staging JSON only) → {output / '_staging' / 'datasets'}")
            else:
                click.echo(
                    f"Wrote {count} datasets → deliverable PDFs: {output / 'datasets'}; "
                    f"internal: {output / '_staging' / 'datasets'}"
                )
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e


@main.command("generate")
@click.option("--count", type=int, default=2000, show_default=True)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--complexity", type=str, default=None, help="easy | medium | moderately_complex")
@click.option("--state", type=str, default=None)
@click.option("--tax-year", type=int, default=None)
@click.option("--plan-only", is_flag=True)
@click.option("--no-pdfs", is_flag=True)
def cmd_generate(
    count: int,
    seed: int,
    output: Path,
    complexity: str | None,
    state: str | None,
    tax_year: int | None,
    plan_only: bool,
    no_pdfs: bool,
) -> None:
    """Generate a large batch (default 2000 datasets)."""
    try:
        if plan_only:
            path = _run_plan_only(output, seed, count, complexity)
            click.echo(f"Wrote batch plan ({count} slots) → {path}")
        else:
            _run_generation(
                output, seed, count, complexity, state, tax_year, write_pdfs=not no_pdfs
            )
            if no_pdfs:
                click.echo(f"Wrote {count} cases (staging JSON only) → {output / '_staging' / 'datasets'}")
            else:
                click.echo(
                    f"Wrote {count} datasets → deliverable PDFs: {output / 'datasets'}; "
                    f"internal: {output / '_staging' / 'datasets'}"
                )
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e


@main.command("validate-batch")
@click.argument("batch_root", type=click.Path(path_type=Path, exists=True, file_okay=False))
@click.option("--no-pdfs", is_flag=True, help="Skip PDF and checksum checks")
@click.option(
    "--strict-distribution",
    is_flag=True,
    help="Fail on mix drift vs config/generator/mix.yaml (default: warn)",
)
@click.option(
    "--no-per-dataset-audit",
    is_flag=True,
    help="Skip manifests/delivery_audits/<slug>.json per dataset",
)
@click.option("--no-batch-report", is_flag=True, help="Skip manifests/delivery_validation_report.json")
def cmd_validate_batch(
    batch_root: Path,
    no_pdfs: bool,
    strict_distribution: bool,
    no_per_dataset_audit: bool,
    no_batch_report: bool,
) -> None:
    """Validate a batch output tree (integrity, dedup, reconciliation, optional mix stats)."""
    from taxweave_atlas.delivery.batch_validate import validate_batch_output

    try:
        report = validate_batch_output(
            batch_root,
            expect_pdfs=not no_pdfs,
            strict_distribution=strict_distribution,
            write_per_dataset_audit=not no_per_dataset_audit,
            write_batch_report=not no_batch_report,
        )
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e

    _emit_delivery_report(report)
    if not report.ok:
        raise SystemExit(1)


@main.command("produce")
@click.argument("mode", type=click.Choice(["pilot", "weekly"]))
@click.option("--count", type=int, default=None, help="Override count (defaults: pilot 35, weekly 350)")
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--complexity", type=str, default=None)
@click.option("--state", type=str, default=None)
@click.option("--tax-year", type=int, default=None)
@click.option("--no-pdfs", is_flag=True)
@click.option("--strict-distribution", is_flag=True)
def cmd_produce(
    mode: str,
    count: int | None,
    seed: int,
    output: Path,
    complexity: str | None,
    state: str | None,
    tax_year: int | None,
    no_pdfs: bool,
    strict_distribution: bool,
) -> None:
    """Generate then run validate-batch (recommended for handoff)."""
    from taxweave_atlas.delivery.batch_validate import validate_batch_output
    from taxweave_atlas.generation.batch_runner import run_case_generation_batch

    n = count if count is not None else (35 if mode == "pilot" else 350)
    try:
        run_case_generation_batch(
            output,
            master_seed=seed,
            count=n,
            complexity_override=complexity,
            state_override=state,
            tax_year_override=tax_year,
            write_pdfs=not no_pdfs,
        )
        report = validate_batch_output(
            output,
            expect_pdfs=not no_pdfs,
            strict_distribution=strict_distribution,
        )
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e

    _emit_delivery_report(report)
    if not report.ok:
        raise SystemExit(1)


@main.command("validate-specs")
def cmd_validate_specs() -> None:
    """Check sample pack and config against application.yaml."""
    from taxweave_atlas.validation.specs import validate_specs_against_application_config

    try:
        validate_specs_against_application_config()
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e
    click.echo("specs OK")


@main.command("render-pdfs")
@click.argument("target", type=click.Path(path_type=Path, exists=True))
@click.option(
    "--reconcile",
    is_flag=True,
    help="Reconcile from source fields before render (stale case.json)",
)
def cmd_render_pdfs(target: Path, reconcile: bool) -> None:
    """Regenerate staging + PDF-only export from _staging/datasets/.../case.json or batch root."""
    from taxweave_atlas.pdf.pipeline import (
        load_case_from_path,
        render_dataset_deliverable_trees,
        render_pdfs_for_batch_output,
        resolve_staging_export_dirs,
    )

    try:
        if target.is_file() and target.name == "case.json":
            case = load_case_from_path(target)
            staging_dir, export_dir = resolve_staging_export_dirs(target)
            render_dataset_deliverable_trees(
                case, staging_dir, export_dir, reconcile_first=reconcile
            )
            click.echo(f"Rendered staging → {staging_dir}; export PDFs → {export_dir}")
            return
        case_path = target / "case.json"
        if case_path.is_file():
            case = load_case_from_path(case_path)
            staging_dir, export_dir = resolve_staging_export_dirs(case_path)
            render_dataset_deliverable_trees(
                case, staging_dir, export_dir, reconcile_first=reconcile
            )
            click.echo(f"Rendered staging → {staging_dir}; export PDFs → {export_dir}")
            return
        staging_ds = target / "_staging" / "datasets"
        if staging_ds.is_dir():
            n = render_pdfs_for_batch_output(target, reconcile_first=reconcile)
            click.echo(f"Rendered staging+export for {n} folders under {staging_ds}")
            return
        raise SystemExit(
            "Expected _staging/datasets/.../case.json, its parent folder, or a batch root with _staging/datasets/"
        )
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e


if __name__ == "__main__":
    main()
