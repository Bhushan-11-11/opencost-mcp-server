# Architecture

## System Overview

The system is split into a local trust domain and a cloud/public domain.

### Local Trust Domain

- `vault-agent`
- local documents and project code
- local Ollama runtime
- optional local Qdrant
- claim registry and verification evidence

### Public/Cloud Domain

- `scout-agent`
- `execution-agent`
- optional hosted search and connector infrastructure

## Data Flow

1. `scout-agent` discovers a role and emits a `JobManifest`.
2. `vault-agent` reads the `JobManifest`, retrieves matching evidence from local documents and code, and produces a `ResumeRewriteRequest` result set.
3. `verifier-agent` checks every proposed claim against local evidence and returns a `VerifiedResumePatch`.
4. `execution-agent` receives a sanitized application package and submits only after verification status is acceptable.
5. Submission results are written to an application ledger for traceability.

## Privacy Rules

- Raw master resume, salary constraints, and internal project notes remain local.
- Only job-specific rewritten material and minimally required candidate metadata can cross out of the local domain.
- Every outbound package should be tagged with a sensitivity level.

## Storage Strategy

Use filesystem-first storage, then add Qdrant only if retrieval quality needs it.

- Filesystem source of truth:
  - resume
  - cover letter
  - project folders
  - proof snippets
  - generated application artifacts
- Optional Qdrant collections:
  - `candidate_documents`
  - `project_evidence`
  - `job_manifests`
  - `application_history`

## Agent Mapping To Existing Samples

- `scout-agent` <- `deep-search`
- `verifier-agent` <- `llm-auditor`
- `execution-agent` <- `parallel_task_decomposition_execution`
- `vault-agent` <- custom implementation, borrowing retrieval and orchestration ideas only

## First Build Milestone

First milestone should produce this local-only path:

1. load candidate profile
2. ingest resume and cover letter
3. accept one job description
4. produce rewritten resume bullets
5. verify each bullet against evidence
6. export one sanitized application package
