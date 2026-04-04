"""Mandatory IRS1040 and 6–7 rule-based supporting forms per reconciled case."""

from __future__ import annotations

from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.reconciliation.supporting_forms import SUPPORTING_FORM_POOL, count_supporting_forms
from taxweave_atlas.schema.ids import DatasetIdentity
from taxweave_atlas.structure.case_copy import build_mef_subset_prompt_xml
from taxweave_atlas.validation.specs import load_sample_case
from taxweave_atlas.reconciliation.pipeline import reconcile_case


def test_generated_cases_have_six_or_seven_supporting_forms() -> None:
    for seed, cx in [(8011, "easy"), (8012, "medium"), (8013, "moderately_complex")]:
        for idx in range(5):
            case = build_synthetic_case(
                master_seed=seed,
                identity=DatasetIdentity(index=idx),
                salt=0,
                complexity_override=cx,
                state_override="FL",
                tax_year_override=2023,
            )
            n = count_supporting_forms(case)
            assert 6 <= n <= 7, f"{seed}/{cx}/{idx}: expected 6–7 supporting forms, got {n}"
            for d in case.structural_mef.documents:
                assert d.element_name in SUPPORTING_FORM_POOL


def test_sample_pack_reconciles_with_form_policy() -> None:
    case = reconcile_case(load_sample_case())
    n = count_supporting_forms(case)
    assert n == 6
    assert b"<IRS1040 " in build_mef_subset_prompt_xml(case)
    assert b"<IRSW2 " in build_mef_subset_prompt_xml(case)
