# Production Readiness Review + Core Python Explanations (`hi/`)

## Scope reviewed
- `hi/deep-search`
- `hi/llm-auditor`
- `hi/parallel_task_decomposition_execution`
- `hi/sovereign-job-hunter`

## Top production gaps (priority order)

### P0 (must fix before production)
- Secrets management risk: a real `.env` file exists in repo tree at `hi/sovereign-job-hunter/.env` and likely carries runtime credentials.
- No automated test coverage for three projects (`deep-search`, `parallel_task_decomposition_execution`, `sovereign-job-hunter`), so critical flows are unguarded.
- `sovereign-job-hunter` has no package/dependency manifest (`pyproject.toml`/`requirements.txt` absent), making builds non-reproducible.
- `parallel_task_decomposition_execution` execution tools are mock implementations, not real external integrations (`tools.py` mock publish/create behavior).

### P1 (high impact)
- Fragile import strategy in `sovereign-job-hunter`: multiple `sys.path` mutations + dynamic module loading from file paths instead of package imports.
- Runtime error handling is mostly fail-fast with uncaught exceptions; no structured retry taxonomy for external model/API calls except limited retries in one client path.
- Observability is limited: no request IDs, no structured JSON logs, no metrics/tracing, and no redaction layer for PII-heavy payloads.
- No CI workflows detected (lint/type/test/security scans are not enforced at PR time).
- Config validation is spread across runtime logic rather than centralized typed settings classes.

### P2 (important hardening)
- Supply-chain inconsistency: mixed lock/constraints patterns (`uv.lock`, Poetry, requirements), and one requirements file has duplicate/variant dependency declarations.
- No clear API/service boundary for orchestration in `sovereign-job-hunter`; CLI script currently acts as both composition root and business workflow.
- Schema and output contracts are strong (Pydantic), but no schema-versioning/migration strategy for persisted artifacts (`json`/`jsonl`).
- No load/performance tests for LLM-heavy loops (`deep-search` iterative research, verifier + resume pipeline in sovereign).

## Project-specific notes

### `deep-search`
- Strength: clean multi-agent pipeline with planner/research/evaluator/composer loop and citation post-processing.
- Gap: no tests present in project tree.
- Gap: config defaults set preview models directly; no environment-driven override layer for production rollouts.

### `llm-auditor`
- Strength: has both unit-style async test and eval harness.
- Gap: tests depend on live model/search behavior and can be flaky without deterministic stubs.

### `parallel_task_decomposition_execution`
- Strength: clear orchestrated flow (enhance -> parallel broadcast -> summary).
- Gap: tools are intentionally mocked; production connectors, retries, idempotency, and auth rotation are missing.

### `sovereign-job-hunter`
- Strength: strong typed contracts in `shared/schemas.py`, explicit quality gate before submission, durable ledger append.
- Gap: no tests, no packaging manifest, and high coupling across modules through path-based loading.

## Suggested productionization sequence
1. Add packaging + reproducible dependency strategy for `sovereign-job-hunter`.
2. Add baseline CI for all four projects: lint, type-check, unit tests, security scan.
3. Introduce typed settings (single source of truth) and secret-provider integration.
4. Replace mock integrations in `parallel_task_decomposition_execution` with real adapters behind interfaces.
5. Add integration tests for end-to-end critical paths (especially sovereign runner and deep-search loop).
6. Add structured logging, trace IDs, and PII redaction middleware/callbacks.

---

## Core Python file explanations

### `hi/deep-search/app/config.py`
- Loads environment variables from `app/.env`.
- Chooses auth mode: API key (AI Studio) if `GOOGLE_API_KEY` is present, otherwise Vertex mode via ADC.
- Exposes `ResearchConfiguration` with model choices and loop iteration cap.

### `hi/deep-search/app/agent.py`
- Defines structured models (`SearchQuery`, `Feedback`) for evaluator outputs.
- Implements callbacks:
- `collect_research_sources_callback`: harvests grounding chunks/supports into citation-ready source metadata.
- `citation_replacement_callback`: replaces internal `<cite source="src-N" />` tags with markdown links.
- Implements custom `EscalationChecker` agent to stop loop when evaluator grade is `pass`.
- Builds full workflow:
- `plan_generator` -> user plan refinement.
- `section_planner` -> report structure.
- `section_researcher` -> first-pass research.
- `LoopAgent` with evaluator + enhanced search refinement.
- `report_composer` -> final cited report.
- Exposes `root_agent` and `App` instance.

