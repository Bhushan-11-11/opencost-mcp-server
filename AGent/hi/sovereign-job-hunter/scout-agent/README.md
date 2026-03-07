# Scout Agent

## Role

The `scout-agent` searches the public market and emits structured `JobManifest` records.

## Base Sample

Use `../deep-search` as the implementation reference.

## Adaptations Needed

- replace research-report output with `JobManifest`
- search across role postings, company pages, engineering blogs, and public signals
- extract:
  - required skills
  - preferred skills
  - company culture clues
  - stack clues
  - compensation text when present
- rank roles against the candidate profile

## Output Contract

Primary output is `shared.schemas.JobManifest`.

## Search Priorities For This Candidate

- AI/ML Engineer
- GenAI Engineer
- LLM Engineer
- Applied AI Engineer
- RAG Engineer
- AI Backend Engineer
- MLOps Engineer
