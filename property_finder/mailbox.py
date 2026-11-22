"""Reads MagicBricks / NoBroker / 99acres / Housing alert emails from an inbox over IMAP.

Set these as secrets (never commit them):
  ALERT_IMAP_HOST      e.g. imap.gmail.com
  ALERT_IMAP_USER      the inbox that receives the portal alerts
  ALERT_IMAP_PASSWORD  an app password (Gmail: Google Account > Security > App passwords)

Alert email layouts differ between portals and change over time. This parser takes every link to a
listing page plus the text around it, which works for the card-style alert emails the portals send.
Once real alert emails arrive, the parser can be tuned to their exact layout.
"""
from __future__ import annotations

import email
import html
import imaplib
import os
import re
from datetime import date
from email.utils import parsedate_to_datetime

from .collectors import from_text, photo_urls
from .models import Listing

LISTING_LINK = re.compile(
    r'<a[^>]+href="(https?://[^"]*(?:magicbricks|nobroker|99acres|housing)\.[^"]+)"', re.I)


def _html_of(msg) -> str:
    for part in msg.walk():
        if part.get_content_type() in ("text/html", "text/plain"):
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8", "replace")
            if part.get_content_type() == "text/html":
                return text
            plain = text
    return locals().get("plain", "")


def _strip(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<br\s*/?>|</(p|div|tr|td|li|h\d)>", "\n", fragment, flags=re.I)
    return html.unescape(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def listings_from_email(raw_html: str, cfg: dict, received: str, source: str) -> list[Listing]:
    out, seen = [], set()
    matches = list(LISTING_LINK.finditer(raw_html))
    for i, m in enumerate(matches):
        url = html.unescape(m.group(1))
        base = re.sub(r"[?#].*$", "", url)
        if base in seen or not re.search(r"\d{5,}|property|detail|pdp", base, re.I):
            continue  # skip unsubscribe / logo / menu links
        seen.add(base)
        end = matches[i + 1].start() if i + 1 < len(matches) else m.start() + 3000
        text = _strip(raw_html[max(0, m.start() - 1500): end])
        if not re.search(r"sq|rent|₹|rs", text, re.I):
            continue
        l = from_text(text, cfg, source=source, url=url)
        photos = photo_urls(raw_html[max(0, m.start() - 1500): end])
        if photos:
            l.extra["photos"] = photos
        l.posted_date = l.posted_date or received   # the alert email's date is the latest possible post date
        out.append(l)
    return out


def clean_secret(name: str, spaces_ok: bool = False) -> str:
    """Secrets pasted into GitHub often carry stray spaces, newlines or quotes; remove them."""
    v = (os.environ.get(name) or "").strip().strip('"').strip("'").strip()
    return v if spaces_ok else v.replace(" ", "")


def describe_host(name: str, value: str, expected: str) -> str:
    """Explain a bad host secret without printing the value (GitHub hides secrets in logs anyway)."""
    hint = "matches" if value == expected else f"does NOT match '{expected}'"
    return f"{name} {hint} (length {len(value)}, expected {len(expected)})"


def fetch_alert_listings(cfg: dict, since: str, log=print) -> list[Listing]:
    host, user = clean_secret("ALERT_IMAP_HOST").lower(), clean_secret("ALERT_IMAP_USER")
    pw = clean_secret("ALERT_IMAP_PASSWORD")   # Gmail shows app passwords with spaces; they are optional
    if not (host and user and pw):
        log("  mailbox: not configured (ALERT_IMAP_* secrets missing), skipping")
        return []
    since_imap = date.fromisoformat(since).strftime("%d-%b-%Y")
    out: list[Listing] = []
    try:
        box = imaplib.IMAP4_SSL(host, timeout=30)
    except OSError as e:
        log(f"  ! mailbox: cannot reach the mail server ({e}). {describe_host('ALERT_IMAP_HOST', host, 'imap.gmail.com')}")
        return []
    with box:
        try:
            box.login(user, pw)
        except imaplib.IMAP4.error as e:
            log(f"  ! mailbox: Gmail refused the login ({e}). Check ALERT_IMAP_USER is the full address and "
                f"ALERT_IMAP_PASSWORD is a 16-character app password, not the normal Gmail password.")
            return []
        box.select("INBOX", readonly=True)
        for sender in cfg.get("alerts", {}).get("portal_senders", []):
            _, ids = box.search(None, f'(SINCE {since_imap} FROM "{sender}")')
            for mid in ids[0].split():
                _, data = box.fetch(mid, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                try:
                    received = parsedate_to_datetime(msg["Date"]).date().isoformat()
                except Exception:
                    received = ""
                out += listings_from_email(_html_of(msg), cfg, received, sender)
    log(f"  mailbox: {len(out)} listings from alert emails")
    return out
