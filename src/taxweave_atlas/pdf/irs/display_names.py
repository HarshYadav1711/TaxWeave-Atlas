from __future__ import annotations

from taxweave_atlas.schema.case import SyntheticTaxCase


def names_shown_on_schedules(case: SyntheticTaxCase) -> str:
    """
    Text for schedule headers ("Name(s) shown on your return").

    Joint returns should match both names as they appear together on Form 1040.
    """
    p = case.profile
    primary = f"{p.primary_first_name} {p.primary_last_name}".strip()
    if p.filing_status != "married_filing_jointly":
        return primary
    sf = (p.spouse_first_name or "").strip()
    sl = (p.spouse_last_name or "").strip()
    if not sf or not sl:
        return primary
    return f"{primary} & {sf} {sl}"
