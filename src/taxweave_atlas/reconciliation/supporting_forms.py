"""
Rule-based selection of 6–7 supporting schedules/forms (excluding IRS1040, which is always emitted).

Selection is deterministic from ``SyntheticTaxCase`` fields — no random form inclusion.
"""

from __future__ import annotations

from taxweave_atlas.exceptions import ReconciliationError
from taxweave_atlas.schema.case import SyntheticTaxCase

# Pool required by product spec (MeF-style element tags).
SUPPORTING_FORM_POOL: frozenset[str] = frozenset(
    {
        "IRS1040Schedule1",
        "IRS1040Schedule2",
        "IRS1040ScheduleB",
        "IRS1040ScheduleC",
        "IRS1040ScheduleSE",
        "IRS1040Schedule8812",
        "IRS8995",
        "IRS4562",
        "IRS8867",
    }
)

# When more than seven forms apply, drop lowest priority first (pair C/SE drops together).
_DROP_PRIORITY: dict[str, int] = {
    "IRS4562": 10,
    "IRS8995": 20,
    "IRS1040Schedule1": 30,
    "IRS1040Schedule2": 40,
    "IRS8867": 50,
    "IRS1040ScheduleB": 60,
    "IRS1040Schedule8812": 70,
    "IRS1040ScheduleC": 80,
    "IRS1040ScheduleSE": 80,
}

# Prompt XML / PDF narrative order after IRS1040 and IRSW2.
SUPPORTING_FORM_EMIT_ORDER: tuple[str, ...] = (
    "IRS1040ScheduleB",
    "IRS1040Schedule1",
    "IRS1040Schedule2",
    "IRS1040ScheduleC",
    "IRS1040ScheduleSE",
    "IRS1040Schedule8812",
    "IRS8995",
    "IRS4562",
    "IRS8867",
)


def _credit_totals(case: SyntheticTaxCase) -> int:
    return sum(c.amount for c in case.credits.credits)


def applicable_supporting_forms(case: SyntheticTaxCase) -> set[str]:
    """Forms justified by reconciled-source fields (before capping to seven)."""
    out: set[str] = set()
    inc = case.income
    if inc.interest > 0 or inc.dividends_ordinary > 0:
        out.add("IRS1040ScheduleB")

    se_net = int(inc.other_ordinary_income.get("self_employment_net", 0) or 0)
    if se_net > 0:
        out.add("IRS1040ScheduleC")
        out.add("IRS1040ScheduleSE")

    sch1_adj = sum(case.deductions.adjustments_to_agi.values())
    ret = int(inc.passive_income.get("retirement_distributions", 0) or 0)
    if sch1_adj > 0 or ret > 0:
        out.add("IRS1040Schedule1")

    if case.schedule_2_additional_taxes > 0:
        out.add("IRS1040Schedule2")

    qc = case.profile.dependents_qualifying_children_under_17
    ctc = sum(c.amount for c in case.credits.credits if c.code == "CTC_SYNTH")
    actc = sum(c.amount for c in case.credits.credits if c.code == "ACTC_SYNTH")
    if qc >= 1 and (ctc > 0 or actc > 0):
        out.add("IRS1040Schedule8812")

    if case.form_8995_qualified_business_income > 0:
        out.add("IRS8995")

    if case.form_4562_depreciation_amount > 0:
        out.add("IRS4562")

    if _credit_totals(case) > 0:
        out.add("IRS8867")

    assert out <= SUPPORTING_FORM_POOL
    return out


def _remove_c_se_pair(s: set[str]) -> None:
    s.discard("IRS1040ScheduleC")
    s.discard("IRS1040ScheduleSE")


def finalize_supporting_forms(case: SyntheticTaxCase, applicable: set[str]) -> set[str]:
    """
    If more than seven supporting forms apply, drop lowest-priority removable forms.

    Protected: Schedule B when interest/dividends exist; C/SE pair when SE net > 0;
    8812 when qualifying children and CTC/ACTC; 8867 when credits exist.
    """
    s = set(applicable)
    se_net = int(case.income.other_ordinary_income.get("self_employment_net", 0) or 0)
    qc = case.profile.dependents_qualifying_children_under_17
    ctc = sum(c.amount for c in case.credits.credits if c.code == "CTC_SYNTH")
    actc = sum(c.amount for c in case.credits.credits if c.code == "ACTC_SYNTH")
    credits_total = _credit_totals(case)

    def can_drop(name: str) -> bool:
        if name == "IRS1040ScheduleB":
            return not (case.income.interest > 0 or case.income.dividends_ordinary > 0)
        if name in ("IRS1040ScheduleC", "IRS1040ScheduleSE"):
            return se_net <= 0
        if name == "IRS1040Schedule8812":
            return not (qc >= 1 and (ctc > 0 or actc > 0))
        if name == "IRS8867":
            return credits_total <= 0
        if name == "IRS8995":
            return case.form_8995_qualified_business_income <= 0
        if name == "IRS4562":
            return case.form_4562_depreciation_amount <= 0
        if name == "IRS1040Schedule2":
            return case.schedule_2_additional_taxes <= 0
        if name == "IRS1040Schedule1":
            sch1_adj = sum(case.deductions.adjustments_to_agi.values())
            ret = int(case.income.passive_income.get("retirement_distributions", 0) or 0)
            return sch1_adj <= 0 and ret <= 0
        return True

    while len(s) > 7:
        droppable = [f for f in s if can_drop(f)]
        if not droppable:
            break
        victim = min(droppable, key=lambda f: _DROP_PRIORITY.get(f, 999))
        if victim in ("IRS1040ScheduleC", "IRS1040ScheduleSE"):
            _remove_c_se_pair(s)
        else:
            s.discard(victim)

    return s


def ordered_supporting_forms(final: set[str]) -> list[str]:
    """Stable order matching sample-style flow: schedules, then additional forms."""
    return [name for name in SUPPORTING_FORM_EMIT_ORDER if name in final]


def count_supporting_forms(case: SyntheticTaxCase) -> int:
    return sum(1 for d in case.structural_mef.documents if d.element_name in SUPPORTING_FORM_POOL)


def _final_supporting_count(case: SyntheticTaxCase) -> int:
    return len(finalize_supporting_forms(case, applicable_supporting_forms(case)))


def trim_supporting_form_overflow(case: SyntheticTaxCase) -> SyntheticTaxCase:
    """
    If rule-based selection would still exceed seven forms after capping, strip synthetic
    stubs (4562, 8995, Schedule 2) only — never income, adjustments, or retirement drivers.
    """
    c = case
    guard = 0
    while _final_supporting_count(c) > 7 and guard < 32:
        guard += 1
        if c.form_4562_depreciation_amount > 0:
            c = c.model_copy(update={"form_4562_depreciation_amount": 0})
            continue
        if c.form_8995_qualified_business_income > 0:
            c = c.model_copy(update={"form_8995_qualified_business_income": 0})
            continue
        if c.schedule_2_additional_taxes > 0:
            c = c.model_copy(update={"schedule_2_additional_taxes": 0})
            continue
        break

    if _final_supporting_count(c) > 7:
        raise ReconciliationError(
            "Supporting form selection exceeds seven even after stub trimming; relax generator triggers."
        )
    return c
