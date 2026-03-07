from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.schemas import ApplicationPacket


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render resume and cover letter PDFs from application_packet.json")
    parser.add_argument(
        "--application-packet",
        default=None,
        help="Path to application_packet.json",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for generated PDFs",
    )
    return parser.parse_args()


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _styles():
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "Name",
            parent=base["Title"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#111827"),
        ),
        "header": ParagraphStyle(
            "Header",
            parent=base["Heading3"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#374151"),
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#111827"),
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontSize=10.5,
            leading=14,
            leftIndent=12,
            bulletIndent=0,
            textColor=colors.HexColor("#111827"),
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#4b5563"),
        ),
    }


def _extract_headline_summary(packet: ApplicationPacket) -> tuple[str | None, str | None]:
    headline = packet.verified_patch.headline_patch
    summary = packet.verified_patch.summary_patch
    if headline or summary:
        return headline, summary

    extracted_headline = None
    extracted_summary = None
    for line in packet.sanitized_resume_text.splitlines():
        line = line.strip()
        if line.lower().startswith("headline:"):
            extracted_headline = line.split(":", 1)[1].strip()
        elif line.lower().startswith("summary:"):
            extracted_summary = line.split(":", 1)[1].strip()
    return extracted_headline, extracted_summary


def _extract_bullets(packet: ApplicationPacket) -> list[str]:
    if packet.verified_patch.rewritten_claims:
        return [claim.text.strip() for claim in packet.verified_patch.rewritten_claims if claim.text.strip()]

    bullets: list[str] = []
    for line in packet.sanitized_resume_text.splitlines():
        line = line.strip()
        if line.startswith("-"):
            value = line.lstrip("-").strip()
            if value:
                bullets.append(value)
    return bullets


def _parse_resume_sections(resume_text: str) -> tuple[list[str], dict[str, list[str]]]:
    heading_names = {
        "professional summary",
        "technical skills",
        "professional experience",
        "projects",
        "education",
    }
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    preface: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        lower = line.lower()
        if lower in heading_names:
            current = lower.title()
            sections.setdefault(current, [])
            continue
        if current is None:
            preface.append(line)
            continue
        sections[current].append(line)
    return preface, sections


def _build_resume(packet: ApplicationPacket, out_file: Path) -> None:
    styles = _styles()
    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="Tailored Resume",
    )

    name = packet.outbound_fields.get("candidate_name", "").strip() or "Candidate"
    email = packet.outbound_fields.get("candidate_email", "").strip()
    target_title = packet.outbound_fields.get("job_title", "").strip()
    company = packet.outbound_fields.get("company", "").strip()
    headline, summary = _extract_headline_summary(packet)
    preface, sections = _parse_resume_sections(packet.sanitized_resume_text)
    bullets = _extract_bullets(packet)

    story = [Paragraph(name, styles["name"]), Spacer(1, 6)]
    meta_line = " | ".join(part for part in [email, target_title] if part)
    if meta_line:
        story.append(Paragraph(meta_line, styles["small"]))
        story.append(Spacer(1, 6))
    if company:
        story.append(Paragraph(f"Target Role: {target_title} at {company}", styles["small"]))
        story.append(Spacer(1, 10))

    if preface:
        for row in preface:
            story.append(Paragraph(row, styles["small"]))
        story.append(Spacer(1, 6))

    if headline:
        story.append(Paragraph("Headline", styles["header"]))
        story.append(Paragraph(headline, styles["body"]))
        story.append(Spacer(1, 6))

    summary_rows = sections.get("Professional Summary", [])
    if summary_rows or summary:
        story.append(Paragraph("Professional Summary", styles["header"]))
        summary_text = " ".join(summary_rows).strip() or summary or ""
        if summary_text:
            story.append(Paragraph(summary_text, styles["body"]))
            story.append(Spacer(1, 6))

    skill_rows = sections.get("Technical Skills", [])
    if skill_rows:
        story.append(Paragraph("Technical Skills", styles["header"]))
        story.append(Paragraph(" ".join(skill_rows), styles["body"]))
        story.append(Spacer(1, 6))

    exp_rows = sections.get("Professional Experience", [])
    if exp_rows:
        story.append(Paragraph("Professional Experience", styles["header"]))
        for row in exp_rows:
            if row.startswith("-"):
                story.append(Paragraph(row.lstrip("- ").strip(), styles["bullet"], bulletText="•"))
            else:
                story.append(Paragraph(row, styles["body"]))
            story.append(Spacer(1, 2))
        story.append(Spacer(1, 4))
    elif bullets:
        story.append(Paragraph("Professional Experience", styles["header"]))
        for bullet in bullets:
            story.append(Paragraph(bullet, styles["bullet"], bulletText="•"))
            story.append(Spacer(1, 2))
        story.append(Spacer(1, 4))

    project_rows = sections.get("Projects", [])
    if project_rows:
        story.append(Paragraph("Projects", styles["header"]))
        for row in project_rows:
            if row.startswith("-"):
                story.append(Paragraph(row.lstrip("- ").strip(), styles["bullet"], bulletText="•"))
            else:
                story.append(Paragraph(row, styles["body"]))
            story.append(Spacer(1, 2))
        story.append(Spacer(1, 4))

    education_rows = sections.get("Education", [])
    if education_rows:
        story.append(Paragraph("Education", styles["header"]))
        for row in education_rows:
            story.append(Paragraph(row, styles["body"]))
            story.append(Spacer(1, 2))

    doc.build(story)


