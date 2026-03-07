from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.gemini_client import GeminiClient, GeminiConfig
from shared.observability import (
    configure_json_logging,
    emit_metric,
    redact_secrets,
    set_correlation_id,
    time_block,
)
from shared.schemas import ApplicationPacket


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _set_env_key(key: str, value: str) -> None:
    current = os.getenv(key)
    if current is None or not current.strip():
        os.environ[key] = value


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        _set_env_key(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _to_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _quality_gate(packet: ApplicationPacket) -> None:
    errors: list[str] = []
    resume_text = packet.sanitized_resume_text or ""
    cover_text = packet.sanitized_cover_letter_text or ""
    bullets = [c.text.strip() for c in packet.verified_patch.rewritten_claims if c.text.strip()]

    for section in ["Professional Summary", "Technical Skills", "Professional Experience"]:
        if section.lower() not in resume_text.lower():
            errors.append(f"Missing resume section: {section}")

    if len(bullets) < 6:
        errors.append(f"Insufficient verified bullets: {len(bullets)} (min 6).")
    metric_hits = sum(1 for b in bullets if any(ch.isdigit() for ch in b))
    if metric_hits < 2:
        errors.append("Too few quantified bullets (need at least 2 with numbers).")

    cover_words = [w for w in cover_text.replace("\n", " ").split(" ") if w.strip()]
    if len(cover_words) < 160 or len(cover_words) > 320:
        errors.append(f"Cover letter length out of range: {len(cover_words)} words (target 160-320).")
    if "dear " not in cover_text.lower():
        errors.append("Cover letter missing salutation.")
    if "sincerely" not in cover_text.lower():
        errors.append("Cover letter missing sign-off.")

    if errors:
        raise RuntimeError("Quality gate failed: " + " | ".join(errors))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sovereign Job Hunter unified runner.")
    parser.add_argument("--job-file", default=None, help="Path to job description text file.")
    parser.add_argument("--resume", default=None, help="Absolute path to resume PDF.")
    parser.add_argument("--cover-letter", default=None, help="Absolute path to cover letter PDF.")
    parser.add_argument("--out-dir", default=None, help="Output directory.")
    parser.add_argument("--pdf-out-dir", default=None, help="PDF output directory.")
    parser.add_argument("--ledger-path", default=None, help="Ledger jsonl path.")
    parser.add_argument("--gemini-model", default=None, help="Gemini model name.")
    parser.add_argument("--gemini-api-key", default=None, help="Gemini API key.")
    parser.add_argument("--gemini-timeout-seconds", type=int, default=None, help="Gemini timeout.")
    parser.add_argument("--gemini-temperature", type=float, default=None, help="Gemini temperature.")
    parser.add_argument("--embedding-model", default=None, help="Gemini embedding model.")
    parser.add_argument("--use-qdrant", action="store_true", help="Enable Qdrant reranking.")
    parser.add_argument("--qdrant-storage-path", default=None, help="Qdrant local path.")
    parser.add_argument("--qdrant-collection-name", default=None, help="Qdrant collection name.")
    parser.add_argument("--approve-submit", action="store_true", help="Enable approval gate pass.")
    parser.add_argument("--live-submit", action="store_true", help="Run non-dry-run submission mode.")
    parser.add_argument(
        "--providers",
        nargs="+",
        default=None,
        help="Submission providers list. Example: stackone greenhouse workday",
    )
    return parser.parse_args()


def main() -> None:
    configure_json_logging(level=os.getenv("SJH_LOG_LEVEL", "INFO"))
    correlation_id = set_correlation_id(os.getenv("SJH_CORRELATION_ID"))
    logger = logging.getLogger("sjh.runner")
    logger.info("Starting Sovereign Job Hunter run.")
    _load_dotenv(ROOT / ".env")
    args = _parse_args()

    args.resume = args.resume or _env("SJH_RESUME_PATH")
    args.cover_letter = args.cover_letter or _env("SJH_COVER_LETTER_PATH")
    args.job_file = args.job_file or _env("SJH_JOB_FILE")
    args.out_dir = args.out_dir or _env("SJH_OUTPUT_DIR", str(ROOT / "outputs"))
    args.pdf_out_dir = args.pdf_out_dir or _env("SJH_PDF_OUTPUT_DIR", str(ROOT / "outputs" / "pdf"))
    args.ledger_path = args.ledger_path or _env("SJH_LEDGER_PATH", str(ROOT / "outputs" / "submission_ledger.jsonl"))
    args.gemini_model = args.gemini_model or _env("SJH_GEMINI_MODEL")
    args.gemini_api_key = args.gemini_api_key or _env("SJH_GEMINI_API_KEY")
    if args.gemini_timeout_seconds is None:
        args.gemini_timeout_seconds = _to_int(_env("SJH_GEMINI_TIMEOUT_SECONDS"), -1)
    if args.gemini_temperature is None:
        raw_temp = _env("SJH_GEMINI_TEMPERATURE")
        args.gemini_temperature = float(raw_temp) if raw_temp is not None else None
    if not args.use_qdrant:
        env_use_qdrant = _env("SJH_USE_QDRANT")
        args.use_qdrant = str(env_use_qdrant).lower() in {"1", "true", "yes", "on"} if env_use_qdrant else False
    args.qdrant_storage_path = args.qdrant_storage_path or _env("SJH_QDRANT_STORAGE_PATH")
    args.qdrant_collection_name = args.qdrant_collection_name or _env("SJH_QDRANT_COLLECTION_NAME")
    args.embedding_model = args.embedding_model or _env("SJH_EMBEDDING_MODEL")
    if args.providers is None:
        providers_raw = _env("SJH_SUBMISSION_PROVIDERS", "stackone greenhouse workday")
        args.providers = [p.strip() for p in providers_raw.split() if p.strip()]

    required = {
        "SJH_RESUME_PATH/--resume": args.resume,
        "SJH_COVER_LETTER_PATH/--cover-letter": args.cover_letter,
        "SJH_JOB_FILE/--job-file": args.job_file,
        "SJH_GEMINI_MODEL/--gemini-model": args.gemini_model,
        "SJH_GEMINI_API_KEY/--gemini-api-key": args.gemini_api_key,
    }
    missing = [k for k, v in required.items() if not v]
    if args.gemini_timeout_seconds is None or args.gemini_timeout_seconds <= 0:
        missing.append("SJH_GEMINI_TIMEOUT_SECONDS/--gemini-timeout-seconds")
    if args.gemini_temperature is None:
        missing.append("SJH_GEMINI_TEMPERATURE/--gemini-temperature")
    if missing:
        raise RuntimeError("Missing required configuration: " + ", ".join(missing))
    out_dir = Path(args.out_dir)
    emit_metric(out_dir, "config_validated", {"correlation_id": correlation_id})

    with time_block(out_dir, "gemini_healthcheck"):
        health_client = GeminiClient(
            GeminiConfig(
                api_key=args.gemini_api_key,
                model=args.gemini_model,
                timeout_seconds=max(10, args.gemini_timeout_seconds),
                temperature=args.gemini_temperature,
            )
        )
        if not health_client.healthcheck():
            raise RuntimeError(f"Gemini model unavailable for this key: {args.gemini_model}")

    if args.use_qdrant:
        qdrant_missing: list[str] = []
        if not args.qdrant_storage_path:
            qdrant_missing.append("SJH_QDRANT_STORAGE_PATH/--qdrant-storage-path")
        if not args.qdrant_collection_name:
            qdrant_missing.append("SJH_QDRANT_COLLECTION_NAME/--qdrant-collection-name")
        if not args.embedding_model:
            qdrant_missing.append("SJH_EMBEDDING_MODEL/--embedding-model")
        if qdrant_missing:
            raise RuntimeError("Missing Qdrant configuration: " + ", ".join(qdrant_missing))

    scout_module = _load_module("scout_agent_module", ROOT / "scout-agent" / "agent.py")
    vault_module = _load_module("vault_agent_module", ROOT / "vault-agent" / "agent.py")
    verifier_module = _load_module("verifier_agent_module", ROOT / "verifier-agent" / "agent.py")
    execution_module = _load_module("execution_agent_module", ROOT / "execution-agent" / "agent.py")

    ScoutAgent = scout_module.ScoutAgent
    VaultAgent = vault_module.VaultAgent
    VerifierAgent = verifier_module.VerifierAgent
    ExecutionAgent = execution_module.ExecutionAgent

    with time_block(out_dir, "scout_stage"):
        job_text = Path(args.job_file).read_text(encoding="utf-8")
        scout = ScoutAgent()
        manifest = scout.create_job_manifest(job_text, source="local-demo", url=None)

    with time_block(out_dir, "vault_stage"):
        vault = VaultAgent(
            args.resume,
            args.cover_letter,
            use_gemini=True,
            gemini_model=args.gemini_model,
            gemini_api_key=args.gemini_api_key,
            gemini_timeout_seconds=args.gemini_timeout_seconds,
            gemini_temperature=args.gemini_temperature,
            use_qdrant=args.use_qdrant,
            qdrant_storage_path=args.qdrant_storage_path,
            qdrant_collection_name=args.qdrant_collection_name,
            embedding_model=args.embedding_model,
        )
        profile = vault.extract_candidate_profile(candidate_id="naga-addala")
        vault.build_claim_registry()
        rewrite_request = vault.create_rewrite_request(profile.candidate_id, manifest, max_bullets=8)
        tailored_claims = vault.draft_tailored_claims(manifest, rewrite_request)

    with time_block(out_dir, "verification_stage"):
        verifier = VerifierAgent(
            use_gemini=True,
            gemini_model=args.gemini_model,
            gemini_api_key=args.gemini_api_key,
            gemini_timeout_seconds=args.gemini_timeout_seconds,
            gemini_temperature=args.gemini_temperature,
        )
        verified_patch = verifier.verify_tailored_claims(
            candidate_id=profile.candidate_id,
            job_id=manifest.job_id,
            tailored_claims=tailored_claims,
        )
        headline_patch, summary_patch = vault.generate_resume_patches(
            job_manifest=manifest,
            tailored_claims=verified_patch.rewritten_claims,
        )
        verified_patch.headline_patch = headline_patch
        verified_patch.summary_patch = summary_patch
        cover_letter_text = vault.draft_cover_letter(
            job_manifest=manifest,
            tailored_claims=verified_patch.rewritten_claims,
        )

    packet = ApplicationPacket(
        candidate_id=profile.candidate_id,
        job_id=manifest.job_id,
        sanitized_resume_text=vault.build_ats_resume_text(verified_patch.rewritten_claims),
        sanitized_cover_letter_text=cover_letter_text,
        verified_patch=verified_patch,
        outbound_fields={
            "candidate_name": profile.full_name,
            "candidate_email": profile.email,
            "job_title": manifest.title,
            "company": manifest.company,
        },
    )
    _quality_gate(packet)

    out_dir.mkdir(parents=True, exist_ok=True)
    packet_path = out_dir / "application_packet.json"
    (out_dir / "candidate_profile.json").write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "job_manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "rewrite_request.json").write_text(rewrite_request.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "verified_resume_patch.json").write_text(verified_patch.model_dump_json(indent=2), encoding="utf-8")
    packet_path.write_text(packet.model_dump_json(indent=2), encoding="utf-8")

    with time_block(out_dir, "render_pdfs_stage"):
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "execution-agent" / "render_pdfs.py"),
                "--application-packet",
                str(packet_path),
                "--out-dir",
                str(args.pdf_out_dir),
            ],
            cwd=str(ROOT),
            check=True,
        )

    with time_block(out_dir, "execution_stage"):
        executor = ExecutionAgent(ledger_path=str(args.ledger_path))
        ledger_entry, results = executor.submit(
            packet=packet,
            manifest=manifest,
            approved=args.approve_submit,
            dry_run=not args.live_submit,
            providers=args.providers,
        )
    submission_results = [
        {"provider": row.provider, "status": row.status, "detail": row.detail}
        for row in results
    ]
    (out_dir / "submission_results.json").write_text(
        json.dumps(submission_results, indent=2),
        encoding="utf-8",
    )
    (out_dir / "ledger_entry.json").write_text(ledger_entry.model_dump_json(indent=2), encoding="utf-8")

    print("Sovereign Job Hunter run completed.")
    print(f"Job ID: {manifest.job_id}")
    print(f"Verification: {verified_patch.overall_status}")
    print(f"Application packet: {packet_path}")
    print(f"PDF output: {args.pdf_out_dir}")
    print(f"Ledger path: {args.ledger_path}")
    print(f"Submission status: {ledger_entry.status}")
    logger.info(
        redact_secrets(
            f"Run completed. job_id={manifest.job_id} verification={verified_patch.overall_status} status={ledger_entry.status}"
        )
    )


if __name__ == "__main__":
    main()
