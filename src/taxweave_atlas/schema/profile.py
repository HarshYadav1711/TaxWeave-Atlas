from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

FilingStatus = Literal[
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
    "qualifying_surviving_spouse",
]


class MailingAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line1: str
    line2: str | None = None
    city: str
    state: str
    zip: str


class TaxpayerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_first_name: str
    primary_last_name: str
    spouse_first_name: str | None = None
    spouse_last_name: str | None = None
    filing_status: FilingStatus
    taxpayer_label: str
    synthetic_ssn_primary: str
    synthetic_ssn_spouse: str | None = None
    address: MailingAddress

    @computed_field
    @property
    def primary_full_name(self) -> str:
        return f"{self.primary_first_name} {self.primary_last_name}"
