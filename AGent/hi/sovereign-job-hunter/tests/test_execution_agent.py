from __future__ import annotations

from pathlib import Path

from conftest import load_module
from shared.schemas import VerifiedResumePatch


execution_module = load_module("execution-agent/agent.py", "execution_agent_test")

ExecutionAgent = execution_module.ExecutionAgent
ApplicationPacket = execution_module.ApplicationPacket
JobManifest = execution_module.JobManifest
def _build_packet(status: str) -> ApplicationPacket:
    return ApplicationPacket(
        candidate_id="cand-1",
        job_id="job-1",
        sanitized_resume_text="Professional Summary\nTechnical Skills\nProfessional Experience\n",
        sanitized_cover_letter_text="Dear Hiring Manager,\n\nHello\n\nSincerely,\nTest",
        verified_patch=VerifiedResumePatch(
            candidate_id="cand-1",
            job_id="job-1",
            overall_status=status,
            rewritten_claims=[],
        ),
        outbound_fields={"candidate_name": "Test User", "candidate_email": "test@example.com"},
    )


def _build_manifest() -> JobManifest:
    return JobManifest(
        job_id="job-1",
        source="manual",
        company="Example",
        title="AI Engineer",
        description_text="desc",
    )


def test_submit_blocks_without_approval(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    agent = ExecutionAgent(ledger_path=str(ledger_path))

    entry, results = agent.submit(
        packet=_build_packet("approved"),
        manifest=_build_manifest(),
        approved=False,
        dry_run=True,
        providers=["stackone"],
    )

    assert entry.status == "awaiting_approval"
    assert results == []


def test_submit_dry_run_success(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    agent = ExecutionAgent(ledger_path=str(ledger_path))

    entry, results = agent.submit(
        packet=_build_packet("approved"),
        manifest=_build_manifest(),
        approved=True,
        dry_run=True,
        providers=["stackone", "greenhouse"],
    )

    assert entry.status == "dry_run_submitted"
    assert len(results) == 2
