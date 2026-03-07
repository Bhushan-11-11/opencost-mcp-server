from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.gemini_client import GeminiClient, GeminiConfig
from shared.prompts import (
    ATS_RESUME_TASK_PROMPT,
    COVER_LETTER_TASK_PROMPT,
    REWRITE_TASK_PROMPT,
    SYSTEM_ROLE_PROMPT,
)
from shared.qdrant_store import QdrantClaimStore, QdrantConfig
from shared.schemas import (
    CandidateProfile,
    DocumentRef,
    EvidenceSnippet,
    JobManifest,
    ResumeClaim,
    ResumeRewriteRequest,
    VerificationStatus,
    WorkPreference,
)


SKILL_KEYWORDS = [
    "python",
    "fastapi",
    "langchain",
    "rag",
    "pytorch",
    "tensorflow",
    "scikit-learn",
    "xgboost",
    "prophet",
    "openai",
    "anthropic",
    "azure",
    "aws",
    "docker",
    "kubernetes",
    "github actions",
    "llm",
    "mlops",
]


@dataclass
class VaultArtifacts:
    candidate_profile: CandidateProfile
    resume_text: str
    cover_letter_text: str
    claim_registry: list[ResumeClaim]


class VaultAgent:
    """Local authority for candidate data, evidence, and tailored claim drafting."""

    def __init__(
        self,
        resume_path: str,
        cover_letter_path: str,
        use_gemini: bool,
        gemini_model: str | None,
        gemini_api_key: str | None,
        gemini_timeout_seconds: int | None,
        gemini_temperature: float | None,
        use_qdrant: bool,
        qdrant_storage_path: str | None,
        qdrant_collection_name: str | None,
        embedding_model: str | None,
    ) -> None:
        self.resume_path = Path(resume_path)
        self.cover_letter_path = Path(cover_letter_path)
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
                    "Missing Gemini configuration for vault-agent: " + ", ".join(missing)
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
        self.use_qdrant = use_qdrant
        self.embedding_model = embedding_model
        if self.use_qdrant:
            missing = [
                name
                for name, value in [
                    ("qdrant_storage_path", qdrant_storage_path),
                    ("qdrant_collection_name", qdrant_collection_name),
                    ("embedding_model", embedding_model),
                ]
                if value is None
            ]
            if missing:
                raise RuntimeError("Missing Qdrant config for vault-agent: " + ", ".join(missing))
            vector_size = self._resolve_vector_size()
            self.qdrant_store = QdrantClaimStore(
                QdrantConfig(
                    storage_path=str(qdrant_storage_path),
                    collection_name=str(qdrant_collection_name),
                    vector_size=vector_size,
                )
            )
        else:
            self.qdrant_store = None
        self._resume_text = ""
        self._cover_letter_text = ""
        self._candidate_profile: CandidateProfile | None = None
        self._claim_registry: list[ResumeClaim] = []
        self._latest_resume_sections: dict[str, object] | None = None

    def _resolve_vector_size(self) -> int:
        if not self.gemini_client or not self.embedding_model:
            raise RuntimeError("Gemini client and embedding model are required to resolve vector size.")
        probe = self.gemini_client.embed_text("vector-size-probe", embedding_model=self.embedding_model)
        if not probe:
            raise RuntimeError("Embedding probe returned empty vector.")
        return len(probe)

    @staticmethod
    def _clean_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _is_name_candidate(line: str) -> bool:
        blocked = {
            "Top Skills",
            "Summary",
            "Experience",
            "Education",
            "Contact",
            "Certifications",
            "Publications",
        }
        if line in blocked:
            return False
        if len(line.split()) < 3 or len(line.split()) > 5:
            return False
        if any(ch.isdigit() for ch in line):
            return False
        return bool(re.fullmatch(r"[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){2,4}", line))

    def _extract_name(self) -> str:
        resume_lines = [line.strip() for line in self._resume_text.splitlines() if line.strip()]
        for idx, line in enumerate(resume_lines):
            if "AI/ML Engineer" in line and idx > 0:
                candidate = resume_lines[idx - 1]
                if self._is_name_candidate(candidate):
                    return candidate

        for line in resume_lines:
            if self._is_name_candidate(line) and "Top Skills" not in line:
                if "Neural Networks" not in line and "Keras" not in line:
                    return line

        compact_cover = self._clean_whitespace(self._cover_letter_text)
        sig_match = re.search(
            r"Sincerely,\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){2,4})",
            compact_cover,
        )
        if sig_match:
            return sig_match.group(1).strip()

        return "Unknown Candidate"

    @staticmethod
    def _is_resume_section_break(line: str) -> bool:
        if not line:
            return False
        if re.match(r"Page \d+ of \d+", line):
            return True
        if line in {
            "Experience",
            "Education",
            "Summary",
            "Contact",
            "Top Skills",
            "Certifications",
            "Publications",
        }:
            return True
        if re.fullmatch(r"[A-Z][A-Za-z0-9&.,'() /-]{2,60}", line):
            if len(line.split()) <= 6 and not line.endswith("."):
                return True
        return False

    def _extract_resume_bullets(self) -> list[str]:
        normalized = self._resume_text.replace("\uf0b7", "•")
        parts = re.split(r"\s*•\s*", normalized)
        if len(parts) <= 1:
            return []

        bullets: list[str] = []
        for chunk in parts[1:]:
            text = self._clean_whitespace(chunk)
            if not text:
                continue

            # Remove common PDF artifacts and stop at section boundaries.
            text = re.sub(r"Page \d+ of \d+", "", text)
            boundary_match = re.search(
                r"\b(Experience|Education|Contact|Top Skills|Certifications|Publications)\b",
                text,
            )
            if boundary_match and boundary_match.start() > 0:
                text = text[: boundary_match.start()].strip()

            if not text or len(text) < 24:
                continue
            bullets.append(self._clean_claim_text(text))

        deduped: list[str] = []
        seen: set[str] = set()
        for bullet in bullets:
            key = self._canonicalize_for_dedupe(bullet)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(bullet)
        return deduped

    @staticmethod
    def _clean_claim_text(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip().strip(" -")
        cleaned = cleaned.rstrip(",;")
        if cleaned and cleaned[-1] not in {".", "!", "?"}:
            cleaned += "."
        cleaned = cleaned.replace("preproces.", "preprocessing.")
        return cleaned

    @staticmethod
    def _canonicalize_for_dedupe(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _enforce_claim_quality(self, text: str) -> str:
        cleaned = self._clean_claim_text(text)
        if len(cleaned) > 220:
            first_sentence = cleaned.split(".")[0].strip()
            cleaned = self._clean_claim_text(first_sentence)
        words = cleaned.split()
        if len(words) > 25:
            cleaned = self._clean_claim_text(" ".join(words[:25]))
        return cleaned

    def _known_skill_set(self) -> set[str]:
        known: set[str] = set()
        if self._candidate_profile:
            known.update(s.lower() for s in self._candidate_profile.target_skills if s.strip())
        for claim in self._claim_registry:
            known.update(tag.lower() for tag in claim.skill_tags)
            low = claim.text.lower()
            known.update(skill for skill in SKILL_KEYWORDS if skill in low)
        return known

    def _contains_unknown_skill_terms(self, claim_text: str, known_skills: set[str]) -> bool:
        lower = claim_text.lower()
        found = {skill for skill in SKILL_KEYWORDS if skill in lower}
        return len(found - known_skills) > 0

    def _validate_tailored_claims(
        self,
        claims: list[ResumeClaim],
        min_bullets: int,
        max_words: int,
    ) -> None:
        errors: list[str] = []
        if len(claims) < min_bullets:
            errors.append(f"Only {len(claims)} bullets generated; minimum required is {min_bullets}.")
        known_skills = self._known_skill_set()
        for idx, claim in enumerate(claims, start=1):
            words = claim.text.split()
            if len(words) > max_words:
                errors.append(f"Bullet {idx} has {len(words)} words (max {max_words}).")
            if self._contains_unknown_skill_terms(claim.text, known_skills):
                errors.append(f"Bullet {idx} includes skill terms not present in resume evidence.")
        if errors:
            raise RuntimeError("Tailored claims failed constraints: " + " | ".join(errors))

    @staticmethod
    def _read_pdf(path: Path) -> str:
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        text = "\n".join(line.rstrip() for line in text.splitlines())
        return text.strip()

    def ingest_documents(self) -> tuple[str, str]:
        self._resume_text = self._read_pdf(self.resume_path)
        self._cover_letter_text = self._read_pdf(self.cover_letter_path)
        return self._resume_text, self._cover_letter_text

    def extract_candidate_profile(self, candidate_id: str = "candidate-001") -> CandidateProfile:
        if not self._resume_text:
            self.ingest_documents()

        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", self._resume_text)
        email = email_match.group(0) if email_match else ""

        name = self._extract_name()

        location = None
        location_match = re.search(r"\n([A-Za-z]+(?:\s+[A-Za-z]+)?\s+Metro)\n", self._resume_text)
        if location_match:
            location = location_match.group(1).strip()

        target_titles = []
        open_roles_match = re.search(r"open to roles in (.+?)—", self._resume_text, flags=re.IGNORECASE | re.DOTALL)
        if open_roles_match:
            raw = open_roles_match.group(1).replace("·", ",").replace("\n", " ")
            target_titles = [self._clean_whitespace(part) for part in raw.split(",") if part.strip()]

        skill_line_match = re.search(r"Core Stack:\s*(.+?)Currently open", self._resume_text, flags=re.IGNORECASE | re.DOTALL)
        target_skills: list[str] = []
        if skill_line_match:
            skill_blob = skill_line_match.group(1).replace("·", ",").replace("\n", " ")
            target_skills = [self._clean_whitespace(part) for part in skill_blob.split(",") if part.strip()]

        profile = CandidateProfile(
            candidate_id=candidate_id,
            full_name=name,
            email=email,
            location=location,
            target_titles=target_titles,
            target_skills=target_skills,
            work_preferences=[WorkPreference.FLEXIBLE],
            source_documents=[
                DocumentRef(
                    doc_id="resume",
                    path=str(self.resume_path.resolve()),
                    title=self.resume_path.name,
                ),
                DocumentRef(
                    doc_id="cover_letter",
                    path=str(self.cover_letter_path.resolve()),
                    title=self.cover_letter_path.name,
                ),
            ],
        )
        self._candidate_profile = profile
        return profile

    def build_claim_registry(self) -> list[ResumeClaim]:
        if not self._resume_text:
            self.ingest_documents()

        claims: list[ResumeClaim] = []
        bullet_lines = self._extract_resume_bullets()

        for idx, bullet in enumerate(bullet_lines, start=1):
            claim_text = self._clean_claim_text(bullet)
            lower = claim_text.lower()
            tags = [skill for skill in SKILL_KEYWORDS if skill in lower]
            evidence = EvidenceSnippet(
                evidence_id=f"ev-{idx}",
                source_doc_id="resume",
                excerpt=claim_text,
                rationale="Extracted directly from resume bullet point.",
                confidence=0.85,
                path=str(self.resume_path.resolve()),
            )
            claims.append(
                ResumeClaim(
                    claim_id=f"claim-{idx}",
                    text=claim_text,
                    skill_tags=tags,
                    evidence=[evidence],
                    verification_status=VerificationStatus.PARTIAL,
                )
            )

        self._claim_registry = claims
        if self.use_qdrant and self.gemini_client and self.qdrant_store:
            vectors = [
                self.gemini_client.embed_text(claim.text, embedding_model=self.embedding_model)
                for claim in claims
            ]
            self.qdrant_store.upsert_claims(claims, vectors)
        return claims

    def create_rewrite_request(
        self, candidate_id: str, job_manifest: JobManifest, max_bullets: int = 8
    ) -> ResumeRewriteRequest:
        return ResumeRewriteRequest(
            candidate_id=candidate_id,
            job_id=job_manifest.job_id,
            target_title=job_manifest.title,
            job_focus_areas=(job_manifest.required_skills + job_manifest.preferred_skills)[:10],
            preserve_constraints=[
                "Do not invent experience, metrics, or tools.",
                "Keep claims grounded in candidate evidence.",
            ],
            max_bullets=max_bullets,
        )

    def draft_tailored_claims(
        self, job_manifest: JobManifest, rewrite_request: ResumeRewriteRequest
    ) -> list[ResumeClaim]:
        if not self._claim_registry:
            self.build_claim_registry()

        ranked = self._rank_claims(job_manifest)
        if self.use_qdrant and self.gemini_client and self.qdrant_store:
            ranked = self._rerank_with_qdrant(job_manifest, ranked)
        if self.use_gemini:
            if self.gemini_client is None:
                raise RuntimeError("Gemini client is not configured.")
            llm_selected = self._llm_tailor_claims(
                ranked_claims=ranked,
                job_manifest=job_manifest,
                rewrite_request=rewrite_request,
            )
            if not llm_selected:
                raise RuntimeError(
                    "Gemini produced no valid tailored claims. Fallback is disabled."
                )
            return llm_selected

        selected = ranked[: rewrite_request.max_bullets]
        if not selected:
            selected = self._claim_registry[: rewrite_request.max_bullets]
        return selected

    def _rerank_with_qdrant(
        self,
        job_manifest: JobManifest,
        ranked_claims: list[ResumeClaim],
    ) -> list[ResumeClaim]:
        if not self.gemini_client or not self.qdrant_store:
            return ranked_claims
        query = (
            f"{job_manifest.title}\n"
            f"Required: {', '.join(job_manifest.required_skills)}\n"
            f"Preferred: {', '.join(job_manifest.preferred_skills)}\n"
            f"{job_manifest.description_text[:1200]}"
        )
        query_vec = self.gemini_client.embed_text(query, embedding_model=self.embedding_model)
        claim_ids = self.qdrant_store.search_claim_ids(query_vec, top_k=max(12, len(ranked_claims)))
        by_id = {claim.claim_id: claim for claim in ranked_claims}
        qdrant_ranked = [by_id[cid] for cid in claim_ids if cid in by_id]
        seen = {claim.claim_id for claim in qdrant_ranked}
        qdrant_ranked.extend([claim for claim in ranked_claims if claim.claim_id not in seen])
        return qdrant_ranked

    def _rank_claims(self, job_manifest: JobManifest) -> list[ResumeClaim]:
        required = {skill.lower() for skill in job_manifest.required_skills}
        preferred = {skill.lower() for skill in job_manifest.preferred_skills}
        target_terms = required | preferred

        def score_claim(claim: ResumeClaim) -> tuple[int, int, int, int]:
            text = claim.text.lower()
            tags = {tag.lower() for tag in claim.skill_tags}
            overlap = len(tags.intersection(target_terms))
            keyword_hits = sum(1 for term in target_terms if term in text)
            metric_bonus = 1 if re.search(r"\b\d+[%x+]?\b", text) else 0
            generic_penalty = 1 if "3+ years" in text or "master's in computer science" in text else 0
            return overlap, keyword_hits, metric_bonus, -generic_penalty

        ranked = sorted(
            self._claim_registry,
            key=lambda claim: score_claim(claim),
            reverse=True,
        )
        return ranked

    def _llm_tailor_claims(
        self,
        ranked_claims: list[ResumeClaim],
        job_manifest: JobManifest,
        rewrite_request: ResumeRewriteRequest,
    ) -> list[ResumeClaim]:
        candidate_pool = ranked_claims[: min(16, len(ranked_claims))]
        pool_lines = []
        for claim in candidate_pool:
            ev_excerpt = claim.evidence[0].excerpt[:220] if claim.evidence else ""
            claim_text = claim.text[:220]
            pool_lines.append(
                f"- {claim.claim_id} | claim: {claim_text} | evidence: {ev_excerpt}"
            )
        jd_compact = job_manifest.description_text[:1600]
        task = REWRITE_TASK_PROMPT.format(
            max_words_per_bullet=25,
            max_bullets=rewrite_request.max_bullets,
        )
        prompt = (
            f"{SYSTEM_ROLE_PROMPT}\n\n"
            f"{task}\n\n"
            "Candidate Resume Evidence Claims:\n"
            + "\n".join(pool_lines)
            + "\n\n"
            "Job Description:\n"
            f"{jd_compact}\n\n"
            f"Target title: {rewrite_request.target_title}\n"
            f"Focus skills: {', '.join(rewrite_request.job_focus_areas)}\n\n"
            f"Company: {job_manifest.company}\n\n"
            "Generate the optimized bullets now."
        )
        result = self.gemini_client.generate_json(prompt)
        selected = result.get("selected", [])
        if not isinstance(selected, list):
            return []

        source_by_id = {claim.claim_id: claim for claim in candidate_pool}
        tailored_claims: list[ResumeClaim] = []
        seen: set[str] = set()
        for row in selected:
            if not isinstance(row, dict):
                continue
            claim_id = str(row.get("claim_id", "")).strip()
            tailored_text = str(row.get("tailored_text", "")).strip()
            if not claim_id or not tailored_text:
                continue
            source = source_by_id.get(claim_id)
            if not source:
                continue

            cleaned_tailored = self._enforce_claim_quality(tailored_text)
            canonical = self._canonicalize_for_dedupe(cleaned_tailored)
            if canonical in seen or len(cleaned_tailored) < 20:
                continue
            seen.add(canonical)
            low = cleaned_tailored.lower()
            tags = sorted(set(source.skill_tags + [skill for skill in SKILL_KEYWORDS if skill in low]))
            tailored_claims.append(
                ResumeClaim(
                    claim_id=source.claim_id,
                    text=cleaned_tailored,
                    skill_tags=tags,
                    evidence=source.evidence,
                    verification_status=VerificationStatus.PARTIAL,
                )
            )
            if len(tailored_claims) >= rewrite_request.max_bullets:
                break

        minimum_target = min(6, rewrite_request.max_bullets)
        if len(tailored_claims) < minimum_target:
            top_up = self._llm_topup_claims(
                candidate_pool=candidate_pool,
                existing_claims=tailored_claims,
                target_count=minimum_target,
                job_manifest=job_manifest,
            )
            tailored_claims.extend(top_up)
        self._validate_tailored_claims(
            claims=tailored_claims,
            min_bullets=minimum_target,
            max_words=25,
        )
        return tailored_claims

    def _llm_topup_claims(
        self,
        candidate_pool: list[ResumeClaim],
        existing_claims: list[ResumeClaim],
        target_count: int,
        job_manifest: JobManifest,
    ) -> list[ResumeClaim]:
        existing_ids = {claim.claim_id for claim in existing_claims}
        remaining = [claim for claim in candidate_pool if claim.claim_id not in existing_ids]
        if not remaining:
            return []

        selected_ids = [claim.claim_id for claim in self._rank_claims(job_manifest) if claim in remaining]
        by_id = {claim.claim_id: claim for claim in remaining}
        out: list[ResumeClaim] = []
        seen = {self._canonicalize_for_dedupe(c.text) for c in existing_claims}
        for raw_id in selected_ids:
            claim_id = str(raw_id).strip()
            claim = by_id.get(claim_id)
            if not claim:
                continue
            text = self._enforce_claim_quality(claim.text)
            key = self._canonicalize_for_dedupe(text)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                ResumeClaim(
                    claim_id=claim.claim_id,
                    text=text,
                    skill_tags=claim.skill_tags,
                    evidence=claim.evidence,
                    verification_status=VerificationStatus.PARTIAL,
                )
            )
            if len(existing_claims) + len(out) >= target_count:
                break
        return out

    def generate_resume_patches(
        self,
        job_manifest: JobManifest,
        tailored_claims: list[ResumeClaim],
    ) -> tuple[str, str]:
        if not self._candidate_profile:
            raise RuntimeError("Candidate profile is required before generating patches.")
        claim_lines = "\n".join(f"- {claim.text}" for claim in tailored_claims[:8])
        resume_context = "\n".join(
            line.strip()
            for line in self._resume_text.splitlines()
            if line.strip()
        )[:2200]
        prompt = (
            f"{SYSTEM_ROLE_PROMPT}\n\n"
            f"{ATS_RESUME_TASK_PROMPT}\n\n"
            "Candidate Profile:\n"
            f"Target job title: {job_manifest.title}\n"
            f"Candidate name: {self._candidate_profile.full_name}\n"
            f"Candidate email: {self._candidate_profile.email}\n"
            f"Core skills from profile: {', '.join(self._candidate_profile.target_skills)}\n\n"
            "Base Resume Context:\n"
            f"{resume_context}\n\n"
            "Validated Experience Claims:\n"
            f"{claim_lines}\n\n"
            "Generate the optimized resume sections now."
        )
        result = self.gemini_client.generate_json(prompt)
        headline = self._clean_claim_text(str(result.get("headline", "")).strip())
        summary = self._clean_claim_text(str(result.get("professional_summary", "")).strip())
        technical_skills = result.get("technical_skills", [])
        experience_bullets = result.get("experience_bullets", [])
        projects_bullets = result.get("projects_bullets", [])
        education_block = str(result.get("education_block", "")).strip()
        if not isinstance(technical_skills, list):
            technical_skills = []
        if not isinstance(experience_bullets, list):
            experience_bullets = []
        if not isinstance(projects_bullets, list):
            projects_bullets = []

        if not headline or not summary:
            raise RuntimeError("Gemini did not produce valid headline/summary patches.")
        if len(summary.split()) > 80:
            raise RuntimeError("Summary exceeds ATS constraints (>80 words).")
        for idx, bullet in enumerate(experience_bullets, start=1):
            if len(str(bullet).split()) > 25:
                raise RuntimeError(f"Generated experience bullet {idx} exceeds 25-word limit.")

        self._latest_resume_sections = {
            "headline": headline,
            "professional_summary": summary,
            "technical_skills": [self._clean_whitespace(str(s)) for s in technical_skills if str(s).strip()],
            "experience_bullets": [self._clean_claim_text(str(b)) for b in experience_bullets if str(b).strip()],
            "projects_bullets": [self._clean_claim_text(str(b)) for b in projects_bullets if str(b).strip()],
            "education_block": self._clean_whitespace(education_block),
        }
        return headline, summary

    def draft_cover_letter(
        self,
        job_manifest: JobManifest,
        tailored_claims: list[ResumeClaim],
    ) -> str:
        if not self._candidate_profile:
            raise RuntimeError("Candidate profile is required before generating cover letter.")
        claim_lines = "\n".join(f"- {claim.text}" for claim in tailored_claims[:6])
        prompt = (
            f"{SYSTEM_ROLE_PROMPT}\n\n"
            f"{COVER_LETTER_TASK_PROMPT}\n\n"
            "Candidate Context:\n"
            f"Candidate: {self._candidate_profile.full_name}\n"
            f"Email: {self._candidate_profile.email}\n"
            f"Target job: {job_manifest.title} at {job_manifest.company}\n"
            f"Location: {job_manifest.location or 'Not specified'}\n"
            f"Claims:\n{claim_lines}\n\n"
            "Generate the tailored cover letter now."
        )
        result = self.gemini_client.generate_json(prompt)
        letter = str(result.get("cover_letter", "")).strip()
        letter = re.sub(r"\+?\d[\d\-\s()]{7,}", "", letter)
        letter = re.sub(r"https?://\S+|www\.\S+", "", letter)
        letter = self._normalize_cover_letter(letter)
        if len(letter) < 120:
            raise RuntimeError("Gemini did not produce a usable cover letter.")
        return letter

    def _normalize_cover_letter(self, text: str) -> str:
        chunks = [self._clean_whitespace(part) for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not chunks:
            return ""
        first = chunks[0]
        if not first.lower().startswith("dear "):
            chunks.insert(0, "Dear Hiring Manager,")
        if not any("sincerely" in c.lower() for c in chunks[-2:]):
            signature = self._candidate_profile.full_name if self._candidate_profile else "Candidate"
            chunks.append(f"Sincerely,\n{signature}")
        return "\n\n".join(chunks)

    def build_ats_resume_text(self, tailored_claims: list[ResumeClaim]) -> str:
        sections = self._latest_resume_sections or {}
        headline = str(sections.get("headline", "")).strip()
        summary = str(sections.get("professional_summary", "")).strip()
        technical_skills = sections.get("technical_skills", [])
        experience_bullets = sections.get("experience_bullets", [])
        projects_bullets = sections.get("projects_bullets", [])
        education_block = str(sections.get("education_block", "")).strip()

        if not isinstance(technical_skills, list):
            technical_skills = []
        if not isinstance(experience_bullets, list):
            experience_bullets = []
        if not isinstance(projects_bullets, list):
            projects_bullets = []

        if not experience_bullets:
            experience_bullets = [claim.text for claim in tailored_claims]

        lines: list[str] = []
        if self._candidate_profile:
            lines.append(self._candidate_profile.full_name)
            contact_parts = [self._candidate_profile.email]
            if self._candidate_profile.location:
                contact_parts.append(self._candidate_profile.location)
            if contact_parts:
                lines.append(" | ".join(part for part in contact_parts if part))
            lines.append("")
        lines.append("Professional Summary")
        if headline:
            lines.append(headline)
        if summary:
            lines.append(summary)
        lines.append("")
        lines.append("Technical Skills")
        lines.append(", ".join(technical_skills) if technical_skills else ", ".join(self._candidate_profile.target_skills if self._candidate_profile else []))
        lines.append("")
        lines.append("Professional Experience")
        lines.extend(f"- {bullet}" for bullet in experience_bullets)
        if projects_bullets:
            lines.append("")
            lines.append("Projects")
            lines.extend(f"- {bullet}" for bullet in projects_bullets)
        if education_block:
            lines.append("")
            lines.append("Education")
            lines.append(education_block)
        return "\n".join(line for line in lines if line is not None)

    def materialize(self) -> VaultArtifacts:
        profile = self._candidate_profile or self.extract_candidate_profile()
        claims = self._claim_registry or self.build_claim_registry()
        if not self._resume_text or not self._cover_letter_text:
            self.ingest_documents()
        return VaultArtifacts(
            candidate_profile=profile,
            resume_text=self._resume_text,
            cover_letter_text=self._cover_letter_text,
            claim_registry=claims,
        )
