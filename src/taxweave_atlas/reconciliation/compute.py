from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ConfigurationError, ReconciliationError
from taxweave_atlas.reconciliation.paths_util import resolve_dotted_path as resolve_path
from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.schema.executive import ExecutiveSummary
from taxweave_atlas.schema.federal import FederalFormLines, FederalReturn
from taxweave_atlas.schema.profile import FilingStatus
from taxweave_atlas.schema.state import StateAdjustments, StateReturn, StateReturnLines
from taxweave_atlas.schema.supporting import SupportingDocument, SupportingDocumentsIndex


def _progressive_tax(taxable: int, brackets: list[dict[str, Any]]) -> int:
    if taxable <= 0:
        return 0
    tax_total = 0
    prev_top = 0
    remaining = taxable
    for row in brackets:
        upper = row.get("upper")
        rate = float(row["rate"])
        top = upper if upper is not None else None
        if remaining <= 0:
            break
        if top is None:
            width = remaining
        else:
            width = min(remaining, top - prev_top)
        if width > 0:
            tax_total += int(round(width * rate))
            remaining -= width
        prev_top = top if top is not None else prev_top
    if remaining > 0 and brackets[-1].get("upper") is not None:
        raise ConfigurationError("marginal_brackets did not exhaust taxable income")
    return tax_total


def _std_deduction(comp: dict[str, Any], tax_year: int, filing_status: FilingStatus) -> int:
    by_year = comp["standard_deduction_by_year"]
    y = by_year.get(str(tax_year))
    if not isinstance(y, dict):
        raise ReconciliationError(f"No standard deduction table for year {tax_year}")
    v = y.get(filing_status)
    if not isinstance(v, int):
        raise ReconciliationError(f"No standard deduction for filing status {filing_status!r} in {tax_year}")
    return int(v)


def assert_scope(case: SyntheticTaxCase, scope: dict[str, Any]) -> None:
    if case.tax_year not in scope["supported_tax_years"]:
        raise ReconciliationError(f"Tax year {case.tax_year} outside reconciliation scope")
    st = case.profile.address.state
    if st not in scope["supported_states"]:
        raise ReconciliationError(f"State {st!r} outside reconciliation scope")

    allowed_o = set(scope["supported_other_ordinary_income_keys"])
    for k in case.income.other_ordinary_income:
        if k not in allowed_o:
            raise ReconciliationError(
                f"Unsupported other_ordinary_income key {k!r} — add to scope or remove from case"
            )

    allowed_p = set(scope["supported_passive_income_keys"])
    for k in case.income.passive_income:
        if k not in allowed_p:
            raise ReconciliationError(
                f"Unsupported passive_income key {k!r} — add to scope or remove from case"
            )


def compute_agi(case: SyntheticTaxCase, scope: dict[str, Any]) -> tuple[int, dict[str, int]]:
    d = case.model_dump(mode="json")
    breakdown: dict[str, int] = {}
    total = 0
    for row in scope["agi_components"]:
        field = row["field"]
        src = row["source"]
        optional = bool(row.get("optional"))
        default = int(row.get("default", 0))
        try:
            v = resolve_path(d, src)
            if v is None:
                val = default
            else:
                val = int(v)
        except KeyError:
            if optional:
                val = default
            else:
                raise ReconciliationError(f"Missing AGI component path {src!r}") from None
        breakdown[field] = val
        total += val
    return total, breakdown


def apply_credits(pre_credit_tax: int, case: SyntheticTaxCase, credit_rules: dict[str, Any]) -> tuple[int, int, int]:
    """
    Implements `config/reconciliation/credits.yaml` credit_application:
    nonrefundable capped at pre-credit tax, then refundable offsets remainder, floored at net_tax_floor.
    """
    refundable_cfg = credit_rules.get("refundable") or {}
    floor = int(refundable_cfg.get("net_tax_floor", 0))

    nonref = [c.amount for c in case.credits.credits if not c.refundable]
    ref = [c.amount for c in case.credits.credits if c.refundable]
    nonref_sum = sum(nonref)
    ref_sum = sum(ref)
    nonref_applied = min(pre_credit_tax, nonref_sum)
    after_nonref = pre_credit_tax - nonref_applied
    ref_applied = min(after_nonref, ref_sum)
    total_tax = max(floor, after_nonref - ref_applied)
    return total_tax, nonref_applied, ref_applied


