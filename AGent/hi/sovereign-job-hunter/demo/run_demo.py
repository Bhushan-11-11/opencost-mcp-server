from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.schemas import ApplicationPacket
from shared.gemini_client import GeminiClient, GeminiConfig


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        msg = f"Cannot load module from {file_path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


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
    parser = argparse.ArgumentParser(description="Sovereign Job Hunter end-to-end local demo.")
    parser.add_argument(
        "--resume",
        default=None,
        help="Absolute path to resume PDF.",
    )
    parser.add_argument(
        "--cover-letter",
        default=None,
        help="Absolute path to cover letter PDF.",
    )
    parser.add_argument(
        "--job-file",
        default=None,
        help="Path to raw job description text file.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for generated JSON artifacts.",
    )
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="Disable Gemini for debug runs only.",
    )
    parser.add_argument(
        "--gemini-model",
        default=None,
        help="Gemini model name.",
    )
    parser.add_argument(
        "--gemini-api-key",
        default=None,
        help="Gemini API key.",
    )
    parser.add_argument(
        "--gemini-timeout-seconds",
        type=int,
        default=None,
        help="Timeout for Gemini requests.",
    )
    parser.add_argument(
        "--gemini-temperature",
        type=float,
        default=None,
        help="Sampling temperature for Gemini requests.",
    )
    parser.add_argument(
        "--use-qdrant",
        action="store_true",
        help="Enable local Qdrant retrieval reranking.",
    )
    parser.add_argument(
        "--qdrant-storage-path",
        default=None,
        help="Path for embedded/local Qdrant storage.",
    )
    parser.add_argument(
        "--qdrant-collection-name",
        default=None,
        help="Qdrant collection name for claim vectors.",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Embedding model used for vector indexing/search.",
    )
    return parser.parse_args()


