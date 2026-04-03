from __future__ import annotations

from taxweave_atlas.exceptions import ValidationError
from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.schema.profile import FilingStatus


def validate_generated_case(case: SyntheticTaxCase) -> None:
    """Reject impossible or internally contradictory synthetic profiles early."""
    p = case.profile
    q = case.questionnaire.answers
    inc = case.income
    ded = case.deductions
    fl = case.federal.lines

    if inc.wages < 0 or inc.interest < 0 or inc.dividends_ordinary < 0:
        raise ValidationError("Income components cannot be negative")

    if inc.w2.social_security_wages != inc.wages or inc.w2.medicare_wages != inc.wages:
        raise ValidationError("W-2 wage boxes must match income.wages")

    if q.q_wages_reported != inc.wages:
        raise ValidationError("Questionnaire wages must equal income.wages")

    if inc.forms_1099_int.interest_reported != inc.interest:
        raise ValidationError("1099-INT interest must equal income.interest")

    if q.num_qualifying_children_under_17 != p.dependents_qualifying_children_under_17:
        raise ValidationError("Questionnaire child dependents must match profile")

    if q.num_other_dependents != p.dependents_other:
        raise ValidationError("Questionnaire other dependents must match profile")

    fs: FilingStatus = p.filing_status
    if fs in ("married_filing_jointly", "married_filing_separately"):
        if not p.spouse_first_name or not p.spouse_last_name or not p.synthetic_ssn_spouse:
            raise ValidationError(f"Filing status {fs} requires synthetic spouse identity fields")

    if fs == "single":
        if p.spouse_first_name or p.spouse_last_name or p.synthetic_ssn_spouse:
            raise ValidationError("Single filing must not include spouse identity fields")

    if fs == "head_of_household":
        if p.dependents_qualifying_children_under_17 + p.dependents_other < 1:
            raise ValidationError("Head of household requires at least one dependent")

    if fs == "qualifying_surviving_spouse":
        if p.dependents_qualifying_children_under_17 < 1:
            raise ValidationError("Qualifying surviving spouse requires at least one qualifying child")

    if p.synthetic_ssn_spouse is not None and p.synthetic_ssn_spouse == p.synthetic_ssn_primary:
        raise ValidationError("Spouse SSN must differ from primary SSN")

    if q.itemized_deduction_elected and ded.elected_method != "itemized":
        raise ValidationError("Itemized questionnaire flag inconsistent with deduction packet")

    if not q.itemized_deduction_elected and ded.elected_method == "itemized":
        raise ValidationError("Deduction packet itemized without questionnaire election")

    if ded.elected_method == "standard" and ded.itemized_components:
        raise ValidationError("Standard deduction election cannot include itemized components")

    if ded.elected_method == "itemized" and not ded.itemized_components:
        raise ValidationError("Itemized election requires at least one itemized component")

    for c in case.credits.credits:
        if c.amount < 0:
            raise ValidationError("Credit amounts cannot be negative")

    if q.has_self_employment_income and not inc.other_ordinary_income.get("self_employment_net"):
        raise ValidationError("Self-employment flag requires self_employment_net amount")

    if not q.has_self_employment_income and inc.other_ordinary_income.get("self_employment_net"):
        raise ValidationError("Self-employment amount present without questionnaire flag")

    if q.has_retirement_distributions and not inc.passive_income.get("retirement_distributions"):
        raise ValidationError("Retirement flag requires retirement_distributions amount")

    if not q.has_retirement_distributions and inc.passive_income.get("retirement_distributions"):
        raise ValidationError("Retirement distributions present without questionnaire flag")

    agi_expected = (
        inc.wages
        + inc.interest
        + inc.dividends_ordinary
        + sum(inc.other_ordinary_income.values())
        + sum(inc.passive_income.values())
    )
    if fl.agi != agi_expected:
        raise ValidationError(f"Federal AGI {fl.agi} inconsistent with income components ({agi_expected})")

    if fl.wages != inc.wages:
        raise ValidationError("Federal wages line must match income.wages")

    if fl.taxable_interest != inc.interest:
        raise ValidationError("Federal interest must match income.interest")

    if fl.ordinary_dividends != inc.dividends_ordinary:
        raise ValidationError("Federal dividends must match income")

    if fl.federal_withholding != inc.federal_withholding:
        raise ValidationError("Federal withholding mismatch")

    ex = case.executive_summary
    if ex.agi != fl.agi or ex.taxable_income != fl.taxable_income or ex.total_tax != fl.total_tax:
        raise ValidationError("Executive summary must match federal lines")

    if ex.federal_withholding != fl.federal_withholding:
        raise ValidationError("Executive withholding mismatch")

    if ex.state_tax != case.state.tax_computed:
        raise ValidationError("Executive state tax mismatch")

    if case.state.tax_computed != case.state.lines.state_tax:
        raise ValidationError("State tax_computed must equal lines.state_tax")
