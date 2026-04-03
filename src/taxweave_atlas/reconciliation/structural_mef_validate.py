"""Coherence: structural MeF documents match case flags, income, credits, and complexity tier."""

from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ReconciliationError, ValidationError
from taxweave_atlas.schema.case import SyntheticTaxCase


def validate_structural_mef_coherence(case: SyntheticTaxCase, spec: dict[str, Any]) -> None:
    """Raise if emitted/absent schedules disagree with case data (post-reconciliation)."""
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
    if qc >= min_qc:
        if not has_8812:
            raise ReconciliationError(
                "structural_mef coherence: qualifying children require IRS1040Schedule8812 when credits exist"
            )
    else:
        if has_8812:
            raise ReconciliationError(
                "structural_mef coherence: IRS1040Schedule8812 must be absent when no qualifying children"
            )

    # Mirror amounts (path-bound fields)
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