### `hi/llm-auditor/llm_auditor/agent.py`
- Thin orchestration layer.
- Builds `SequentialAgent` of:
- `critic_agent` (claim extraction/verification with grounding).
- `reviser_agent` (rewrites inaccurate output).
- Exposes as `root_agent`.

### `hi/llm-auditor/llm_auditor/sub_agents/critic/agent.py`
- Uses `google_search` tool for verification.
- `after_model_callback` appends grounded references into final markdown text.
- Normalizes multi-part response into one text part.

### `hi/llm-auditor/llm_auditor/sub_agents/reviser/agent.py`
- Rewriter agent that consumes critic findings.
- Callback strips internal sentinel marker (`---END-OF-EDIT---`) and trailing content.

### `hi/parallel_task_decomposition_execution/parallel_task_decomposition_agent/config.py`
- Loads `.env` values for MCP-related credentials/tokens.
- Emits warnings when expected real-integration credentials are missing.

### `hi/parallel_task_decomposition_execution/parallel_task_decomposition_agent/tools.py`
- Defines MCP toolset examples (gmail/slack/calendar) with stdio transport.
- Current execution helpers are mocks:
- `publish_email_announcement`
- `publish_slack_message`
- `create_calendar_event`
- These return success-shaped responses without hitting real providers.

### `hi/parallel_task_decomposition_execution/parallel_task_decomposition_agent/agent.py`
- Defines sub-flows for email, slack, and calendar creation.
- Runs channels in parallel using `ParallelAgent` (`broadcast_agent`).
- Wraps with `main_flow_agent` that first enriches message via web search.
- `root_agent` is the user-facing coordinator.

### `hi/sovereign-job-hunter/shared/schemas.py`
- Central Pydantic contracts for entire sovereign workflow.
- Covers candidate profile, job manifest, evidence snippets, claims, verified patches, application packet, and ledger entry.
- Provides strong boundary typing between agents.

### `hi/sovereign-job-hunter/shared/gemini_client.py`
- Typed Gemini client wrapper for:
- model availability healthcheck,
- text generation,
- JSON generation with retry + parsing cleanup,
- embeddings.
- Enforces explicit runtime config (no hidden defaults).

### `hi/sovereign-job-hunter/shared/qdrant_store.py`
- Wraps local Qdrant for claim vector storage/search.
- Ensures collection exists.
- Supports claim upsert and top-k claim-id retrieval by query vector.

### `hi/sovereign-job-hunter/scout-agent/agent.py`
- Converts raw job text into `JobManifest`.
- Uses regex extraction for company/title/location/compensation.
- Infers required/preferred skills from lexicon + linguistic cues.
- Generates deterministic `job_id` hash.

### `hi/sovereign-job-hunter/vault-agent/agent.py`
- Ingests resume + cover letter PDFs.
- Extracts candidate profile and claim registry from local docs.
- Ranks and optionally reranks claims (Qdrant embeddings).
- Uses Gemini prompts to tailor claims, generate resume sections, and draft cover letter.
- Enforces quality constraints (word limits, evidence constraints, minimum bullets).
- Builds ATS-formatted resume text used downstream.

### `hi/sovereign-job-hunter/verifier-agent/agent.py`
- Verifies tailored claims against attached evidence.
- First pass uses lexical overlap heuristics.
- Optional second pass uses Gemini JSON assessments for stricter labeling.
- Produces `VerifiedResumePatch` with overall status + warnings.

### `hi/sovereign-job-hunter/execution-agent/agent.py`
- Gated submission handler with durable JSONL ledger.
- Blocks when approval missing or verification not approved.
- Supports dry-run and queued-live modes across provider list.
- Emits machine-readable submission outcomes.

### `hi/sovereign-job-hunter/execution-agent/render_pdfs.py`
- Reads `ApplicationPacket` JSON and renders resume + cover letter PDFs via ReportLab.
- Contains section parsing + formatting logic and reasonable fallback text when cover letter is absent.

### `hi/sovereign-job-hunter/run_sjh.py`
- End-to-end CLI orchestrator for scout -> vault -> verifier -> PDF render -> execution.
- Handles env loading, arg parsing, config checks, model healthcheck, output artifact writes.
- Applies final quality gate before submission path is allowed.
