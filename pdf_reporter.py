from __future__ import annotations

"""
Generates a color-coded PDF report of all job applications.
Saved to the user's Desktop as: job_applications_YYYY-MM-DD.pdf
"""
import hashlib
import json
import logging
from datetime import date, datetime
from pathlib import Path

# Python 3.8 compatibility — reportlab calls hashlib.md5(usedforsecurity=False)
# which is only valid from Python 3.9+. Strip the kwarg silently.
_orig_md5 = hashlib.md5
hashlib.md5 = lambda *a, **kw: _orig_md5(*a)  # type: ignore[assignment]

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from config import EXCEL_OUTPUT_DIR
from database import get_all_jobs, get_all_daily_summaries

logger = logging.getLogger(__name__)

# ── Colors (matching the Excel report palette) ────────────────────────────────
C_NAVY       = colors.HexColor("#1F3864")
C_BLUE       = colors.HexColor("#2E75B6")
C_GREEN      = colors.HexColor("#C6EFCE")
C_YELLOW     = colors.HexColor("#FFEB9C")
C_RED        = colors.HexColor("#FFC7CE")
C_GREY       = colors.HexColor("#EDEDED")
C_ALT        = colors.HexColor("#F2F7FF")
C_WHITE      = colors.white
C_DARK_TEXT  = colors.HexColor("#1A1A1A")
C_GREY_TEXT  = colors.HexColor("#555555")


def _status_label(status: str) -> str:
    mapping = {
        "applied":         "Applied",
        "requires_manual": "Manual Apply",
        "failed":          "Failed",
        "skipped":         "Skipped",
        "scored":          "Found",
        "found":           "Found",
    }
    return mapping.get((status or "").lower(), status or "—")


def _row_color(status: str, idx: int):
    s = (status or "").lower()
    if s == "applied":         return C_GREEN
    if s == "requires_manual": return C_YELLOW
    if s == "failed":          return C_RED
    if s in ("skipped", "scored", "found"): return C_GREY
    return C_ALT if idx % 2 == 0 else C_WHITE


def _fmt_score(score) -> str:
    try:
        return f"{float(score):.0%}" if score else "—"
    except Exception:
        return "—"


def _fmt_dt(dt_str: str) -> str:
    if not dt_str:
        return ""
    if "T" in dt_str:
        try:
            return datetime.fromisoformat(dt_str).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    return dt_str[:10]


# ── Applications table ────────────────────────────────────────────────────────

_COLS       = ["Date", "Company", "Job Title", "Location", "Type", "Source", "Match", "Applied?", "Resume Saved As", "Notes"]
_COL_WIDTHS = [2.0, 3.2, 5.0, 2.8, 1.8, 2.2, 1.5, 1.8, 4.0, 3.5]   # cm


