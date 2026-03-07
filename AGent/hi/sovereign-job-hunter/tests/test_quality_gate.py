from __future__ import annotations

import pytest

from conftest import load_module
from shared.schemas import ResumeClaim, VerifiedResumePatch


run_module = load_module("run_sjh.py", "run_sjh_test")
ApplicationPacket = run_module.ApplicationPacket
_quality_gate = run_module._quality_gate


def test_quality_gate_accepts_valid_packet() -> None:
    claims = [
        ResumeClaim(claim_id=f"c{i}", text=f"Improved model latency by {i+1}% using Python and FastAPI.")
        for i in range(6)
    ]
    packet = ApplicationPacket(
        candidate_id="cand-1",
        job_id="job-1",
        sanitized_resume_text=(
            "Professional Summary\n"
            "Technical Skills\n"
            "Professional Experience\n"
        ),
        sanitized_cover_letter_text=(
            "Dear Hiring Manager,\n\n"
            "I am excited to apply for this role with strong experience in production AI systems. "
            "I have delivered measurable outcomes and cross-functional leadership across multiple projects. "
            "My work includes scalable APIs, MLOps pipelines, and stakeholder communication for delivery. "
            "I also led deployment improvements, monitoring improvements, and quantifiable product outcomes "
            "across multiple releases with measurable impact and stakeholder alignment over time. "
            "I bring strong ownership, clear communication, and end-to-end execution from discovery through delivery. "
            "In recent teams I partnered with product, design, and platform stakeholders to define measurable goals, "
            "deliver milestones, and maintain reliable execution under deadlines. "
            "I proactively identify risks, align teams on mitigation plans, and keep delivery quality high through testing and monitoring. "
            "I am confident this operating style matches your team values and role expectations. "
            "I would value the chance to contribute the same rigor, technical depth, and collaborative execution in this position. "
            "Thank you for your consideration, and I look forward to discussing how I can help your team ship reliable, high-impact outcomes.\n\n"
            "Sincerely,\nTest User"
        ),
        verified_patch=VerifiedResumePatch(
            candidate_id="cand-1",
            job_id="job-1",
            rewritten_claims=claims,
            overall_status="approved",
        ),
    )

    _quality_gate(packet)


def test_quality_gate_rejects_invalid_packet() -> None:
    packet = ApplicationPacket(
        candidate_id="cand-1",
        job_id="job-1",
        sanitized_resume_text="Professional Summary\n",
        sanitized_cover_letter_text="Hi\n",
        verified_patch=VerifiedResumePatch(
            candidate_id="cand-1",
            job_id="job-1",
            rewritten_claims=[],
            overall_status="needs_review",
        ),
    )

    with pytest.raises(RuntimeError):
        _quality_gate(packet)
