from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from shared.schemas import ApplicationLedgerEntry, ApplicationPacket, JobManifest

logger = logging.getLogger("sjh.execution")


@dataclass
class SubmissionResult:
    provider: str
    status: str
    detail: str


class ExecutionAgent:
    """Gated submission workflow with durable local ledger."""

    def __init__(self, ledger_path: str) -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            self.ledger_path.write_text("", encoding="utf-8")

    @staticmethod
    def _application_id(candidate_id: str, job_id: str) -> str:
        seed = f"{candidate_id}|{job_id}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        return f"app-{digest}"

    def _append_ledger(self, entry: ApplicationLedgerEntry) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json())
            f.write("\n")
        logger.info(
            "Ledger append status=%s job_id=%s application_id=%s",
            entry.status,
            entry.job_id,
            entry.application_id,
        )

    def submit(
        self,
        packet: ApplicationPacket,
        manifest: JobManifest,
        approved: bool,
        dry_run: bool,
        providers: list[str],
    ) -> tuple[ApplicationLedgerEntry, list[SubmissionResult]]:
        application_id = self._application_id(packet.candidate_id, packet.job_id)
        timestamp = dt.datetime.now(dt.UTC).isoformat()

        if not approved:
            entry = ApplicationLedgerEntry(
                application_id=application_id,
                candidate_id=packet.candidate_id,
                job_id=packet.job_id,
                submitted_at=None,
                channel="manual-gate",
                status="awaiting_approval",
                notes=["Operator approval required before submission."],
            )
            self._append_ledger(entry)
            return entry, []

        if packet.verified_patch.overall_status != "approved":
            entry = ApplicationLedgerEntry(
                application_id=application_id,
                candidate_id=packet.candidate_id,
                job_id=packet.job_id,
                submitted_at=None,
                channel="verification-gate",
                status="blocked_verification",
                notes=[
                    f"Verification status is {packet.verified_patch.overall_status}.",
                    "Submission blocked until status becomes approved.",
                ],
            )
            self._append_ledger(entry)
            return entry, []

        results: list[SubmissionResult] = []
        for provider in providers:
            if dry_run:
                results.append(
                    SubmissionResult(
                        provider=provider,
                        status="dry_run_ok",
                        detail=(
                            "Simulated submission payload prepared for "
                            f"{manifest.title} at {manifest.company}."
                        ),
                    )
                )
            else:
                # Connector integration point: StackOne/Workday/Greenhouse/etc.
                results.append(
                    SubmissionResult(
                        provider=provider,
                        status="queued",
                        detail="Connector not configured yet. Entry queued for operator execution.",
                    )
                )

        entry = ApplicationLedgerEntry(
            application_id=application_id,
            candidate_id=packet.candidate_id,
            job_id=packet.job_id,
            submitted_at=timestamp,
            channel=",".join(providers),
            status="dry_run_submitted" if dry_run else "queued_for_submission",
            notes=[f"{r.provider}:{r.status}" for r in results],
        )
        self._append_ledger(entry)
        return entry, results

    def read_ledger(self) -> list[ApplicationLedgerEntry]:
        raw = self.ledger_path.read_text(encoding="utf-8").splitlines()
        entries: list[ApplicationLedgerEntry] = []
        for line in raw:
            line = line.strip()
            if not line:
                continue
            entries.append(ApplicationLedgerEntry.model_validate(json.loads(line)))
        return entries
