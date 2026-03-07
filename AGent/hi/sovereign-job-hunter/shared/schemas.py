from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SensitivityLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    RESTRICTED = "restricted"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    REJECTED = "rejected"


class WorkPreference(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    FLEXIBLE = "flexible"


class DocumentRef(BaseModel):
    doc_id: str = Field(description="Stable local identifier for the document.")
    path: str = Field(description="Absolute local filesystem path.")
    title: str
    sensitivity: SensitivityLevel = SensitivityLevel.PRIVATE


class CandidateProfile(BaseModel):
    candidate_id: str
    full_name: str
    email: str
    location: str | None = None
    target_titles: list[str] = Field(default_factory=list)
    target_skills: list[str] = Field(default_factory=list)
    work_preferences: list[WorkPreference] = Field(default_factory=list)
    salary_floor_usd: int | None = None
    notes: list[str] = Field(default_factory=list)
    source_documents: list[DocumentRef] = Field(default_factory=list)


class JobManifest(BaseModel):
    job_id: str
    source: str = Field(description="LinkedIn, Indeed, company site, recruiter, etc.")
    url: HttpUrl | None = None
    company: str
    title: str
    location: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    compensation_text: str | None = None
    description_text: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    company_signals: list[str] = Field(default_factory=list)
    tech_stack_signals: list[str] = Field(default_factory=list)
    scout_summary: str | None = None
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL


class EvidenceSnippet(BaseModel):
    evidence_id: str
    source_doc_id: str
    excerpt: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    path: str | None = None
    line_hint: str | None = None


class ResumeClaim(BaseModel):
    claim_id: str
    text: str
    skill_tags: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSnippet] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.PARTIAL
    reviewer_notes: str | None = None


class ResumeRewriteRequest(BaseModel):
    candidate_id: str
    job_id: str
    target_title: str
    job_focus_areas: list[str] = Field(default_factory=list)
    preserve_constraints: list[str] = Field(default_factory=list)
    max_bullets: int = 8


class VerifiedResumePatch(BaseModel):
    candidate_id: str
    job_id: str
    summary_patch: str | None = None
    headline_patch: str | None = None
    rewritten_claims: list[ResumeClaim] = Field(default_factory=list)
    overall_status: Literal["approved", "needs_review", "rejected"] = "needs_review"
    verification_notes: list[str] = Field(default_factory=list)


class ApplicationPacket(BaseModel):
    candidate_id: str
    job_id: str
    sanitized_resume_text: str
    sanitized_cover_letter_text: str | None = None
    verified_patch: VerifiedResumePatch
    outbound_fields: dict[str, str] = Field(default_factory=dict)
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL


class ApplicationLedgerEntry(BaseModel):
    application_id: str
    candidate_id: str
    job_id: str
    submitted_at: str | None = None
    channel: str
    status: str
    notes: list[str] = Field(default_factory=list)
