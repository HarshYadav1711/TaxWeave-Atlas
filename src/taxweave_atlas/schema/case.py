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
from taxweave_atlas.schema.supporting import SupportingDocumentsIndex


class SyntheticTaxCase(BaseModel):
    """
    Single aggregate for one synthetic taxpayer-year. All downstream PDFs and validators
    should consume this shape (or projections of it).
    """

    model_config = ConfigDict(extra="forbid")

    tax_year: int
    profile: TaxpayerProfile
    questionnaire: QuestionnairePacket
    income: IncomeSources
    deductions: DeductionPacket = Field(default_factory=DeductionPacket)
    credits: CreditsPacket = Field(default_factory=CreditsPacket)
    supporting_documents: SupportingDocumentsIndex = Field(default_factory=SupportingDocumentsIndex)
    federal: FederalReturn
    state: StateReturn
    executive_summary: ExecutiveSummary
