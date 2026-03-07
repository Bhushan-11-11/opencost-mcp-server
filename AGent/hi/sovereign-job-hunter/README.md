# Sovereign Job Hunter

Local-first job search and application system built around four cooperating agents:

- `vault-agent`: private candidate data, local evidence retrieval, local resume rewriting
- `scout-agent`: public market and job discovery
- `verifier-agent`: claim checking against local evidence
- `execution-agent`: controlled application submission workflow

## Design Priorities

- Sensitive data stays local by default
- Gemini is the active model runtime in this branch
- Qdrant is optional and only used for local retrieval/indexing
- Cloud agents operate on minimized, sanitized payloads
- Every rewritten claim should map back to evidence before submission

## Folder Layout

```text
sovereign-job-hunter/
  README.md
  architecture.md
  shared/
    __init__.py
    schemas.py
  vault-agent/
    README.md
  scout-agent/
    README.md
  verifier-agent/
    README.md
  execution-agent/
    README.md
```

## Recommended Reuse From Existing Samples

- `../deep-search`: starting point for `scout-agent`
- `../llm-auditor`: starting point for `verifier-agent`
- `../parallel_task_decomposition_execution`: starting point for `execution-agent`
- `../RAG`: retrieval pattern reference only; do not use its Vertex-only implementation as your local vault backend

## Initial Candidate Inputs

- `/Users/nagabhushan.addala/Desktop/AGent/Naga_addala_resume.pdf`
- `/Users/nagabhushan.addala/Desktop/AGent/Naga_addala_coverletter.pdf`

## Unified Run

Use one command to execute scout -> vault -> verifier -> PDF render -> execution ledger:

```bash
python3 run_sjh.py --job-file demo/jd.txt --approve-submit
```

Notes:
- default mode is dry-run submission (`--live-submit` enables queue mode for real connectors)
- outputs are written to `SJH_OUTPUT_DIR`
- ledger entries append to `SJH_LEDGER_PATH`

## Immediate Build Order

1. Implement `shared/schemas.py` as the contract boundary across agents.
2. Build `vault-agent` first because every other agent depends on its candidate and evidence outputs.
3. Adapt `scout-agent` from `deep-search` to emit `JobManifest` records instead of research reports.
4. Adapt `verifier-agent` from `llm-auditor` to verify claims against local evidence, not just web sources.
5. Adapt `execution-agent` to run gated application workflows and keep an audit trail.

## Production Hardening Additions

- `pyproject.toml`, `requirements.txt`, and `Makefile` now provide reproducible install/test commands.
- Structured JSON logging and metrics events are enabled via `shared/observability.py` and used in `run_sjh.py`.
- Security guardrail: CI blocks tracked `.env` files and runs `gitleaks` secret scanning.
- Automated tests cover scout parsing, verifier status logic, execution gating, and application quality gate.

### Quick Start (Hardened)

```bash
cd hi/sovereign-job-hunter
make install
make test
python3 run_sjh.py --job-file demo/jd.txt --approve-submit
```
