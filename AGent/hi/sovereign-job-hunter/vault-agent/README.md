# Vault Agent

## Role

The `vault-agent` is the local authority for candidate truth.

It should:

- load the master resume and cover letter
- ingest project code and notes
- retrieve evidence for job-relevant claims
- rewrite resume content locally with Ollama
- emit only sanitized outputs for downstream agents

## Runtime

- Primary model runtime: local Ollama
- Optional retrieval backend: local Qdrant
- Source of truth: local filesystem

## First Responsibilities

1. Parse candidate documents into structured profile data.
2. Build a local claim registry from resume bullets and project evidence.
3. Accept a `JobManifest` and create a `ResumeRewriteRequest`.
4. Generate rewritten bullets with evidence links.
5. Pass proposed claims to `verifier-agent`.

## Suggested Local Inputs

- `/Users/nagabhushan.addala/Desktop/AGent/Naga_addala_resume.pdf`
- `/Users/nagabhushan.addala/Desktop/AGent/Naga_addala_coverletter.pdf`
- selected project repositories and code snippets

## Notes For Your Profile

Prioritize evidence retrieval around:

- LLM prompt pipelines
- RAG systems
- LangChain and document retrieval
- FastAPI backends
- forecasting and classification models
- AWS, Azure, Docker, Kubernetes
