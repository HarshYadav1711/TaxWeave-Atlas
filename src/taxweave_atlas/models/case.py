from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

FilingStatus = Literal["single", "married_filing_jointly", "head_of_household"]


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line1: str
    city: str
    state: str
    zip: str


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_first_name: str
    primary_last_name: str
    spouse_first_name: str | None = None
    spouse_last_name: str | None = None
    filing_status: FilingStatus
    taxpayer_label: str
    synthetic_ssn_primary: str
    synthetic_ssn_spouse: str | None = None
    address: Address

    @computed_field
    @property
    def primary_full_name(self) -> str:
        return f"{self.primary_first_name} {self.primary_last_name}"


class QuestionnaireAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q_wages_reported: int
    q_foreign_account: bool
    q_crypto: bool
    q_energy_credits: bool


class Questionnaire(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: QuestionnaireAnswers


class W2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employer_name: str
    employer_ein: str
    employee_name: str
    employee_ssn: str
    social_security_wages: int
    medicare_wages: int


class Form1099Int(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payer_name: str
    payer_tin: str
    recipient_name: str
    recipient_tin: str
    interest_reported: int


class Income(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wages: int
    interest: int
    dividends_ordinary: int
    federal_withholding: int
    w2: W2
    forms_1099_int: Form1099Int

    @model_validator(mode="after")
    def w2_aligns(self) -> Income:
        if self.w2.social_security_wages != self.wages:
            raise ValueError("income.w2.social_security_wages must equal income.wages")
        if self.w2.medicare_wages != self.wages:
            raise ValueError("income.w2.medicare_wages must equal income.wages")
        if self.forms_1099_int.interest_reported != self.interest:
            raise ValueError("forms_1099_int.interest_reported must equal income.interest")
        return self


class FederalLines(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wages: int
    taxable_interest: int
    ordinary_dividends: int
    agi: int
    standard_deduction: int
    taxable_income: int
    total_tax: int
    federal_withholding: int


class FederalReturn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: FederalLines


class StateAdjustments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    additions: int
    subtractions: int


class StateLines(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_wages: int
    additions: int
    subtractions: int
    state_taxable_income: int
    state_tax: int


class StateReturn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    adjustments: StateAdjustments
    lines: StateLines
    tax_computed: int

    @model_validator(mode="after")
    def tax_matches_lines(self) -> StateReturn:
        if self.tax_computed != self.lines.state_tax:
            raise ValueError("state.tax_computed must equal state.lines.state_tax")
        return self


class ExecutiveSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agi: int
    taxable_income: int
    total_tax: int
    federal_withholding: int
    state_tax: int
    effective_rate_federal: float


class TaxCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tax_year: int
    profile: Profile
    questionnaire: Questionnaire
    income: Income
    federal: FederalReturn
    state: StateReturn
    executive_summary: ExecutiveSummary

    @model_validator(mode="after")
    def cross_checks(self) -> TaxCase:
        if self.questionnaire.answers.q_wages_reported != self.income.wages:
            raise ValueError("questionnaire q_wages_reported must equal income.wages")
        if self.federal.lines.wages != self.income.wages:
            raise ValueError("federal.lines.wages must equal income.wages")
        if self.federal.lines.taxable_interest != self.income.interest:
            raise ValueError("federal taxable_interest must equal income.interest")
        if self.federal.lines.ordinary_dividends != self.income.dividends_ordinary:
            raise ValueError("federal ordinary_dividends must match")
        if self.federal.lines.federal_withholding != self.income.federal_withholding:
            raise ValueError("federal withholding must match income")
        ex = self.executive_summary
        fl = self.federal.lines
        if ex.agi != fl.agi or ex.taxable_income != fl.taxable_income:
            raise ValueError("executive summary must match federal lines")
        if ex.total_tax != fl.total_tax or ex.federal_withholding != fl.federal_withholding:
            raise ValueError("executive summary tax fields must match federal lines")
        if ex.state_tax != self.state.tax_computed:
            raise ValueError("executive summary state_tax must match state.tax_computed")
        return self

    def as_flat_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
