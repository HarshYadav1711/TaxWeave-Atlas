from __future__ import annotations

import hashlib
import json

from taxweave_atlas.schema.case import SyntheticTaxCase


def case_fingerprint(case: SyntheticTaxCase) -> str:
    """Stable identity hash for de-duplication across batches."""
    p = case.profile.model_dump(mode="json")
    inc = case.income.model_dump(mode="json")
    key = {
        "tax_year": case.tax_year,
        "state": case.state.code,
        "filing": p["filing_status"],
        "ssn_p": p["synthetic_ssn_primary"],
        "ssn_s": p.get("synthetic_ssn_spouse"),
        "wages": inc["wages"],
        "interest": inc["interest"],
        "dividends": inc["dividends_ordinary"],
        "ein": inc["w2"]["employer_ein"],
        "last": p["primary_last_name"],
        "first": p["primary_first_name"],
        "qc": p["dependents_qualifying_children_under_17"],
        "od": p["dependents_other"],
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