def main() -> None:
    _load_dotenv(ROOT / ".env")
    args = _parse_args()
    args.resume = args.resume or _env("SJH_RESUME_PATH")
    args.cover_letter = args.cover_letter or _env("SJH_COVER_LETTER_PATH")
    args.job_file = args.job_file or _env("SJH_JOB_FILE")
    args.out_dir = args.out_dir or _env("SJH_OUTPUT_DIR")
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

    if not args.resume:
        raise RuntimeError("Missing resume path. Set SJH_RESUME_PATH or pass --resume.")
    if not args.cover_letter:
        raise RuntimeError("Missing cover letter path. Set SJH_COVER_LETTER_PATH or pass --cover-letter.")
    if not args.job_file:
        raise RuntimeError("Missing JD file. Set SJH_JOB_FILE or pass --job-file.")
    if not args.out_dir:
        raise RuntimeError("Missing output directory. Set SJH_OUTPUT_DIR or pass --out-dir.")

    scout_module = _load_module("scout_agent_module", ROOT / "scout-agent" / "agent.py")
    vault_module = _load_module("vault_agent_module", ROOT / "vault-agent" / "agent.py")
    verifier_module = _load_module("verifier_agent_module", ROOT / "verifier-agent" / "agent.py")

    ScoutAgent = scout_module.ScoutAgent
    VaultAgent = vault_module.VaultAgent
    VerifierAgent = verifier_module.VerifierAgent

    job_text = Path(args.job_file).read_text(encoding="utf-8")

    scout = ScoutAgent()
    job_manifest = scout.create_job_manifest(
        job_description_text=job_text,
        source="local-demo",
        url=None,
    )

    use_gemini = not args.no_gemini
    if not use_gemini:
        raise RuntimeError(
            "This pipeline is configured for strict Gemini-only generation. "
            "Deterministic fallback mode is disabled."
        )
    if use_gemini:
        missing = []
        if not args.gemini_model:
            missing.append("SJH_GEMINI_MODEL/--gemini-model")
        if not args.gemini_api_key:
            missing.append("SJH_GEMINI_API_KEY/--gemini-api-key")
        if args.gemini_timeout_seconds is None or args.gemini_timeout_seconds <= 0:
            missing.append("SJH_GEMINI_TIMEOUT_SECONDS/--gemini-timeout-seconds")
        if args.gemini_temperature is None:
            missing.append("SJH_GEMINI_TEMPERATURE/--gemini-temperature")
        if missing:
            raise RuntimeError("Missing Gemini config: " + ", ".join(missing))
        health_client = GeminiClient(
            GeminiConfig(
                api_key=args.gemini_api_key,
                model=args.gemini_model,
                timeout_seconds=max(10, args.gemini_timeout_seconds),
                temperature=args.gemini_temperature,
            )
        )
        if not health_client.healthcheck():
            raise RuntimeError(
                "Gemini healthcheck failed. "
                f"Model: {args.gemini_model}"
            )
    if args.use_qdrant:
        missing_qdrant = []
        if not args.qdrant_storage_path:
            missing_qdrant.append("SJH_QDRANT_STORAGE_PATH/--qdrant-storage-path")
        if not args.qdrant_collection_name:
            missing_qdrant.append("SJH_QDRANT_COLLECTION_NAME/--qdrant-collection-name")
        if not args.embedding_model:
            missing_qdrant.append("SJH_EMBEDDING_MODEL/--embedding-model")
        if missing_qdrant:
            raise RuntimeError("Missing Qdrant config: " + ", ".join(missing_qdrant))
    vault = VaultAgent(
        args.resume,
        args.cover_letter,
        use_gemini=use_gemini,
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
    rewrite_request = vault.create_rewrite_request(profile.candidate_id, job_manifest, max_bullets=8)
    tailored_claims = vault.draft_tailored_claims(job_manifest, rewrite_request)

    verifier = VerifierAgent(
        use_gemini=use_gemini,
        gemini_model=args.gemini_model,
        gemini_api_key=args.gemini_api_key,
        gemini_timeout_seconds=args.gemini_timeout_seconds,
        gemini_temperature=args.gemini_temperature,
    )
    verified_patch = verifier.verify_tailored_claims(
        candidate_id=profile.candidate_id,
        job_id=job_manifest.job_id,
        tailored_claims=tailored_claims,
    )
    headline_patch, summary_patch = vault.generate_resume_patches(
        job_manifest=job_manifest,
        tailored_claims=verified_patch.rewritten_claims,
    )
    verified_patch.headline_patch = headline_patch
    verified_patch.summary_patch = summary_patch
    cover_letter_text = vault.draft_cover_letter(
        job_manifest=job_manifest,
        tailored_claims=verified_patch.rewritten_claims,
    )

    packet = ApplicationPacket(
        candidate_id=profile.candidate_id,
        job_id=job_manifest.job_id,
        sanitized_resume_text=vault.build_ats_resume_text(verified_patch.rewritten_claims),
        sanitized_cover_letter_text=cover_letter_text,
        verified_patch=verified_patch,
        outbound_fields={
            "candidate_name": profile.full_name,
            "candidate_email": profile.email,
            "job_title": job_manifest.title,
            "company": job_manifest.company,
        },
    )
    _quality_gate(packet)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidate_profile.json").write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "job_manifest.json").write_text(job_manifest.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "rewrite_request.json").write_text(rewrite_request.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "verified_resume_patch.json").write_text(
        verified_patch.model_dump_json(indent=2), encoding="utf-8"
    )
    (out_dir / "application_packet.json").write_text(packet.model_dump_json(indent=2), encoding="utf-8")

    print("Demo completed successfully.")
    print(f"Output directory: {out_dir}")
    print(f"Job ID: {job_manifest.job_id}")
    print(f"Verification status: {verified_patch.overall_status}")
    print(f"Claims produced: {len(verified_patch.rewritten_claims)}")
    print(f"Gemini enabled: {use_gemini}")
    if use_gemini:
        print(f"Gemini model: {args.gemini_model}")
        print(f"Gemini timeout seconds: {args.gemini_timeout_seconds}")
        print(f"Gemini temperature: {args.gemini_temperature}")
    print(f"Qdrant enabled: {args.use_qdrant}")
    if args.use_qdrant:
        print(f"Qdrant storage: {args.qdrant_storage_path}")
        print(f"Qdrant collection: {args.qdrant_collection_name}")
        print(f"Embedding model: {args.embedding_model}")


if __name__ == "__main__":
    main()
