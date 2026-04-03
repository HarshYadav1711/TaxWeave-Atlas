from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ReconciliationError
from taxweave_atlas.reconciliation.cross_document_format import format_cross_document_mismatch
from taxweave_atlas.reconciliation.paths_util import resolve_dotted_path
from taxweave_atlas.schema.case import SyntheticTaxCase


def _default_tolerance(tolerance_cfg: dict[str, Any] | None) -> int:
    if not tolerance_cfg:
        return 0
    raw = tolerance_cfg.get("default_abs", 0)
    return int(raw) if raw is not None else 0


def _rule_tolerance(rule: dict[str, Any], tolerance_cfg: dict[str, Any] | None) -> int:
    if "abs_tolerance" in rule:
        return int(rule["abs_tolerance"])
    return _default_tolerance(tolerance_cfg)


def _numeric_within_tolerance(lv: object, rv: object, tol: int) -> bool:
    """Exact match when tol==0; otherwise numeric abs difference."""
    if tol == 0:
        return lv == rv
    try:
        a = float(lv)  # type: ignore[arg-type]
        b = float(rv)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return lv == rv
    return abs(a - b) <= tol


def run_cross_checks(
    case: SyntheticTaxCase,
    rules: list[dict[str, Any]],
    tolerance_cfg: dict[str, Any] | None = None,
) -> None:
    """YAML-driven cross-document checks with structured mismatch messages."""
    data = case.model_dump(mode="json")
    for rule in rules:
        rid = rule.get("id", "?")
        op = rule.get("op")
        if op != "eq":
            raise ReconciliationError(f"Cross-check {rid}: unsupported op {op!r}")
        left_path = rule.get("left")
        right_path = rule.get("right")
        if not isinstance(left_path, str) or not isinstance(right_path, str):
            raise ReconciliationError(f"Cross-check {rid}: left/right must be string paths")
        tol = _rule_tolerance(rule, tolerance_cfg)
        tol_note = f"abs_tolerance={tol} (currency units)" if tol else "exact match (abs_tolerance=0)"
        try:
            lv = resolve_dotted_path(data, left_path)
            rv = resolve_dotted_path(data, right_path)
        except KeyError as e:
            raise ReconciliationError(
                f"Cross-document check [{rid}] failed: missing path {e} "
                f"({rule.get('description', '')})"
            ) from e
        if not _numeric_within_tolerance(lv, rv, tol):
            left_doc = str(
                rule.get("left_document") or f"model path {left_path}"
            )
            right_doc = str(
                rule.get("right_document") or f"model path {right_path}"
            )
            raise ReconciliationError(
                format_cross_document_mismatch(
                    check_id=str(rid),
                    left_document=left_doc,
                    right_document=right_doc,
                    left_field=left_path,
                    right_field=right_path,
                    left_value=lv,
                    right_value=rv,
                    tolerance_note=tol_note,
                )
            )

    _assert_supporting_documents_align(case, tolerance_cfg)
    _assert_schedule_c_net_matches_schedule_se(case)


