from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from taxweave_atlas.schema.credits import CreditsPacket
from taxweave_atlas.schema.deductions import DeductionPacket
from taxweave_atlas.schema.executive import ExecutiveSummary
from taxweave_atlas.schema.federal import FederalReturn
from taxweave_atlas.schema.income import IncomeSources
from taxweave_atlas.schema.profile import TaxpayerProfile
from taxweave_atlas.schema.questionnaire import QuestionnairePacket
from taxweave_atlas.schema.state import StateReturn
from taxweave_atlas.schema.structural_mef import StructuralMefPacket
from taxweave_atlas.schema.supporting import SupportingDocumentsIndex


class SyntheticTaxCase(BaseModel):
    """
    **Canonical tax case** for one synthetic taxpayer-year: the single object from which
    all dataset artifacts must derive (client summary, inputs, completed return, executive
    summary, prompt XML/DOCX). Reconciliation fills federal, state, executive, and
    supporting-document slices before packaging.
    """

    model_config = ConfigDict(extra="forbid")

    tax_year: int
    profile: TaxpayerProfile
    questionnaire: QuestionnairePacket
    income: IncomeSources
    deductions: DeductionPacket = Field(default_factory=DeductionPacket)
    credits: CreditsPacket = Field(default_factory=CreditsPacket)
    supporting_documents: SupportingDocumentsIndex = Field(default_factory=SupportingDocumentsIndex)
    structural_mef: StructuralMefPacket = Field(default_factory=StructuralMefPacket)
    federal: FederalReturn
    state: StateReturn
    executive_summary: ExecutiveSummary


# Alias for documentation / external integrations (same model).
TaxCase = SyntheticTaxCase
