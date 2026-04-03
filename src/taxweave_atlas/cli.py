from __future__ import annotations

from pathlib import Path

import click

from taxweave_atlas.exceptions import TaxWeaveError


@click.group()
@click.version_option(package_name="taxweave-atlas")
def main() -> None:
    """TaxWeave Atlas — local synthetic tax dataset tooling (foundation stage)."""


def _run_batch(output: Path, master_seed: int, count: int, complexity: str | None) -> Path:
    from taxweave_atlas.orchestration.batch import write_foundation_batch_plan

    try:
        return write_foundation_batch_plan(
            output,
            master_seed=master_seed,
            count=count,
            complexity_level=complexity,
        )
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e


@main.command("pilot")
@click.option("--count", type=int, default=10, show_default=True, help="Pilot batch size")
@click.option("--seed", type=int, default=42, show_default=True, help="Master RNG seed")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output root (manifests/ created beneath it)",
)
@click.option(
    "--complexity",
    type=str,
    default=None,
    help="Override application.yaml default_complexity",
)
def cmd_pilot(count: int, seed: int, output: Path, complexity: str | None) -> None:
    """Plan a small batch (deterministic ids/seeds only; no case/PDF generation)."""
    path = _run_batch(output, seed, count, complexity)
    click.echo(f"Wrote foundation batch plan ({count} datasets) to {path}")


@main.command("generate")
@click.option("--count", type=int, default=2000, show_default=True, help="Full batch size")
@click.option("--seed", type=int, default=42, show_default=True, help="Master RNG seed")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output root (manifests/ created beneath it)",
)
@click.option(
    "--complexity",
    type=str,
    default=None,
    help="Override application.yaml default_complexity",
)
def cmd_generate(count: int, seed: int, output: Path, complexity: str | None) -> None:
    """Plan a full-scale batch (deterministic ids/seeds only; no case/PDF generation)."""
    path = _run_batch(output, seed, count, complexity)
    click.echo(f"Wrote foundation batch plan ({count} datasets) to {path}")


@main.command("validate-specs")
def cmd_validate_specs() -> None:
    """Validate sample pack JSON + application/tax_rules placeholders."""
    from taxweave_atlas.validation.specs import validate_specs_against_application_config

    try:
        validate_specs_against_application_config()
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e
    click.echo("specs OK")


if __name__ == "__main__":
    main()
