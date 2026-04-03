"""Reconciliation-owned MeF schedule stubs: applicability and path-mapped amounts only."""

from __future__ import annotations

from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.schema.ids import DatasetIdentity


def test_easy_tier_never_emits_schedule_c_or_se() -> None:
    for salt in range(40):
        case = build_synthetic_case(
            master_seed=7001,
            identity=DatasetIdentity(index=0),
            salt=salt,
            complexity_override="easy",
            state_override="TX",
            tax_year_override=2023,
        )
        names = {d.element_name for d in case.structural_mef.documents}
        assert "IRS1040ScheduleC" not in names
        assert "IRS1040ScheduleSE" not in names


def test_medium_emits_schedule_c_when_self_employment_present() -> None:
    found = False
    for salt in range(250):
        case = build_synthetic_case(
            master_seed=7002,
            identity=DatasetIdentity(index=0),
            salt=salt,
            complexity_override="medium",
            state_override="NY",
            tax_year_override=2022,
        )
        se = int(case.income.other_ordinary_income.get("self_employment_net", 0) or 0)
        if se <= 0:
            continue
        found = True
        names = {d.element_name for d in case.structural_mef.documents}
        assert "IRS1040ScheduleC" in names
        assert "IRS1040ScheduleSE" in names
        for doc in case.structural_mef.documents:
            if doc.element_name == "IRS1040ScheduleC":
                assert doc.fields.get("NetProfitOrLossAmt") == se
            if doc.element_name == "IRS1040ScheduleSE":
                assert doc.fields.get("NetEarningsSelfEmploymentAmt") == se
        break
    assert found, "expected at least one medium case with self_employment_net in salt sweep"


def test_schedule_8812_when_qualifying_children_and_ctc_credits() -> None:
    found = False
    for salt in range(400):
        case = build_synthetic_case(
            master_seed=7003,
            identity=DatasetIdentity(index=0),
            salt=salt,
            complexity_override="medium",
            state_override="CA",
            tax_year_override=2023,
        )
        qc = case.profile.dependents_qualifying_children_under_17
        if qc < 1:
            continue
        found = True
        names = {d.element_name for d in case.structural_mef.documents}
        assert "IRS1040Schedule8812" in names
        ctc = sum(c.amount for c in case.credits.credits if c.code == "CTC_SYNTH")
        actc = sum(c.amount for c in case.credits.credits if c.code == "ACTC_SYNTH")
        assert ctc > 0 or actc > 0
        doc = next(d for d in case.structural_mef.documents if d.element_name == "IRS1040Schedule8812")
        assert doc.fields.get("QlfyChildUnderAgeSSNCnt") == qc
        assert doc.fields.get("ChldTxCrdAmt") == ctc
        assert doc.fields.get("RfdblChldTxCrdAmt") == actc
        break
    assert found, "expected at least one medium case with qualifying children in salt sweep"
