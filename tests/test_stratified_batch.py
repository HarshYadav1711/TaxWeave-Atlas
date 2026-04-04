"""Stratified review pilot: marginal distributions and end-to-end batch write."""

from __future__ import annotations

from collections import Counter

from taxweave_atlas.generation.stratified_batch import (
    build_stratification_assignments,
    run_stratified_review_pilot_batch,
)


def test_stratification_marginals_at_80() -> None:
    states, cx, years, profile = build_stratification_assignments(80, master_seed=999)
    assert len(states) == len(cx) == len(years) == 80
    assert Counter(states) == {"CA": 16, "TX": 16, "NY": 16, "IL": 16, "FL": 16}
    assert Counter(cx) == {"easy": 24, "medium": 32, "moderately_complex": 24}
    assert Counter(years)[2025] == 10
    for y in (2020, 2021, 2022, 2023, 2024):
        assert Counter(years)[y] == 14
    assert profile["count"] == 80


def test_stratified_pilot_writes_two_datasets(tmp_path) -> None:
    out = tmp_path / "batch"
    run_stratified_review_pilot_batch(
        out,
        master_seed=12345,
        count=2,
        write_pdfs=False,
        run_delivery_validation=False,
    )
    assert (out / "manifests" / "batch_plan.json").is_file()
    assert (out / "manifests" / "batch_summary.json").is_file()
    assert (out / "_staging" / "datasets" / "dataset_00001" / "case.json").is_file()
