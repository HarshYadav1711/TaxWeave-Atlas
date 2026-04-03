from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FormW2(BaseModel):
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


class IncomeSources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wages: int
    interest: int
    dividends_ordinary: int
    federal_withholding: int
    w2: FormW2
    forms_1099_int: Form1099Int
    # Placeholder buckets for future schedules (amounts only; reconciliation defines treatment).
    other_ordinary_income: dict[str, int] = Field(default_factory=dict)
    passive_income: dict[str, int] = Field(default_factory=dict)
