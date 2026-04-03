"""Reconciliation-owned MeF-shaped schedule stubs (amounts are path-copied from the case, not recomputed)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StructuralMefDocument(BaseModel):
    """One ReturnData child document: element tag name + flat amount fields for prompt XML."""

    model_config = ConfigDict(extra="forbid")

    element_name: str
    document_id: str
    fields: dict[str, int] = Field(default_factory=dict)


class StructuralMefPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[StructuralMefDocument] = Field(default_factory=list)
