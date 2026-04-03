from __future__ import annotations

from pathlib import Path

import click

from taxweave_atlas.exceptions import TaxWeaveError


@click.group()
def main() -> None:
    """TaxWeave Atlas — synthetic tax PDF bundles."""


@main.command("generate")
@click.option("--count", type=int, required=True, help="Number of dataset bundles to generate")
@click.option("--seed", type=int, required=True, help="Deterministic RNG seed (audit/repro)")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory (created; must not overlap existing datasets)",
)
@click.option(
    "--no-case-json",
    is_flag=True,
    default=False,
    help="Omit case.json sidecar (PDFs only in tree; not recommended for audit)",
)
def cmd_generate(count: int, seed: int, output: Path, no_case_json: bool) -> None:
    """Generate synthetic PDF dataset bundles."""
    from taxweave_atlas.pipeline import generate_batch

    try:
        res = generate_batch(
            count=count,
            seed=seed,
            output=output,
            write_case_json=not no_case_json,
        )
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e
    click.echo(f"Wrote {res.count} datasets under {res.output_dir}")
    click.echo(f"Manifest: {res.fingerprints_path}")


@main.command("validate-reference")
def cmd_validate_reference() -> None:
    """Validate reference_pack against manifest, mappings, and rules."""
    from taxweave_atlas.pipeline import validate_reference_pack

    try:
        validate_reference_pack()
    except TaxWeaveError as e:
        raise SystemExit(f"error: {e}") from e
    click.echo("reference_pack OK")


if __name__ == "__main__":
    main()
