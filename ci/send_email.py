"""
Sends a daily job digest email via Gmail SMTP (free — uses App Password).

Required env vars (set as GitHub Secrets):
  GMAIL_USER          — Gmail address to send FROM (e.g. you@gmail.com)
  GMAIL_APP_PASSWORD  — 16-char Gmail App Password (not your real password)
  NOTIFY_EMAIL        — Address to send TO (can be same as GMAIL_USER)
"""
from __future__ import annotations

import email.policy
import os
import smtplib
import sqlite3
import sys
from datetime import date
from email.message import EmailMessage


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Replace non-breaking spaces, smart quotes, and strip other non-ASCII noise."""
    if not text:
        return ""
    cleaned = (
        text.replace("\xa0", " ")
            .replace("\u200b", "")
            .replace("\u202f", " ")
            .replace("\u2013", "-")
            .replace("\u2014", "-")
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
    )
    return cleaned.encode("ascii", "ignore").decode("ascii").strip()


def _score_bar(score: float) -> str:
    """Turn 0.0–1.0 into a coloured badge."""
    pct = int(score * 100)
    if pct >= 80:
        color = "#22C55E"   # green
    elif pct >= 65:
        color = "#F59E0B"   # amber
    else:
        color = "#94A3B8"   # grey
    return (
        f'<span style="background:{color};color:#fff;'
        f'padding:2px 8px;border-radius:12px;font-size:12px;font-weight:700;">'
        f'{pct}%</span>'
    )


def _load_jobs(today: str) -> list[dict]:
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jobs.db")
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT title, company, location, url, source, relevance_score, job_type
           FROM jobs
           WHERE date = ?
           ORDER BY relevance_score DESC""",
        (today,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── HTML email template ───────────────────────────────────────────────────────

def _build_html(jobs: list[dict], today: str) -> str:
    total   = len(jobs)
    strong  = [j for j in jobs if j.get("relevance_score", 0) >= 0.80]
    good    = [j for j in jobs if 0.65 <= j.get("relevance_score", 0) < 0.80]
    others  = [j for j in jobs if j.get("relevance_score", 0) < 0.65]

    def job_rows(job_list: list[dict]) -> str:
        if not job_list:
            return '<tr><td colspan="5" style="color:#94A3B8;padding:12px;text-align:center;">None</td></tr>'
        rows = ""
        for j in job_list:
            url     = _clean(j.get("url", "#"))
            company = _clean(j.get("company", "—")) or "—"
            title   = _clean(j.get("title", "—")) or "—"
            loc     = _clean(j.get("location", "")) or "—"
            src     = _clean(j.get("source", "—"))
            score   = j.get("relevance_score") or 0.0
            rows += f"""
            <tr style="border-bottom:1px solid #1E2535;">
              <td style="padding:10px 12px;">
                <a href="{url}" style="color:#60A5FA;text-decoration:none;font-weight:600;">{title}</a>
              </td>
              <td style="padding:10px 12px;color:#CBD5E1;">{company}</td>
              <td style="padding:10px 12px;color:#94A3B8;font-size:13px;">{loc}</td>
              <td style="padding:10px 12px;color:#94A3B8;font-size:13px;">{src}</td>
              <td style="padding:10px 12px;text-align:center;">{_score_bar(score)}</td>
            </tr>"""
        return rows

    def section(title: str, color: str, job_list: list[dict]) -> str:
        return f"""
        <tr>
          <td colspan="5" style="background:{color};padding:8px 12px;
              font-size:12px;font-weight:700;color:#fff;letter-spacing:0.08em;
              text-transform:uppercase;">
            {title} ({len(job_list)})
          </td>
        </tr>
        {job_rows(job_list)}"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0D1117;font-family:'Segoe UI',Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0D1117;padding:32px 0;">
    <tr><td align="center">
      <table width="680" cellpadding="0" cellspacing="0"
             style="background:#161B27;border-radius:16px;overflow:hidden;
                    border:1px solid rgba(255,255,255,0.07);">

        <!-- Header banner -->
        <tr>
          <td style="background:linear-gradient(135deg,#1E3A5F,#2563EB);
                     padding:28px 32px;text-align:center;">
            <div style="font-size:28px;">💼</div>
            <div style="font-size:22px;font-weight:700;color:#fff;margin-top:6px;">
              JobAgent — Daily Digest
            </div>
            <div style="font-size:14px;color:rgba(255,255,255,0.7);margin-top:4px;">
              {today}
            </div>
          </td>
        </tr>

        <!-- Stats row -->
        <tr>
          <td style="padding:0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:20px;text-align:center;border-right:1px solid rgba(255,255,255,0.06);">
                  <div style="font-size:32px;font-weight:700;color:#F1F5F9;">{total}</div>
                  <div style="font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:0.07em;margin-top:2px;">Jobs Found</div>
                </td>
                <td style="padding:20px;text-align:center;border-right:1px solid rgba(255,255,255,0.06);">
                  <div style="font-size:32px;font-weight:700;color:#22C55E;">{len(strong)}</div>
                  <div style="font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:0.07em;margin-top:2px;">Strong Match ≥80%</div>
                </td>
                <td style="padding:20px;text-align:center;border-right:1px solid rgba(255,255,255,0.06);">
                  <div style="font-size:32px;font-weight:700;color:#F59E0B;">{len(good)}</div>
                  <div style="font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:0.07em;margin-top:2px;">Good Match 65–79%</div>
                </td>
                <td style="padding:20px;text-align:center;">
                  <div style="font-size:32px;font-weight:700;color:#94A3B8;">{len(others)}</div>
                  <div style="font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:0.07em;margin-top:2px;">Lower Match</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Jobs table -->
        <tr>
          <td style="padding:0 24px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;border-radius:10px;overflow:hidden;
                          border:1px solid rgba(255,255,255,0.07);">
              <!-- Column headers -->
              <tr style="background:#0D1117;">
                <td style="padding:10px 12px;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.07em;">Job Title</td>
                <td style="padding:10px 12px;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.07em;">Company</td>
                <td style="padding:10px 12px;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.07em;">Location</td>
                <td style="padding:10px 12px;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.07em;">Source</td>
                <td style="padding:10px 12px;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.07em;text-align:center;">Match</td>
              </tr>
              {section("Strong Match — Apply First", "#166534", strong)}
              {section("Good Match", "#92400E", good)}
              {section("Lower Match", "#374151", others)}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 24px;border-top:1px solid rgba(255,255,255,0.06);
                     text-align:center;font-size:12px;color:#475569;">
            Open the <strong style="color:#60A5FA;">JobAgent UI</strong> on your Mac
            to mark which ones you applied to.
            &nbsp;·&nbsp; Automated by GitHub Actions
          </td>
        </tr>

      </table>
    </td></tr>
  </table>

</body>
</html>"""


def _build_plain(jobs: list[dict], today: str) -> str:
    lines = [f"JobAgent Daily Digest - {today}", "=" * 50, ""]
    for j in jobs:
        score = int((j.get("relevance_score") or 0) * 100)
        lines.append(f"[{score}%] {_clean(j.get('title','?'))} @ {_clean(j.get('company','?'))}")
        lines.append(f"      {_clean(j.get('location',''))}")
        lines.append(f"      {_clean(j.get('url',''))}")
        lines.append("")
    return "\n".join(lines)


# ── Send ──────────────────────────────────────────────────────────────────────

def send_digest(today: str = None) -> None:
    today = today or date.today().isoformat()

    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    app_pass   = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    to_email   = os.environ.get("NOTIFY_EMAIL", gmail_user).strip()

    if not gmail_user or not app_pass:
        print("GMAIL_USER or GMAIL_APP_PASSWORD not set — skipping email.")
        return

    jobs = _load_jobs(today)
    if not jobs:
        print("No jobs found today — skipping email.")
        return

    msg = EmailMessage(policy=email.policy.SMTP)
    msg["Subject"] = f"[JobAgent] {len(jobs)} Jobs Found - {today}"
    msg["From"]    = gmail_user
    msg["To"]      = to_email

    # Sanitize to ASCII — plain text drops non-ASCII, HTML converts to entities
    plain = _build_plain(jobs, today).encode("ascii", "ignore").decode("ascii")
    html  = _build_html(jobs, today).encode("ascii", "xmlcharrefreplace").decode("ascii")

    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, app_pass)
            smtp.send_message(msg)
        print(f"Email sent to {to_email} - {len(jobs)} jobs listed.")
    except Exception as e:
        print(f"Email failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    send_digest()