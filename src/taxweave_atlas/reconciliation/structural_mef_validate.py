"""Coherence: structural MeF documents match case flags, income, credits, and form bundle rules."""

from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ReconciliationError, ValidationError
from taxweave_atlas.reconciliation.supporting_forms import (
    SUPPORTING_FORM_POOL,
    applicable_supporting_forms,
    count_supporting_forms,
    finalize_supporting_forms,
    ordered_supporting_forms,
)
from taxweave_atlas.schema.case import SyntheticTaxCase


def validate_structural_mef_coherence(case: SyntheticTaxCase, spec: dict[str, Any]) -> None:
    """Raise if emitted schedules disagree with case data or selection is inconsistent."""
    se_net = int(case.income.other_ordinary_income.get("self_employment_net", 0) or 0)
    names = {d.element_name for d in case.structural_mef.documents}
    has_c = "IRS1040ScheduleC" in names
    has_se = "IRS1040ScheduleSE" in names
    has_8812 = "IRS1040Schedule8812" in names

    if se_net > 0:
        if not has_c or not has_se:
            raise ReconciliationError(
                "structural_mef coherence: self_employment_net > 0 requires "
                "IRS1040ScheduleC and IRS1040ScheduleSE in structural_mef.documents"
            )
    else:
        if has_c or has_se:
            raise ReconciliationError(
                "structural_mef coherence: Schedule C/SE must be absent when self_employment_net is zero"
            )

    qc = case.profile.dependents_qualifying_children_under_17
    min_qc = int((spec.get("schedule_8812") or {}).get("when_min_qualifying_children", 1))
    ctc = sum(c.amount for c in case.credits.credits if c.code == "CTC_SYNTH")
    actc = sum(c.amount for c in case.credits.credits if c.code == "ACTC_SYNTH")
    if qc >= min_qc:
        if ctc > 0 or actc > 0:
            if not has_8812:
                raise ReconciliationError(
                    "structural_mef coherence: qualifying children with CTC/ACTC require IRS1040Schedule8812"
                )
    else:
        if has_8812:
            raise ReconciliationError(
                "structural_mef coherence: IRS1040Schedule8812 must be absent when no qualifying children"
            )

    if case.schedule_2_additional_taxes > 0 and "IRS1040Schedule2" not in names:
        raise ReconciliationError(
            "structural_mef coherence: positive schedule_2_additional_taxes requires IRS1040Schedule2"
        )
    if case.form_8995_qualified_business_income > 0 and "IRS8995" not in names:
        raise ReconciliationError("structural_mef coherence: positive QBI stub requires IRS8995")
    if case.form_4562_depreciation_amount > 0 and "IRS4562" not in names:
        raise ReconciliationError("structural_mef coherence: positive depreciation stub requires IRS4562")

    for doc in case.structural_mef.documents:
        if doc.element_name == "IRS1040ScheduleC":
            np = doc.fields.get("NetProfitOrLossAmt")
            if np is not None and np != se_net:
                raise ReconciliationError(
                    f"structural_mef coherence: Schedule C NetProfitOrLossAmt {np} != self_employment_net {se_net}"
                )
        if doc.element_name == "IRS1040ScheduleSE":
            ne = doc.fields.get("NetEarningsSelfEmploymentAmt")
            if ne is not None and ne != se_net:
                raise ReconciliationError(
                    "structural_mef coherence: Schedule SE net earnings must equal self_employment_net"
                )
        if doc.element_name == "IRS1040Schedule8812":
            s8812 = spec.get("schedule_8812") or {}
            xfn = s8812.get("xml_field_names") or {}
            fc = xfn.get("child_count")
            if fc and doc.fields.get(fc) != qc:
                raise ReconciliationError("structural_mef coherence: 8812 child count must match profile")
            nr_codes = set(s8812.get("nonrefundable_credit_codes") or [])
            ref_codes = set(s8812.get("refundable_credit_codes") or [])
            ctc_sum = sum(c.amount for c in case.credits.credits if c.code in nr_codes)
            actc_sum = sum(c.amount for c in case.credits.credits if c.code in ref_codes)
            f_ctc = xfn.get("ctc_total")
            f_actc = xfn.get("actc_total")
            if f_ctc and doc.fields.get(f_ctc) != ctc_sum:
                raise ReconciliationError("structural_mef coherence: 8812 CTC total must match credit sum")
            if f_actc and doc.fields.get(f_actc) != actc_sum:
                raise ReconciliationError("structural_mef coherence: 8812 ACTC total must match credit sum")

        if doc.element_name == "IRS1040ScheduleB":
            if case.income.interest <= 0 and case.income.dividends_ordinary <= 0:
                raise ReconciliationError(
                    "structural_mef coherence: Schedule B present without interest or dividends"
                )
            fl = case.federal.lines
            if doc.fields.get("InterestAmt") != fl.taxable_interest:
                raise ReconciliationError("structural_mef coherence: Schedule B interest must match Form 1040")
            if doc.fields.get("OrdinaryDividendsAmt") != fl.ordinary_dividends:
                raise ReconciliationError("structural_mef coherence: Schedule B dividends must match Form 1040")

        if doc.element_name == "IRS1040Schedule1":
            exp_adj = case.federal.lines.additional_lines.get("schedule_1_adjustments_total", 0)
            exp_inc = case.federal.lines.additional_lines.get("schedule_1_additional_income_retirement", 0)
            if doc.fields.get("TotalAdjustmentsAmt") != exp_adj:
                raise ReconciliationError("structural_mef coherence: Schedule 1 adjustments must match federal")
            if doc.fields.get("TotalAdditionalIncomeAmt") != exp_inc:
                raise ReconciliationError("structural_mef coherence: Schedule 1 additional income must match federal")

        if doc.element_name == "IRS1040Schedule2":
            if doc.fields.get("TotalTaxAmt") != case.schedule_2_additional_taxes:
                raise ReconciliationError("structural_mef coherence: Schedule 2 must match schedule_2_additional_taxes")
            if case.schedule_2_additional_taxes <= 0:
                raise ReconciliationError("structural_mef coherence: Schedule 2 must not appear when additional tax is zero")

        if doc.element_name == "IRS8995":
            if doc.fields.get("QlfyBusIncmAmt") != case.form_8995_qualified_business_income:
                raise ReconciliationError("structural_mef coherence: Form 8995 QBI must match case field")
            if case.form_8995_qualified_business_income <= 0:
                raise ReconciliationError("structural_mef coherence: Form 8995 requires positive QBI amount")

        if doc.element_name == "IRS4562":
            if doc.fields.get("MACRSDedForAstInSrvcCyovYrAmt") != case.form_4562_depreciation_amount:
                raise ReconciliationError("structural_mef coherence: Form 4562 depreciation must match case field")
            if case.form_4562_depreciation_amount <= 0:
                raise ReconciliationError("structural_mef coherence: Form 4562 requires positive depreciation")

        if doc.element_name == "IRS8867":
            credit_sum = sum(c.amount for c in case.credits.credits)
            if doc.fields.get("TotalCreditsClmAmt") != credit_sum:
                raise ReconciliationError("structural_mef coherence: Form 8867 credit total must match credits packet")
            if credit_sum <= 0:
                raise ReconciliationError("structural_mef coherence: Form 8867 requires credits")

    _validate_supporting_form_bundle(case)