def _build_apps_table(jobs: list[dict], today: str, styles) -> list:
    body_style = ParagraphStyle(
        "body", parent=styles["Normal"],
        fontSize=8, leading=10, textColor=C_DARK_TEXT,
    )
    link_style = ParagraphStyle(
        "link", parent=body_style,
        textColor=colors.HexColor("#0563C1"),
    )

    today_jobs  = [j for j in jobs if j.get("date") == today]
    other_jobs  = [j for j in jobs if j.get("date") != today]
    sorted_jobs = today_jobs + other_jobs

    # Header row
    hdr_style = ParagraphStyle(
        "hdr", parent=styles["Normal"],
        fontSize=8.5, leading=11, textColor=C_WHITE, fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    header = [Paragraph(c, hdr_style) for c in _COLS]
    rows   = [header]

    for job in sorted_jobs:
        status = job.get("status", "")
        notes_raw = job.get("notes") or ""
        keywords  = ", ".join(json.loads(notes_raw)) if notes_raw.startswith("[") else ""
        notes_txt = notes_raw if not notes_raw.startswith("[") else ""

        url = job.get("url", "")
        company_cell = (
            Paragraph(f'<link href="{url}">{job.get("company","")}</link>', link_style)
            if url else Paragraph(job.get("company", ""), body_style)
        )

        applied_str = "Yes" if job.get("manually_applied") else "No"
        resume_fn   = job.get("resume_filename") or "—"

        row = [
            Paragraph(job.get("date", "")[:10], body_style),
            company_cell,
            Paragraph(job.get("title", ""), body_style),
            Paragraph(job.get("location", ""), body_style),
            Paragraph((job.get("job_type") or "").title(), body_style),
            Paragraph(job.get("source", ""), body_style),
            Paragraph(_fmt_score(job.get("relevance_score")), ParagraphStyle(
                "sc", parent=body_style, alignment=TA_CENTER)),
            Paragraph(applied_str, ParagraphStyle(
                "ap", parent=body_style, alignment=TA_CENTER)),
            Paragraph(resume_fn, body_style),
            Paragraph(keywords or notes_txt, body_style),
        ]
        rows.append(row)

    col_widths = [w * cm for w in _COL_WIDTHS]
    table = Table(rows, colWidths=col_widths, repeatRows=1)

    ts = [
        # Header
        ("BACKGROUND",  (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR",   (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8.5),
        ("ALIGN",       (0, 0), (-1, 0), "CENTER"),
        ("ROWHEIGHT",   (0, 0), (-1, 0), 20),
        # Body
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8),
        ("ROWHEIGHT",   (0, 1), (-1, -1), 16),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D0D0")),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    # Per-row background colors
    for i, job in enumerate(sorted_jobs, start=1):
        bg = _row_color(job.get("status", ""), i)
        ts.append(("BACKGROUND", (0, i), (-1, i), bg))

    table.setStyle(TableStyle(ts))
    return [table]


# ── Summary table ─────────────────────────────────────────────────────────────

_SUM_COLS   = ["Date", "Jobs Found", "Applied", "Failed", "Manual Review", "Skipped", "Sheets Synced"]
_SUM_WIDTHS = [2.8, 2.8, 2.4, 2.4, 3.2, 2.4, 3.2]


def _build_summary_table(today: str, styles) -> list:
    summaries = get_all_daily_summaries()
    if not summaries:
        return [Paragraph("No summary data yet.", styles["Normal"])]

    cell_style = ParagraphStyle(
        "sc", parent=styles["Normal"],
        fontSize=8.5, leading=11, alignment=TA_CENTER,
    )
    hdr_style = ParagraphStyle(
        "sh", parent=cell_style,
        textColor=C_WHITE, fontName="Helvetica-Bold",
    )

    header = [Paragraph(c, hdr_style) for c in _SUM_COLS]
    rows   = [header]

    for s in summaries:
        is_today = s.get("date") == today
        row = [
            Paragraph(s.get("date", ""), cell_style),
            Paragraph(str(s.get("jobs_found", 0)), cell_style),
            Paragraph(str(s.get("jobs_applied", 0)), cell_style),
            Paragraph(str(s.get("jobs_failed", 0)), cell_style),
            Paragraph(str(s.get("jobs_manual", 0)), cell_style),
            Paragraph(str(s.get("jobs_skipped", 0)), cell_style),
            Paragraph("Yes" if s.get("sheets_updated") else "—", cell_style),
        ]
        rows.append(row)

    col_widths = [w * cm for w in _SUM_WIDTHS]
    table = Table(rows, colWidths=col_widths, repeatRows=1)

    ts = [
        ("BACKGROUND",  (0, 0), (-1, 0), C_NAVY),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8.5),
        ("ROWHEIGHT",   (0, 0), (-1, 0), 20),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8.5),
        ("ROWHEIGHT",   (0, 1), (-1, -1), 16),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D0D0")),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, s in enumerate(summaries, start=1):
        bg = colors.HexColor("#DDEEFF") if s.get("date") == today else (
            C_ALT if i % 2 == 0 else C_WHITE
        )
        ts.append(("BACKGROUND", (0, i), (-1, i), bg))

    table.setStyle(TableStyle(ts))
    return [table]


# ── Main export ───────────────────────────────────────────────────────────────

def export_pdf(today: str = None) -> str:
    if today is None:
        today = date.today().isoformat()

    out_dir  = Path(EXCEL_OUTPUT_DIR)
    out_path = out_dir / f"job_applications_{today}.pdf"

    jobs = get_all_jobs(limit=2000)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=styles["Normal"],
        fontSize=16, fontName="Helvetica-Bold",
        textColor=C_WHITE, alignment=TA_CENTER,
        spaceAfter=0,
    )
    section_style = ParagraphStyle(
        "section",
        parent=styles["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=C_NAVY, spaceBefore=12, spaceAfter=4,
    )
    legend_style = ParagraphStyle(
        "legend",
        parent=styles["Normal"],
        fontSize=8.5, textColor=C_GREY_TEXT,
        spaceAfter=8,
    )

    # ── Stats banner ───────────────────────────────────────────────────────────
    today_jobs    = [j for j in jobs if j.get("date") == today]
    applied_count = sum(1 for j in today_jobs if j.get("status") == "applied")
    manual_count  = sum(1 for j in today_jobs if j.get("status") == "requires_manual")
    failed_count  = sum(1 for j in today_jobs if j.get("status") == "failed")

    story = []

    # Title box (drawn as a 1-cell table for background color)
    title_tbl = Table(
        [[Paragraph(f"Job Applications — {today}", title_style)]],
        colWidths=[doc.width],
    )
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BLUE),
        ("ROWHEIGHT",  (0, 0), (-1, -1), 32),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(title_tbl)
    story.append(Spacer(1, 0.3 * cm))

    # Stats row
    stats_data = [[
        f"Total Today: {len(today_jobs)}",
        f"Applied: {applied_count}",
        f"Manual Needed: {manual_count}",
        f"Failed: {failed_count}",
        f"All-Time: {len(jobs)}",
    ]]
    stat_style = ParagraphStyle("st", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER)
    stats_cells = [[Paragraph(c, stat_style) for c in stats_data[0]]]
    stats_tbl = Table(stats_cells, colWidths=[doc.width / 5] * 5)
    stats_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_ALT),
        ("BOX",        (0, 0), (-1, -1), 0.5, C_NAVY),
        ("INNERGRID",  (0, 0), (-1, -1), 0.3, colors.HexColor("#C0C0C0")),
        ("ROWHEIGHT",  (0, 0), (-1, -1), 18),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(stats_tbl)
    story.append(Spacer(1, 0.3 * cm))

    # Legend
    story.append(Paragraph(
        "<b>Legend:</b>  "
        "<font color='#2A7A2A'>■</font> Applied &nbsp;&nbsp;|&nbsp;&nbsp; "
        "<font color='#B8860B'>■</font> Manual Apply Needed &nbsp;&nbsp;|&nbsp;&nbsp; "
        "<font color='#CC0000'>■</font> Failed &nbsp;&nbsp;|&nbsp;&nbsp; "
        "<font color='#888888'>■</font> Skipped / Low Match",
        legend_style,
    ))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_NAVY))
    story.append(Spacer(1, 0.2 * cm))

    # ── Applications section ───────────────────────────────────────────────────
    story.append(Paragraph("Applications", section_style))
    if jobs:
        story.extend(_build_apps_table(jobs, today, styles))
    else:
        story.append(Paragraph("No applications yet.", styles["Normal"]))

    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_NAVY))

    # ── Daily Summary section ──────────────────────────────────────────────────
    story.append(Paragraph("Daily Summary", section_style))
    story.extend(_build_summary_table(today, styles))

    doc.build(story)
    logger.info("PDF report saved: %s", out_path)
    return str(out_path)
