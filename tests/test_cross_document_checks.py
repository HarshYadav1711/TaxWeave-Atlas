"""Cross-document reconciliation messages and tolerance (default exact)."""

from __future__ import annotations

import pytest

from taxweave_atlas.exceptions import ReconciliationError
from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.reconciliation.checks import run_cross_checks
from taxweave_atlas.reconciliation.config import load_reconciliation_bundle
from taxweave_atlas.schema.ids import DatasetIdentity


def test_cross_check_failure_includes_documents_and_fields() -> None:
    bundle = load_reconciliation_bundle()
    case = build_synthetic_case(
        master_seed=9001,
        identity=DatasetIdentity(index=0),
        salt=0,
        complexity_override="easy",
        state_override="FL",
        tax_year_override=2023,
    )
    # Break an invariant the YAML rules enforce
    case = case.model_copy(
        update={
            "federal": case.federal.model_copy(
                update={
                    "lines": case.federal.lines.model_copy(update={"wages": case.federal.lines.wages + 9999})
                }
            )
        }
    )
    with pytest.raises(ReconciliationError) as ei:
        run_cross_checks(case, bundle["cross_checks"], bundle.get("cross_check_tolerance"))
    msg = str(ei.value)
    assert "wages_match_w2_federal" in msg or "wages" in msg
    assert "Left document" in msg or "income.wages" in msg


def test_default_tolerance_is_exact_zero() -> None:
    bundle = load_reconciliation_bundle()
    tol = bundle.get("cross_check_tolerance") or {}
    assert int(tol.get("default_abs", -1)) == 0
