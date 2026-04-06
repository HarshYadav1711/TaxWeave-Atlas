from __future__ import annotations

from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.pdf.irs.display_names import names_shown_on_schedules
from taxweave_atlas.reconciliation.pipeline import reconcile_case
from taxweave_atlas.schema.ids import DatasetIdentity


def test_names_shown_joint_includes_spouse() -> None:
    case_mfj = None
    for salt in range(80):
        case = reconcile_case(
            build_synthetic_case(
                master_seed=44100,
                identity=DatasetIdentity(index=0),
                salt=salt,
                complexity_override="easy",
                state_override="TX",
                tax_year_override=2024,
            )
        )
        if case.profile.filing_status == "married_filing_jointly":
            case_mfj = case
            break
    assert case_mfj is not None, "expected an MFJ case in salt sweep"
    text = names_shown_on_schedules(case_mfj)
    assert "&" in text
    assert case_mfj.profile.primary_last_name in text
    assert (case_mfj.profile.spouse_last_name or "") in text
