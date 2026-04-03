from __future__ import annotations

from pathlib import Path

import click

from taxweave_atlas.exceptions import TaxWeaveError


@click.group()
@click.version_option(package_name="taxweave-atlas")
def main() -> None:
    """TaxWeave Atlas — local synthetic tax dataset tooling."""


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
@click.option("--count", type=int, default=10, show_default=True, help="Pilot batch size")
@click.option("--seed", type=int, default=42, show_default=True, help="Master RNG seed")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output root (datasets/ and manifests/ created beneath it)",
)
@click.option(
    "--complexity",
    type=str,
    default=None,
    help="Force complexity tier: easy | medium | moderately_complex",
)
@click.option(
    "--state",
    type=str,
    default=None,
    help="Force state of residence (CA, TX, NY, IL, FL)",
)
@click.option("--tax-year", type=int, default=None, help="Force tax year (active list in application.yaml)")
@click.option(
    "--plan-only",
    is_flag=True,
    default=False,
    help="Write batch_plan.json only (no synthetic cases)",
)
@click.option(
    "--no-pdfs",
    is_flag=True,
    default=False,
    help="Skip PDF bundle (case.json / questionnaire.json only)",
)
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
    """Pilot batch: by default generates synthetic cases + questionnaires."""
    try:
        if plan_only:
            path = _run_plan_only(output, seed, count, complexity)
            click.echo(f"Wrote batch plan only ({count} slots) to {path}")
        else:
            _run_generation(
                output, seed, count, complexity, state, tax_year, write_pdfs=not no_pdfs
            )
            click.echo(f"Wrote {count} synthetic datasets under {output / 'datasets'}")
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e


@main.command("generate")
@click.option("--count", type=int, default=2000, show_default=True, help="Full batch size")
@click.option("--seed", type=int, default=42, show_default=True, help="Master RNG seed")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output root (datasets/ and manifests/ created beneath it)",
)
@click.option(
    "--complexity",
    type=str,
    default=None,
    help="Force complexity tier: easy | medium | moderately_complex",
)
@click.option(
    "--state",
    type=str,
    default=None,
    help="Force state of residence (CA, TX, NY, IL, FL)",
)
@click.option("--tax-year", type=int, default=None, help="Force tax year")
@click.option(
    "--plan-only",
    is_flag=True,
    default=False,
    help="Write batch_plan.json only (no synthetic cases)",
)
@click.option(
    "--no-pdfs",
    is_flag=True,
    default=False,
    help="Skip PDF bundle (case.json / questionnaire.json only)",
)
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
    """Full batch: by default generates synthetic cases + questionnaires."""
    try:
        if plan_only:
            path = _run_plan_only(output, seed, count, complexity)
            click.echo(f"Wrote batch plan only ({count} slots) to {path}")
        else:
            _run_generation(
                output, seed, count, complexity, state, tax_year, write_pdfs=not no_pdfs
            )
            click.echo(f"Wrote {count} synthetic datasets under {output / 'datasets'}")
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e


@main.command("validate-specs")
def cmd_validate_specs() -> None:
    """Validate sample pack JSON + application/tax_rules files."""
    from taxweave_atlas.validation.specs import validate_specs_against_application_config

    try:
        validate_specs_against_application_config()
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e
    click.echo("specs OK")


@main.command("render-pdfs")
@click.argument(
    "target",
    type=click.Path(path_type=Path, exists=True),
    required=True,
)
@click.option(
    "--reconcile",
    is_flag=True,
    default=False,
    help="Re-run reconciliation before rendering (use if case.json predates reconciliation fields)",
)
def cmd_render_pdfs(target: Path, reconcile: bool) -> None:
    """Render PDFs for one dataset folder, one case.json file, or an entire batch output tree."""
    from taxweave_atlas.pdf.pipeline import (
        load_case_from_path,
        render_dataset_pdf_bundle,
        render_pdfs_for_batch_output,
    )

    try:
        if target.is_file() and target.name == "case.json":
            case = load_case_from_path(target)
            render_dataset_pdf_bundle(case, target.parent, reconcile_first=reconcile)
            click.echo(f"Rendered PDFs in {target.parent}")
            return
        case_path = target / "case.json"
        if case_path.is_file():
            case = load_case_from_path(case_path)
            render_dataset_pdf_bundle(case, target, reconcile_first=reconcile)
            click.echo(f"Rendered PDFs in {target}")
            return
        ds_root = target / "datasets"
        if ds_root.is_dir():
            n = render_pdfs_for_batch_output(target, reconcile_first=reconcile)
            click.echo(f"Rendered PDFs for {n} dataset folders under {ds_root}")
            return
        raise SystemExit(
            f"Expected target to be case.json, a dataset folder containing case.json, "
            f"or a batch root with datasets/ — got {target}"
        )
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e


if __name__ == "__main__":
    main()
