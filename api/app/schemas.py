"""The contracts. Change them only with your partner's review: the UI, the
evaluation script and your tests all depend on these shapes.

`Answer` is what the model must produce (section 3.4). `AskResponse` is what
the API returns to the UI and to eval/run_eval.py. The model's `reasoning` is
never sent to the user.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    follow_up: bool = Field(
        default=False,
        description="True when the question depends on an earlier turn. Never cached.",
    )


class Passage(BaseModel):
    """One retrieved chunk, as the retriever hands it to the generator."""

    chunk_id: str
    text: str
    source: str
    section: str
    page: int | None = None
    score: float = Field(description="Similarity, higher is closer (1 - cosine distance).")
    doc_version: str = ""
    superseded: bool = False


class Citation(BaseModel):
    source: str
    section: str
    page: int | None = None


class Answer(BaseModel):
    """The model's output contract. Send its JSON schema to the model, then validate.

    The order matters: the model decides whether the evidence supports an answer before it
    writes the answer, and the descriptions are part of the schema it is given.
    """

    reasoning: str = Field(description="Short notes on which evidence answers the question.")
    answered_from_context: bool = Field(
        description="true when the evidence supports an answer, even a short one such as a "
        "number. false only when the evidence does not contain the answer.")
    answer: str = Field(description="The answer, in one or two sentences, from the evidence only.")
    citations: list[Citation] = Field(
        description="One entry per evidence block used. Copy source and section exactly from "
        "that block's attributes. Empty when answered_from_context is false.")
    confidence: Literal["high", "medium", "low"]


class RetrievedRef(BaseModel):
    """What the response says was retrieved. eval/run_eval.py scores against this."""

    chunk_id: str
    source: str
    section: str
    page: int | None = None
    score: float


class AskResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    answered_from_context: bool
    confidence: Literal["high", "medium", "low"]
    retrieved: list[RetrievedRef]
    provider: str
    cached: bool = False