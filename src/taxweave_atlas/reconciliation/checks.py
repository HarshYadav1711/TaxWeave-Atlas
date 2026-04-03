from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ReconciliationError
from taxweave_atlas.reconciliation.paths_util import resolve_dotted_path
from taxweave_atlas.schema.case import SyntheticTaxCase


def _assert_supporting_documents_align(case: SyntheticTaxCase) -> None:
    """Explicit parity between supporting doc key_amounts and income (not expressible as flat paths)."""
    inc = case.income
    for doc in case.supporting_documents.documents:
        if doc.kind == "w2":
            if doc.key_amounts.get("wages") != inc.wages:
                raise ReconciliationError(
                    f"Supporting W-2 wages {doc.key_amounts.get('wages')!r} != income.wages {inc.wages!r}"
                )
            if doc.key_amounts.get("federal_withholding") != inc.federal_withholding:
                raise ReconciliationError("Supporting W-2 federal withholding must match income")
        elif doc.kind == "1099_int":
            if doc.key_amounts.get("interest") != inc.interest:
                raise ReconciliationError(
                    f"Supporting 1099-INT interest {doc.key_amounts.get('interest')!r} "
                    f"!= income.interest {inc.interest!r}"
                )
        elif doc.kind == "1099_div":
            if doc.key_amounts.get("ordinary_dividends") != inc.dividends_ordinary:
                raise ReconciliationError(
                    "Supporting 1099-DIV ordinary dividends must match income.dividends_ordinary"
                )


def run_cross_checks(case: SyntheticTaxCase, rules: list[dict[str, Any]]) -> None:
    """YAML-driven equality checks across case slices (fail loudly on first violation)."""
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
        try:
            lv = resolve_dotted_path(data, left_path)
            rv = resolve_dotted_path(data, right_path)
        except KeyError as e:
            raise ReconciliationError(f"Cross-check {rid}: path missing ({e})") from e
        if lv != rv:
            raise ReconciliationError(
                f"Cross-check {rid} failed: {left_path}={lv!r} != {right_path}={rv!r} "
                f"({rule.get('description', '')})"
            )

    _assert_supporting_documents_align(case)


def validate_reconciled_case(case: SyntheticTaxCase) -> None:
    """Re-run cross-checks using packaged rules (e.g. after manual edits)."""
    from taxweave_atlas.reconciliation.config import load_reconciliation_bundle
    from taxweave_atlas.reconciliation.structural_mef_validate import (
        validate_structural_mef_coherence,
        validate_structural_mef_vs_complexity,
    )

    bundle = load_reconciliation_bundle()
    run_cross_checks(case, bundle["cross_checks"])
    validate_structural_mef_coherence(case, bundle["structural_mef"])
    validate_structural_mef_vs_complexity(case)