def _assert_supporting_documents_align(
    case: SyntheticTaxCase,
    tolerance_cfg: dict[str, Any] | None,
) -> None:
    """Supporting PDF key_amounts vs income, W-2 vs Form 1040, 1099s vs Schedule B mirror lines."""
    tol = _default_tolerance(tolerance_cfg)
    tol_note = f"abs_tolerance={tol}" if tol else "exact match"
    inc = case.income
    fl = case.federal.lines
    for doc in case.supporting_documents.documents:
        if doc.kind == "w2":
            w_w = doc.key_amounts.get("wages")
            if not _numeric_within_tolerance(w_w, inc.wages, tol):
                raise ReconciliationError(
                    format_cross_document_mismatch(
                        check_id="supporting_w2_wages_vs_income",
                        left_document=f"Supporting PDF {doc.display_name!r} (key_amounts.wages)",
                        right_document="Form W-2 / 1040 wages chain (income.wages)",
                        left_field="key_amounts.wages",
                        right_field="income.wages",
                        left_value=w_w,
                        right_value=inc.wages,
                        tolerance_note=tol_note,
                    )
                )
            if not _numeric_within_tolerance(w_w, fl.wages, tol):
                raise ReconciliationError(
                    format_cross_document_mismatch(
                        check_id="supporting_w2_wages_vs_form1040",
                        left_document=f"Supporting PDF {doc.display_name!r} (key_amounts.wages)",
                        right_document="IRS Form 1040 wages (federal.lines.wages)",
                        left_field="key_amounts.wages",
                        right_field="federal.lines.wages",
                        left_value=w_w,
                        right_value=fl.wages,
                        tolerance_note=tol_note,
                    )
                )
            wh = doc.key_amounts.get("federal_withholding")
            if not _numeric_within_tolerance(wh, inc.federal_withholding, tol):
                raise ReconciliationError(
                    format_cross_document_mismatch(
                        check_id="supporting_w2_withholding_vs_income",
                        left_document=f"Supporting PDF {doc.display_name!r} (federal_withholding)",
                        right_document="income.federal_withholding (1040 withholding line)",
                        left_field="key_amounts.federal_withholding",
                        right_field="income.federal_withholding",
                        left_value=wh,
                        right_value=inc.federal_withholding,
                        tolerance_note=tol_note,
                    )
                )
        elif doc.kind == "1099_int":
            ix = doc.key_amounts.get("interest")
            if not _numeric_within_tolerance(ix, inc.interest, tol):
                raise ReconciliationError(
                    format_cross_document_mismatch(
                        check_id="supporting_1099int_vs_income_interest",
                        left_document=f"Supporting PDF {doc.display_name!r} (interest)",
                        right_document="income.interest",
                        left_field="key_amounts.interest",
                        right_field="income.interest",
                        left_value=ix,
                        right_value=inc.interest,
                        tolerance_note=tol_note,
                    )
                )
            if not _numeric_within_tolerance(ix, fl.taxable_interest, tol):
                raise ReconciliationError(
                    format_cross_document_mismatch(
                        check_id="supporting_1099int_vs_schedule_b_mirror",
                        left_document=f"Supporting PDF {doc.display_name!r} (interest)",
                        right_document="Form 1040 & IRS1040ScheduleB interest (federal.lines.taxable_interest)",
                        left_field="key_amounts.interest",
                        right_field="federal.lines.taxable_interest",
                        left_value=ix,
                        right_value=fl.taxable_interest,
                        tolerance_note=tol_note,
                    )
                )
        elif doc.kind == "1099_div":
            dv = doc.key_amounts.get("ordinary_dividends")
            if not _numeric_within_tolerance(dv, inc.dividends_ordinary, tol):
                raise ReconciliationError(
                    format_cross_document_mismatch(
                        check_id="supporting_1099div_vs_income_dividends",
                        left_document=f"Supporting PDF {doc.display_name!r} (ordinary_dividends)",
                        right_document="income.dividends_ordinary",
                        left_field="key_amounts.ordinary_dividends",
                        right_field="income.dividends_ordinary",
                        left_value=dv,
                        right_value=inc.dividends_ordinary,
                        tolerance_note=tol_note,
                    )
                )
            if not _numeric_within_tolerance(dv, fl.ordinary_dividends, tol):
                raise ReconciliationError(
                    format_cross_document_mismatch(
                        check_id="supporting_1099div_vs_schedule_b_mirror",
                        left_document=f"Supporting PDF {doc.display_name!r} (ordinary_dividends)",
                        right_document="Form 1040 & IRS1040ScheduleB dividends (federal.lines.ordinary_dividends)",
                        left_field="key_amounts.ordinary_dividends",
                        right_field="federal.lines.ordinary_dividends",
                        left_value=dv,
                        right_value=fl.ordinary_dividends,
                        tolerance_note=tol_note,
                    )
                )


def _assert_schedule_c_net_matches_schedule_se(case: SyntheticTaxCase) -> None:
    """MeF IRS1040ScheduleC NetProfitOrLossAmt must equal IRS1040ScheduleSE base (same reconciled net SE)."""
    c_net: int | None = None
    se_net: int | None = None
    for d in case.structural_mef.documents:
        if d.element_name == "IRS1040ScheduleC":
            c_net = d.fields.get("NetProfitOrLossAmt")
        elif d.element_name == "IRS1040ScheduleSE":
            se_net = d.fields.get("NetEarningsSelfEmploymentAmt")
    if c_net is None and se_net is None:
        return
    if c_net is None or se_net is None:
        raise ReconciliationError(
            "Cross-document consistency [schedule_c_vs_schedule_se]: "
            "one of IRS1040ScheduleC / IRS1040ScheduleSE is present without the other"
        )
    if c_net != se_net:
        raise ReconciliationError(
            format_cross_document_mismatch(
                check_id="schedule_c_net_vs_schedule_se_base",
                left_document="Prompt XML / structural_mef — IRS1040ScheduleC",
                right_document="Prompt XML / structural_mef — IRS1040ScheduleSE",
                left_field="NetProfitOrLossAmt",
                right_field="NetEarningsSelfEmploymentAmt",
                left_value=c_net,
                right_value=se_net,
                tolerance_note="exact integer match (no tolerance)",
            )
        )


def validate_reconciled_case(case: SyntheticTaxCase) -> None:
    """Re-run cross-checks using packaged rules (e.g. after manual edits)."""
    from taxweave_atlas.reconciliation.config import load_reconciliation_bundle
    from taxweave_atlas.reconciliation.structural_mef_validate import (
        validate_structural_mef_coherence,
        validate_structural_mef_vs_complexity,
    )

    bundle = load_reconciliation_bundle()
    tol = bundle.get("cross_check_tolerance") or {}
    run_cross_checks(case, bundle["cross_checks"], tol)
    validate_structural_mef_coherence(case, bundle["structural_mef"])
    validate_structural_mef_vs_complexity(case)