def build_federal_return(case: SyntheticTaxCase, *, agi: int, bundle: dict[str, Any]) -> FederalReturn:
    comp = bundle["computation"]
    fs: FilingStatus = case.profile.filing_status
    statutory_std = _std_deduction(comp, case.tax_year, fs)

    itemized_sum = (
        sum(case.deductions.itemized_components.values())
        if case.deductions.elected_method == "itemized"
        else 0
    )
    if case.deductions.elected_method == "standard" and itemized_sum != 0:
        raise ReconciliationError("Standard election with non-empty itemized_components")

    deduction_applied = max(statutory_std, itemized_sum)
    taxable_income = max(0, agi - deduction_applied)

    pre_credit = _progressive_tax(taxable_income, comp["marginal_brackets"])
    total_tax, nr_app, ref_app = apply_credits(pre_credit, case, bundle["credit_application"])

    inc = case.income
    addl: dict[str, int] = {
        "statutory_standard_deduction": statutory_std,
        "schedule_a_total": itemized_sum,
        "itemized_elected": 1 if case.deductions.elected_method == "itemized" else 0,
        "pre_credit_income_tax": pre_credit,
        "nonrefundable_credits_applied": nr_app,
        "refundable_credits_applied": ref_app,
    }

    lines = FederalFormLines(
        wages=inc.wages,
        taxable_interest=inc.interest,
        ordinary_dividends=inc.dividends_ordinary,
        agi=agi,
        standard_deduction=deduction_applied,
        taxable_income=taxable_income,
        total_tax=total_tax,
        federal_withholding=inc.federal_withholding,
        additional_lines=addl,
    )

    if lines.wages != inc.wages or lines.taxable_interest != inc.interest:
        raise ReconciliationError("Federal wage/interest lines must mirror income sources")
    if lines.ordinary_dividends != inc.dividends_ordinary:
        raise ReconciliationError("Federal dividend line must mirror income.dividends_ordinary")

    return FederalReturn(lines=lines)


def build_state_return(case: SyntheticTaxCase, agi: int, bundle: dict[str, Any]) -> StateReturn:
    comp = bundle["computation"]
    code = case.state.code
    rates = comp["state_stub_rates"]
    if code not in rates:
        raise ReconciliationError(f"No state_stub_rates entry for state {code!r}")

    adj = case.state.adjustments
    state_taxable = max(0, agi + adj.additions - adj.subtractions)
    rate = float(rates[code])
    state_tax = int(round(state_taxable * rate))

    lines = StateReturnLines(
        state_wages=case.income.wages,
        additions=adj.additions,
        subtractions=adj.subtractions,
        state_taxable_income=state_taxable,
        state_tax=state_tax,
    )
    return StateReturn(
        code=code,
        adjustments=StateAdjustments(additions=adj.additions, subtractions=adj.subtractions),
        lines=lines,
        tax_computed=state_tax,
    )


def build_executive_summary(case: SyntheticTaxCase, federal: FederalReturn, state: StateReturn) -> ExecutiveSummary:
    fl = federal.lines
    agi = fl.agi
    eff = round(fl.total_tax / agi, 4) if agi > 0 else 0.0
    return ExecutiveSummary(
        agi=fl.agi,
        taxable_income=fl.taxable_income,
        total_tax=fl.total_tax,
        federal_withholding=fl.federal_withholding,
        state_tax=state.tax_computed,
        effective_rate_federal=eff,
    )


def sync_supporting_documents(case: SyntheticTaxCase) -> SupportingDocumentsIndex:
    """Rebuild supporting docs in stable order so PDF mappers can rely on W-2 then 1099-INT."""
    inc = case.income
    slug = str(case.questionnaire.answers.extensions.get("dataset_slug", f"TY{case.tax_year}"))
    docs: list[SupportingDocument] = [
        SupportingDocument(
            kind="w2",
            document_id=f"W2-{slug}",
            display_name="Synthetic Form W-2",
            key_amounts={"wages": inc.wages, "federal_withholding": inc.federal_withholding},
            key_strings={"employer_ein": inc.w2.employer_ein},
        ),
        SupportingDocument(
            kind="1099_int",
            document_id=f"1099INT-{slug}",
            display_name="Synthetic Form 1099-INT",
            key_amounts={"interest": inc.interest},
            key_strings={"payer_tin": inc.forms_1099_int.payer_tin},
        ),
    ]
    if inc.dividends_ordinary > 0:
        docs.append(
            SupportingDocument(
                kind="1099_div",
                document_id=f"1099DIV-{slug}",
                display_name="Synthetic Form 1099-DIV",
                key_amounts={"ordinary_dividends": inc.dividends_ordinary},
                key_strings={"payer_tin": inc.forms_1099_int.payer_tin},
            )
        )
    return SupportingDocumentsIndex(documents=docs)
