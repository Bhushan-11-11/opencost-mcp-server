from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.schemas import JobManifest


SKILL_LEXICON = [
    "python",
    "fastapi",
    "langchain",
    "rag",
    "llm",
    "machine learning",
    "deep learning",
    "pytorch",
    "tensorflow",
    "scikit-learn",
    "xgboost",
    "prophet",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "github actions",
    "mlops",
    "sql",
]

CULTURE_SIGNAL_TERMS = [
    "ownership",
    "autonomous",
    "collaborative",
    "cross-functional",
    "fast-paced",
    "innovation",
    "customer-first",
    "mentorship",
]


class ScoutAgent:
    """Transforms raw job text into a structured JobManifest."""

    @staticmethod
    def _extract_value(patterns: Iterable[str], text: str) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = value.splitlines()[0].strip()
                value = re.sub(r"\s{2,}", " ", value)
                return value.strip(" -|:")
        return None

    @staticmethod
    def _extract_skills(text: str) -> tuple[list[str], list[str]]:
        lower = text.lower()
        required: list[str] = []
        preferred: list[str] = []
        for skill in SKILL_LEXICON:
            if skill in lower:
                if re.search(rf"(required|must have|minimum).*{re.escape(skill)}", lower):
                    required.append(skill)
                elif re.search(rf"(preferred|nice to have|plus).*{re.escape(skill)}", lower):
                    preferred.append(skill)
                else:
                    required.append(skill)
        return sorted(set(required)), sorted(set(preferred))

    @staticmethod
    def _extract_company_signals(text: str) -> list[str]:
        lower = text.lower()
        signals = [term for term in CULTURE_SIGNAL_TERMS if term in lower]
        return sorted(set(signals))

    def create_job_manifest(
        self,
        job_description_text: str,
        source: str = "manual",
        url: str | None = None,
    ) -> JobManifest:
        company = self._extract_value(
            [
                r"company\s*:\s*(.+)",
                r"about\s+company\s*:\s*(.+)",
            ],
            job_description_text,
        ) or "Unknown Company"
        if company.lower() in {"the role", "role", "this role"}:
            company = "Unknown Company"
        title = self._extract_value(
            [
                r"job\s+description\s*:\s*(.+)",
                r"title\s*:\s*(.+)",
                r"role\s*:\s*(.+)",
                r"position\s*:\s*(.+)",
            ],
            job_description_text,
        ) or "AI/ML Engineer"
        location = self._extract_value([r"location\s*:\s*(.+)"], job_description_text)
        work_mode = self._extract_value(
            [r"(remote|hybrid|onsite|on-site)"], job_description_text
        )
        compensation = self._extract_value(
            [
                r"salary\s*:\s*(.+)",
                r"compensation\s*:\s*(.+)",
                r"\$[\d,]+\s*-\s*\$[\d,]+",
            ],
            job_description_text,
        )
        required_skills, preferred_skills = self._extract_skills(job_description_text)
        company_signals = self._extract_company_signals(job_description_text)
        tech_stack_signals = sorted(set(required_skills + preferred_skills))

        key = f"{company}|{title}|{source}|{url or ''}|{job_description_text[:140]}"
        job_id = "job-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

        summary = (
            f"{title} at {company}. Required skills: "
            f"{', '.join(required_skills[:8]) if required_skills else 'not clearly listed'}."
        )

        return JobManifest(
            job_id=job_id,
            source=source,
            url=url,
            company=company,
            title=title,
            location=location,
            work_mode=work_mode,
            compensation_text=compensation,
            description_text=job_description_text.strip(),
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            company_signals=company_signals,
            tech_stack_signals=tech_stack_signals,
            scout_summary=summary,
        )
