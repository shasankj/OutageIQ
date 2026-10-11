"""Structured outputs (Pydantic) for every LLM call, so nothing downstream parses free text."""
from typing import Literal

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    category: Literal["answer", "clarify", "refuse_write", "refuse_injection", "out_of_scope"]
    clarifying_question: str = Field(description="One short question to the user when category is clarify, else empty.")


class SQLDraft(BaseModel):
    interpretation: str = Field(description="One sentence: how you interpreted the question and any assumption made.")
    sql: str = Field(description="A single PostgreSQL SELECT statement.")


class SemanticVerdict(BaseModel):
    answers_question: bool
    problem: str = Field(description="If answers_question is false: what is wrong and how to fix it. Else empty.")


class AnswerDraft(BaseModel):
    answer: str
