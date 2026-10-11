"""
Pydantic schemas for the Compliance Investigation Agent.

Structured output fields mirror the AgentRun model's JSON columns.
Each schema represents one element in the corresponding list column.
"""

from datetime import datetime

from pydantic import BaseModel


# =========================================================
# API request schema
# =========================================================

class AgentRunRequest(BaseModel):
    question: str


# =========================================================
# Structured output element schemas
# =========================================================


class AgentEvidence(BaseModel):
    """A single piece of evidence supporting the agent's finding."""

    claim: str
    source_document: str
    source_section_or_chunk: str
    supporting_text: str


class AgentConflict(BaseModel):
    """A conflict identified between two or more documents."""

    description: str
    documents: list[str]
    relationship: str


class AgentEvidenceGap(BaseModel):
    """An area where evidence is absent or insufficient."""

    description: str
    why_it_matters: str


class AgentRequirement(BaseModel):
    """A regulatory or policy requirement identified in the evidence."""

    requirement: str
    source_document: str
    source_section_or_chunk: str


class AgentAction(BaseModel):
    """A recommended remediation or compliance action."""

    action: str
    rationale: str


class AgentCitation(BaseModel):
    """A source citation referenced in the finding."""

    source_document: str
    source_section_or_chunk: str


# =========================================================
# Top-level finding schema
# =========================================================


class AgentFinding(BaseModel):
    """
    The complete structured output produced by one Agent run.
    This maps 1-to-1 to the populated fields of AgentRun.
    """

    finding: str | None = None
    evidence: list[AgentEvidence] = []
    conflicts: list[AgentConflict] = []
    evidence_gaps: list[AgentEvidenceGap] = []
    applicable_requirements: list[AgentRequirement] = []
    suggested_actions: list[AgentAction] = []
    citations: list[AgentCitation] = []


# =========================================================
# API response schema
# =========================================================


class AgentRunResponse(BaseModel):
    """
    Response schema for an AgentRun record returned from the API.
    Structured list fields are returned as lists of their element schemas
    (populated on completion) or empty lists (pending / failed).
    """

    id: int
    investigation_id: int
    user_id: int
    question: str
    status: str

    finding: str | None = None
    evidence: list[AgentEvidence] = []
    conflicts: list[AgentConflict] = []
    evidence_gaps: list[AgentEvidenceGap] = []
    applicable_requirements: list[AgentRequirement] = []
    suggested_actions: list[AgentAction] = []
    citations: list[AgentCitation] = []

    risk_score: int | None = None
    risk_level: str | None = None

    created_at: datetime

    model_config = {"from_attributes": True}
