"""Sends new matches by email and/or Telegram. Each channel switches on when its secrets are set.

Email:     NOTIFY_SMTP_HOST, NOTIFY_SMTP_PORT (587), NOTIFY_SMTP_USER, NOTIFY_SMTP_PASSWORD, NOTIFY_EMAIL_TO
Telegram:  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import json
import os
import smtplib
import urllib.parse
import urllib.request
from email.mime.text import MIMEText

from .scoring import Scored


def _line(s: Scored) -> str:
    l = s.listing
    bits = [f"{s.score}/100", l.locality or "?", f"₹{l.rent:,}" if l.rent else "rent ?",
            f"{l.area_sqft} sqft" if l.area_sqft else "", "outdoor ✓" if l.outdoor else "",
            "ground floor" if l.floor == "ground" else "", f"posted {l.posted_date}" if l.posted_date else ""]
    return f"{l.title[:80]}\n  " + " · ".join(b for b in bits if b) + (f"\n  {l.url}" if l.url else "")


def message(matches: list[Scored], concept: str) -> tuple[str, str]:
    subject = f"{concept}: {len(matches)} new matching shop{'s' if len(matches) != 1 else ''}"
    body = "\n\n".join(f"{i}. {_line(s)}" for i, s in enumerate(matches, 1))
    return subject, body + "\n\nFull report: reports/latest.html"


def send(matches: list[Scored], concept: str, log=print) -> int:
    if not matches:
        return 0
    subject, body = message(matches, concept)
    sent = 0
    env = os.environ
    if env.get("NOTIFY_SMTP_HOST") and env.get("NOTIFY_EMAIL_TO"):
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subject, env.get("NOTIFY_SMTP_USER", ""), env["NOTIFY_EMAIL_TO"]
        with smtplib.SMTP(env["NOTIFY_SMTP_HOST"], int(env.get("NOTIFY_SMTP_PORT", "587")), timeout=30) as s:
            s.starttls()
            s.login(env["NOTIFY_SMTP_USER"], env["NOTIFY_SMTP_PASSWORD"])
            s.send_message(msg)
        sent += 1
        log("  notified by email")
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        data = urllib.parse.urlencode({"chat_id": env["TELEGRAM_CHAT_ID"], "text": f"{subject}\n\n{body}"[:4000],
                                       "disable_web_page_preview": "true"}).encode()
        url = f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage"
        with urllib.request.urlopen(url, data=data, timeout=30) as r:
            json.load(r)
        sent += 1
        log("  notified on Telegram")
    if not sent:
        log("  no notification channel configured; matches are in the report only")
    return sent
