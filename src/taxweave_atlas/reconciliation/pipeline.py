"""
Deterministic reconciliation: derive federal lines, state tax, executive summary,
and supporting-document key amounts from declared income, deductions, and credits.
"""

from __future__ import annotations

from taxweave_atlas.generation.validation import validate_synthetic_source
from taxweave_atlas.reconciliation.checks import run_cross_checks
from taxweave_atlas.reconciliation.compute import (
    assert_scope,
    build_executive_summary,
    build_federal_return,
    build_state_return,
    compute_agi,
    sync_supporting_documents,
)
from taxweave_atlas.reconciliation.config import load_reconciliation_bundle
from taxweave_atlas.schema.case import SyntheticTaxCase


def reconcile_case(case: SyntheticTaxCase) -> SyntheticTaxCase:
    """Return a copy of ``case`` with reconciled slices; raises on scope or cross-check violations."""
    validate_synthetic_source(case)
    bundle = load_reconciliation_bundle()
    scope = bundle["scope"]
    assert_scope(case, scope)

    agi, _breakdown = compute_agi(case, scope)
    federal = build_federal_return(case, agi=agi, bundle=bundle)
    state = build_state_return(case, agi, bundle)
    executive = build_executive_summary(case, federal, state)
    supporting = sync_supporting_documents(case)

    out = case.model_copy(
        update={
            "federal": federal,
            "state": state,
            "executive_summary": executive,
            "supporting_documents": supporting,
        }
    )
    run_cross_checks(out, bundle["cross_checks"])
    return out
