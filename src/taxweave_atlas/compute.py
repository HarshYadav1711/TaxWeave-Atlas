from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.models.case import FilingStatus


def _brackets(fed: dict[str, Any]) -> list[tuple[int | None, float]]:
    raw = fed.get("tax_brackets")
    if not isinstance(raw, list) or not raw:
        raise ConfigurationError("federal_computation.yaml: tax_brackets invalid")
    out: list[tuple[int | None, float]] = []
    for row in raw:
        if not isinstance(row, dict):
            raise ConfigurationError("tax_brackets rows must be mappings")
        upper = row.get("upper")
        if upper is not None and not isinstance(upper, int):
            raise ConfigurationError("tax_brackets.upper must be int or null")
        rate = row.get("rate")
        if not isinstance(rate, (int, float)):
            raise ConfigurationError("tax_brackets.rate must be numeric")
        out.append((upper, float(rate)))
    return out


def compute_agi(fed: dict[str, Any], wages: int, interest: int, dividends: int) -> int:
    comps = fed.get("agi_components")
    if comps != ["wages", "taxable_interest", "ordinary_dividends"]:
        raise ConfigurationError(
            "federal_computation.yaml agi_components mismatch — update compute.py if intentional"
        )
    return int(wages + interest + dividends)


def standard_deduction(gen: dict[str, Any], status: FilingStatus) -> int:
    table = gen.get("standard_deduction_by_status")
    if not isinstance(table, dict):
        raise ConfigurationError("generator_config: standard_deduction_by_status missing")
    v = table.get(status)
    if not isinstance(v, int):
        raise ConfigurationError(f"No standard deduction for filing status {status!r}")
    return int(v)


def compute_income_tax(fed: dict[str, Any], taxable_income: int) -> int:
    if taxable_income <= 0:
        return 0
    brackets = _brackets(fed)
    tax_total = 0
    prev_top = 0
    remaining = taxable_income
    for upper, rate in brackets:
        if remaining <= 0:
            break
        top = upper if upper is not None else None
        if top is None:
            width = remaining
        else:
            width = min(remaining, top - prev_top)
        if width > 0:
            tax_total += int(round(width * rate))
            remaining -= width
        prev_top = top if top is not None else prev_top
    if remaining > 0 and brackets[-1][0] is not None:
        raise ConfigurationError("federal tax brackets did not exhaust taxable income")
    return tax_total


def compute_federal_lines(
    gen: dict[str, Any],
    fed: dict[str, Any],
    *,
    wages: int,
    interest: int,
    dividends_ordinary: int,
    federal_withholding: int,
    filing_status: FilingStatus,
) -> dict[str, int]:
    agi = compute_agi(fed, wages, interest, dividends_ordinary)
    std = standard_deduction(gen, filing_status)
    taxable = max(0, agi - std)
    total_tax = compute_income_tax(fed, taxable)
    return {
        "wages": wages,
        "taxable_interest": interest,
        "ordinary_dividends": dividends_ordinary,
        "agi": agi,
        "standard_deduction": std,
        "taxable_income": taxable,
        "total_tax": total_tax,
        "federal_withholding": federal_withholding,
    }


def compute_state_bundle(
    gen: dict[str, Any],
    st: dict[str, Any],
    *,
    state_code: str,
    agi: int,
    wages: int,
    additions: int,
    subtractions: int,
) -> dict[str, Any]:
    rates_cfg = st.get("rates")
    if not isinstance(rates_cfg, dict) or state_code not in rates_cfg:
        raise ConfigurationError(f"state_computation.yaml: no rate for state {state_code!r}")
    rate = float(rates_cfg[state_code])
    state_taxable = max(0, agi + additions - subtractions)
    state_tax = int(round(state_taxable * rate))
    lines = {
        "state_wages": wages,
        "additions": additions,
        "subtractions": subtractions,
        "state_taxable_income": state_taxable,
        "state_tax": state_tax,
    }
    return {
        "code": state_code,
        "adjustments": {"additions": additions, "subtractions": subtractions},
        "lines": lines,
        "tax_computed": state_tax,
    }


def effective_federal_rate(total_tax: int, agi: int) -> float:
    if agi <= 0:
        return 0.0
    return round(total_tax / agi, 4)
