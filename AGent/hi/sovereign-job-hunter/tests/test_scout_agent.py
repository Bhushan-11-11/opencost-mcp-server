from __future__ import annotations

from conftest import load_module


scout_module = load_module("scout-agent/agent.py", "scout_agent_test")
ScoutAgent = scout_module.ScoutAgent


def test_create_job_manifest_extracts_core_fields() -> None:
    agent = ScoutAgent()
    jd = """
    Company: Example Labs
    Title: Senior AI Engineer
    Location: Remote, US
    Compensation: $180,000 - $220,000

    Required skills: Python, FastAPI, Docker, Kubernetes
    Nice to have: LangChain, MLOps
    """

    manifest = agent.create_job_manifest(jd, source="manual", url=None)

    assert manifest.company == "Example Labs"
    assert manifest.title == "Senior AI Engineer"
    assert manifest.location == "Remote, US"
    assert "python" in manifest.required_skills
    assert manifest.job_id.startswith("job-")
