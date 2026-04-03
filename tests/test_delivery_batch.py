"""Batch output integrity and delivery validation."""

from __future__ import annotations

from pathlib import Path

from taxweave_atlas.delivery.batch_validate import validate_batch_output
from taxweave_atlas.generation.batch_runner import run_case_generation_batch


def _assert_export_pdf_only(export_dir: Path) -> None:
    root_files = {p.name for p in export_dir.iterdir() if p.is_file()}
    assert root_files == {"manifest.json"}, root_files
    for p in export_dir.rglob("*"):
        if p.is_file() and p.name != "manifest.json":
            assert p.suffix.lower() == ".pdf", p


def test_small_batch_passes_delivery_validation(tmp_path: Path) -> None:
    out = tmp_path / "batch"
    run_case_generation_batch(
        out,
        master_seed=101,
        count=3,
        complexity_override="medium",
        state_override="NY",
        tax_year_override=2022,
        write_pdfs=True,
    )
    report = validate_batch_output(out, expect_pdfs=True, strict_distribution=False)
    assert report.ok, (report.errors, report.warnings)
    assert report.dataset_count == 3
    assert not report.duplicate_fingerprints
    first_staging = sorted((out / "_staging" / "datasets").glob("dataset_*"))[0]
    first_export = out / "datasets" / first_staging.name
    assert (first_staging / "case.json").is_file()
    assert (first_export / "manifest.json").is_file()
    _assert_export_pdf_only(first_export)
    assert (out / "manifests" / "delivery_audits" / f"{first_staging.name}.json").is_file()
    assert (out / "manifests" / "delivery_validation_report.json").is_file()


def test_validate_batch_without_pdfs(tmp_path: Path) -> None:
    out = tmp_path / "nopdf"
    run_case_generation_batch(
        out,
        master_seed=202,
        count=2,
        complexity_override="easy",
        state_override="TX",
        tax_year_override=2021,
        write_pdfs=False,
    )
    report = validate_batch_output(out, expect_pdfs=False, strict_distribution=False)
    assert report.ok, report.errors