def _build_cover_letter(packet: ApplicationPacket, out_file: Path) -> None:
    styles = _styles()
    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title="Cover Letter",
    )

    name = packet.outbound_fields.get("candidate_name", "").strip() or "Candidate"
    email = packet.outbound_fields.get("candidate_email", "").strip()
    title = packet.outbound_fields.get("job_title", "").strip()
    company = packet.outbound_fields.get("company", "").strip()
    content = (packet.sanitized_cover_letter_text or "").strip()

    story: list = [Paragraph(name, styles["name"])]
    if email:
        story.append(Paragraph(email, styles["small"]))
    story.append(Spacer(1, 14))
    if title or company:
        story.append(Paragraph(f"Application for {title} at {company}".strip(), styles["small"]))
        story.append(Spacer(1, 12))

    if not content:
        content = (
            "Dear Hiring Manager,\n\n"
            "Please consider my application for this role. I have attached a tailored resume.\n\n"
            "Sincerely,\n"
            f"{name}"
        )

    for para in [p.strip() for p in content.split("\n") if p.strip()]:
        story.append(Paragraph(para, styles["body"]))
        story.append(Spacer(1, 8))

    doc.build(story)


def main() -> None:
    _load_dotenv(ROOT / ".env")
    args = _parse_args()
    packet_raw = args.application_packet or os.getenv("SJH_APPLICATION_PACKET_PATH")
    out_raw = args.out_dir or os.getenv("SJH_PDF_OUTPUT_DIR")
    if not packet_raw:
        raise RuntimeError(
            "Missing application packet path. Set SJH_APPLICATION_PACKET_PATH or pass --application-packet."
        )
    if not out_raw:
        raise RuntimeError(
            "Missing PDF output dir. Set SJH_PDF_OUTPUT_DIR or pass --out-dir."
        )
    packet_path = Path(packet_raw)
    out_dir = Path(out_raw)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = json.loads(packet_path.read_text(encoding="utf-8"))
    packet = ApplicationPacket.model_validate(raw)

    resume_pdf = out_dir / "resume.pdf"
    cover_pdf = out_dir / "cover_letter.pdf"
    _build_resume(packet, resume_pdf)
    _build_cover_letter(packet, cover_pdf)

    print("PDF rendering completed.")
    print(f"Resume PDF: {resume_pdf}")
    print(f"Cover Letter PDF: {cover_pdf}")


if __name__ == "__main__":
    main()
