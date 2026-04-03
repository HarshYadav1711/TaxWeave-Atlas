from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeductionPacket(BaseModel):
    """
    Declared deductions / method election. Numeric authority lives in config/tax_rules
    once reconciliation is implemented.
    """

    model_config = ConfigDict(extra="forbid")

    elected_method: Literal["not_specified", "standard", "itemized"] = "not_specified"
    standard_amount_override: int | None = None
    itemized_components: dict[str, int] = Field(default_factory=dict)
    adjustments_to_agi: dict[str, int] = Field(default_factory=dict)
