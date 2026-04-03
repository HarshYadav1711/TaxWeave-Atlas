"""Representative synthetic cases: easy, medium, moderately complex."""

from __future__ import annotations

import pytest

from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.generation.validation import validate_generated_case
from taxweave_atlas.schema.ids import DatasetIdentity


@pytest.mark.parametrize(
    "tier",
    ["easy", "medium", "moderately_complex"],
)
def test_synthetic_case_tier_reconciles_and_validates(tier: str) -> None:
    case = build_synthetic_case(
        master_seed=2026,
        identity=DatasetIdentity(index=0),
        salt=0,
        complexity_override=tier,
        state_override="CA",
        tax_year_override=2023,
    )
    validate_generated_case(case)