def _validate_supporting_form_bundle(case: SyntheticTaxCase) -> None:
    """Exactly 6–7 supporting forms from the pool; order matches finalized selection."""
    n = count_supporting_forms(case)
    if n < 6 or n > 7:
        raise ReconciliationError(
            f"structural_mef coherence: supporting form count must be 6–7 (got {n}); "
            "IRS1040 is emitted separately and is not counted here."
        )
    for d in case.structural_mef.documents:
        if d.element_name not in SUPPORTING_FORM_POOL:
            raise ReconciliationError(
                f"structural_mef coherence: unknown structural document {d.element_name!r} "
                f"(expected only {sorted(SUPPORTING_FORM_POOL)})"
            )

    final = finalize_supporting_forms(case, applicable_supporting_forms(case))
    expected_order = ordered_supporting_forms(final)
    actual = [d.element_name for d in case.structural_mef.documents]
    if actual != expected_order:
        raise ReconciliationError(
            f"structural_mef coherence: supporting form order mismatch: got {actual}, expected {expected_order}"
        )


def validate_structural_mef_vs_complexity(case: SyntheticTaxCase) -> None:
    """Easy tier never carries self-employment (generator + questionnaire already enforce)."""
    cx = case.questionnaire.answers.extensions.get("complexity_tier")
    if cx is None:
        return
    cx_s = str(cx).strip()
    if cx_s != "easy":
        return
    se_net = int(case.income.other_ordinary_income.get("self_employment_net", 0) or 0)
    if se_net > 0 or case.questionnaire.answers.has_self_employment_income:
        raise ValidationError("easy complexity tier must not include self-employment income")
