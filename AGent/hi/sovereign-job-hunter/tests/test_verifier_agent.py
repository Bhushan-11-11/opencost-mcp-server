from __future__ import annotations

from conftest import load_module
from shared.schemas import EvidenceSnippet


verifier_module = load_module("verifier-agent/agent.py", "verifier_agent_test")

VerifierAgent = verifier_module.VerifierAgent
ResumeClaim = verifier_module.ResumeClaim
VerificationStatus = verifier_module.VerificationStatus


def test_verify_tailored_claims_marks_unsupported_when_no_evidence() -> None:
    agent = VerifierAgent(
        use_gemini=False,
        gemini_model=None,
        gemini_api_key=None,
        gemini_timeout_seconds=None,
        gemini_temperature=None,
    )

    claim = ResumeClaim(claim_id="c1", text="Built RAG pipeline", evidence=[])
    patch = agent.verify_tailored_claims(
        candidate_id="cand-1", job_id="job-1", tailored_claims=[claim]
    )

    assert patch.overall_status == "needs_review"
    assert patch.rewritten_claims[0].verification_status == VerificationStatus.UNSUPPORTED


def test_verify_tailored_claims_marks_verified_on_strong_overlap() -> None:
    agent = VerifierAgent(
        use_gemini=False,
        gemini_model=None,
        gemini_api_key=None,
        gemini_timeout_seconds=None,
        gemini_temperature=None,
    )

    evidence = EvidenceSnippet(
        evidence_id="ev-1",
        source_doc_id="resume",
        excerpt="Built a Python FastAPI RAG system with retrieval pipelines and evaluation.",
        rationale="From resume",
        confidence=0.95,
    )
    claim = ResumeClaim(
        claim_id="c2",
        text="Built a Python FastAPI RAG system with retrieval pipelines and evaluation.",
        evidence=[evidence],
    )

    patch = agent.verify_tailored_claims(
        candidate_id="cand-1", job_id="job-2", tailored_claims=[claim]
    )

    assert patch.overall_status == "approved"
    assert patch.rewritten_claims[0].verification_status == VerificationStatus.VERIFIED
