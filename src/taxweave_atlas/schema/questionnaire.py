from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class QuestionnaireAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q_wages_reported: int
    q_foreign_account: bool = False
    q_crypto: bool = False
    q_energy_credits: bool = False
    # Future keyed answers — add when specs require them (do not guess defaults in reconciliation).
    extensions: dict[str, bool | int | str] = Field(default_factory=dict)


class QuestionnairePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: QuestionnaireAnswers
