from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SupportingDocKind = Literal[
    "w2",
    "1099_int",
    "1099_div",
    "1099_nec",
    "brokerage_statement",
    "other",
]


class SupportingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SupportingDocKind
    document_id: str
    display_name: str
    # Normalized key figures extracted for reconciliation (schema only; rules decide usage).
    key_amounts: dict[str, int] = Field(default_factory=dict)
    key_strings: dict[str, str] = Field(default_factory=dict)


class SupportingDocumentsIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[SupportingDocument] = Field(default_factory=list)
