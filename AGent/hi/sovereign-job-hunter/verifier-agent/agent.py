from __future__ import annotations

import datetime as dt
import re
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.gemini_client import GeminiClient, GeminiConfig
from shared.schemas import (
    ResumeClaim,
    VerificationStatus,
    VerifiedResumePatch,
)


class VerifierAgent:
    """Verifies tailored claims against local evidence excerpts."""

    def __init__(
        self,
        use_gemini: bool,
        gemini_model: str | None,
        gemini_api_key: str | None,
        gemini_timeout_seconds: int | None,
        gemini_temperature: float | None,
    ) -> None:
        self.use_gemini = use_gemini
        if self.use_gemini:
            missing = [
                name
                for name, value in [
                    ("gemini_model", gemini_model),
                    ("gemini_api_key", gemini_api_key),
                    ("gemini_timeout_seconds", gemini_timeout_seconds),
                    ("gemini_temperature", gemini_temperature),
                ]
                if value is None
            ]
            if missing:
                raise RuntimeError(
                    "Missing Gemini configuration for verifier-agent: " + ", ".join(missing)
                )
            self.gemini_client = GeminiClient(
                GeminiConfig(
                    api_key=str(gemini_api_key),
                    model=str(gemini_model),
                    timeout_seconds=int(gemini_timeout_seconds),
                    temperature=float(gemini_temperature),
                )
            )
        else:
            self.gemini_client = None

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {tok for tok in re.findall(r"[a-z0-9+.-]+", text.lower()) if len(tok) > 2}

    def _assess_claim(self, claim: ResumeClaim) -> ResumeClaim:
        if not claim.evidence:
            claim.verification_status = VerificationStatus.UNSUPPORTED
            claim.reviewer_notes = "No local evidence attached to this claim."
            return claim

        claim_tokens = self._tokenize(claim.text)
        best_overlap = 0.0
        for evidence in claim.evidence:
            ev_tokens = self._tokenize(evidence.excerpt)
            if not claim_tokens or not ev_tokens:
                continue
            overlap = len(claim_tokens.intersection(ev_tokens)) / max(len(claim_tokens), 1)
            best_overlap = max(best_overlap, overlap)

        if best_overlap >= 0.8:
            claim.verification_status = VerificationStatus.VERIFIED
            claim.reviewer_notes = "Claim strongly matches local evidence."
        elif best_overlap >= 0.45:
            claim.verification_status = VerificationStatus.PARTIAL
            claim.reviewer_notes = "Claim partially supported; wording should stay conservative."
        else:
            claim.verification_status = VerificationStatus.UNSUPPORTED
            claim.reviewer_notes = "Claim has weak lexical overlap with attached evidence."
        return claim

    @staticmethod
    def _check_duration_consistency(claims: Iterable[ResumeClaim]) -> list[str]:
        """Adds a lightweight time-sanity warning for known resume phrasing."""
        warnings: list[str] = []
        now = dt.date.today()
        text_blob = " ".join(claim.text.lower() for claim in claims)
        if "april 2025" in text_blob and "1 year" in text_blob and now < dt.date(2026, 4, 1):
            warnings.append(
                f"Potential duration inflation: April 2025 to {now.isoformat()} is under 1 full year."
            )
        return warnings

    def verify_tailored_claims(
        self,
        candidate_id: str,
        job_id: str,
        tailored_claims: list[ResumeClaim],
    ) -> VerifiedResumePatch:
        reviewed = [self._assess_claim(claim) for claim in tailored_claims]
        if self.use_gemini and reviewed:
            if self.gemini_client is None:
                raise RuntimeError("Gemini client is not configured.")
            reviewed = self._llm_verify(reviewed)
        warnings = self._check_duration_consistency(reviewed)

        unsupported_count = sum(
            1 for claim in reviewed if claim.verification_status == VerificationStatus.UNSUPPORTED
        )
        rejected_count = sum(
            1 for claim in reviewed if claim.verification_status == VerificationStatus.REJECTED
        )
        if rejected_count > 0:
            overall_status = "rejected"
        elif unsupported_count > 0:
            overall_status = "needs_review"
        else:
            overall_status = "approved"

        return VerifiedResumePatch(
            candidate_id=candidate_id,
            job_id=job_id,
            rewritten_claims=reviewed,
            overall_status=overall_status,
            verification_notes=warnings,
        )

    def _llm_verify(self, claims: list[ResumeClaim]) -> list[ResumeClaim]:
        claim_lines = []
        for claim in claims:
            evidence_lines = [ev.excerpt[:220] for ev in claim.evidence[:2]]
            claim_text = claim.text[:260]
            claim_lines.append(
                "{"
                f'"claim_id":"{claim.claim_id}",'
                f'"claim":"{claim_text}",'
                f'"evidence":{evidence_lines}'
                "}"
            )
        prompt = (
            "You are a strict factual verifier for resume claims.\n"
            "For each claim, compare it against provided local evidence.\n"
            "Status rules:\n"
            "- verified: strongly supported\n"
            "- partial: partly supported but should be conservative\n"
            "- unsupported: weakly or not supported\n"
            "- rejected: fabricated or contradictory\n"
            "Keep note under 90 characters.\n"
            "Return JSON only with schema:\n"
            "{\n"
            '  "assessments": [\n'
            '    {"claim_id":"string","status":"verified|partial|unsupported|rejected","note":"string"}\n'
            "  ]\n"
            "}\n"
            "Claims:\n"
            + "\n".join(claim_lines)
        )
        result = self.gemini_client.generate_json(prompt)
        assessments = result.get("assessments", [])
        if not isinstance(assessments, list):
            return claims

        valid_map = {
            "verified": VerificationStatus.VERIFIED,
            "partial": VerificationStatus.PARTIAL,
            "unsupported": VerificationStatus.UNSUPPORTED,
            "rejected": VerificationStatus.REJECTED,
        }
        by_id = {claim.claim_id: claim for claim in claims}
        for row in assessments:
            if not isinstance(row, dict):
                continue
            claim_id = str(row.get("claim_id", "")).strip()
            status_raw = str(row.get("status", "")).strip().lower()
            note = str(row.get("note", "")).strip()
            claim = by_id.get(claim_id)
            if not claim or status_raw not in valid_map:
                continue
            claim.verification_status = valid_map[status_raw]
            if note:
                claim.reviewer_notes = note
        return list(by_id.values())
