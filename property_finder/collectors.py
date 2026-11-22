"""Ways listings get into the system.

1. Inbox files  - CSV / JSON files in data/inbox/ (exports or copy-paste from your
                  MagicBricks / NoBroker premium accounts, broker WhatsApp lists, etc.)
2. Pasted text  - raw listing text copied from any portal or WhatsApp message.
3. Watch URLs   - public listing pages in data/watch_urls.txt, fetched and parsed
                  (JSON-LD / meta tags / page text). Best-effort: portals change
                  their HTML and may block automated requests.
"""
from __future__ import annotations

import csv
import html
import json
import re
import time
import urllib.request
from pathlib import Path

from .models import Listing
from .parse import (detect_floor, detect_outdoor, find_area_in_text, find_posted_in_text, find_rent_in_text,
                    match_locality, parse_area, parse_money, parse_posted_date)

# Column names seen in portal exports / spreadsheets -> our field names.
HEADER_MAP = {
    "title": "title", "name": "title", "property": "title", "property name": "title",
    "locality": "locality", "area name": "locality", "location": "locality", "sublocality": "locality",
    "address": "address", "full address": "address", "landmark": "address",
    "rent": "rent", "price": "rent", "monthly rent": "rent", "rent (inr)": "rent", "expected rent": "rent",
    "area": "area_sqft", "area_sqft": "area_sqft", "sqft": "area_sqft", "size": "area_sqft",
    "carpet area": "area_sqft", "super area": "area_sqft", "built up area": "area_sqft", "builtup area": "area_sqft",
    "deposit": "deposit", "security deposit": "deposit",
    "floor": "floor", "outdoor": "outdoor", "outdoor area": "outdoor", "open space": "outdoor",
    "description": "description", "details": "description", "notes": "description", "amenities": "description",
    "url": "url", "link": "url", "listing url": "url",
    "posted": "posted_date", "posted on": "posted_date", "posted_date": "posted_date", "date": "posted_date",
    "updated": "posted_date", "updated on": "posted_date", "last updated": "posted_date", "listed on": "posted_date",
    "photos": "photos", "images": "photos", "photo urls": "photos", "image urls": "photos", "pictures": "photos",
    "source": "source", "portal": "source", "contact": "contact", "owner": "contact", "phone": "contact",
}


def _truthy(v) -> bool | None:
    if v is None or str(v).strip() == "":
        return None
    return str(v).strip().lower() in ("y", "yes", "true", "1", "available")


def from_record(rec: dict, config: dict, source: str = "") -> Listing:
    """Normalise one row (any column naming) into a Listing."""
    data: dict = {}
    for k, v in rec.items():
        if k is None:
            continue
        field = HEADER_MAP.get(k.strip().lower())
        if field and v not in (None, "") and field not in data:
            data[field] = v.strip() if isinstance(v, str) else v
    lst = Listing(
        title=str(data.get("title", "")),
        address=str(data.get("address", "")),
        description=str(data.get("description", "")),
        url=str(data.get("url", "")),
        contact=str(data.get("contact", "")),
        source=str(data.get("source", source)),
        rent=parse_money(data.get("rent")),
        area_sqft=parse_area(data.get("area_sqft")),
        deposit=parse_money(data.get("deposit")),
        floor=str(data.get("floor", "")),
        outdoor=_truthy(data.get("outdoor")),
        posted_date=parse_posted_date(str(data.get("posted_date", ""))),
    )
    blob = " ".join([str(data.get("locality", "")), lst.title, lst.address, lst.description])
    photos = data.get("photos")
    if isinstance(photos, str):
        photos = re.findall(r"https?://[^\s,|]+", photos)
    if photos:
        lst.extra["photos"] = list(dict.fromkeys(photos))
    lst.locality = match_locality(blob, config) or str(data.get("locality", "")).strip().title()
    if lst.rent is None:
        lst.rent = find_rent_in_text(blob)
    if lst.area_sqft is None:
        lst.area_sqft = find_area_in_text(blob)
    if lst.outdoor is None:
        lst.outdoor = detect_outdoor(blob)
    lst.floor = detect_floor(lst.floor + " floor") if lst.floor else detect_floor(blob)
    if not lst.posted_date:
        lst.posted_date = find_posted_in_text(blob)
    if not lst.source and lst.url:
        lst.source = _source_from_url(lst.url)
    return lst


def _source_from_url(url: str) -> str:
    for p in ("magicbricks", "nobroker", "99acres", "housing", "squareyards", "commonfloor"):
        if p in url.lower():
            return p
    return "web"


def load_inbox(inbox: Path, config: dict) -> list[Listing]:
    out: list[Listing] = []
    for path in sorted(inbox.glob("*")):
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as f:
                out += [from_record(r, config, source=path.stem) for r in csv.DictReader(f)]
        elif path.suffix.lower() == ".json":
            rows = json.loads(path.read_text(encoding="utf-8"))
            rows = rows if isinstance(rows, list) else rows.get("listings", [])
            out += [from_record(r, config, source=path.stem) for r in rows]
        elif path.suffix.lower() == ".txt":
            # Listings pasted one after another, separated by a line containing only ---
            for chunk in re.split(r"^\s*-{3,}\s*$", path.read_text(encoding="utf-8"), flags=re.M):
                if chunk.strip():
                    out.append(from_text(chunk, config, source=path.stem))
    return out


def from_text(text: str, config: dict, source: str = "pasted", url: str = "") -> Listing:
    """Parse a free-text listing (copied from a portal page or a WhatsApp message)."""
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    urls = re.findall(r"https?://\S+", text)
    return from_record({
        "title": first_line[:120],
        "description": text.strip()[:2000],
        "url": url or (urls[0] if urls else ""),
        "source": source,
    }, config, source)


# ---------- public URL fetching ----------

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-IN,en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _jsonld_blocks(page: str) -> list[dict]:
    blocks = []
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(html.unescape(raw.strip()))
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                blocks.append(d)
                stack += [v for v in d.values() if isinstance(v, (dict, list))]
            elif isinstance(d, list):
                stack += d
    return blocks


IMG_SKIP = re.compile(r"logo|icon|sprite|avatar|banner|badge|pixel|tracking|placeholder|\.svg", re.I)


def photo_urls(page: str, meta: dict | None = None) -> list[str]:
    """Listing photos from og:image, JSON-LD image fields and large <img> tags."""
    urls = []
    if meta and meta.get("og:image"):
        urls.append(meta["og:image"])
    for b in _jsonld_blocks(page):
        img = b.get("image")
        for i in (img if isinstance(img, list) else [img]):
            if isinstance(i, str):
                urls.append(i)
            elif isinstance(i, dict) and i.get("url"):
                urls.append(i["url"])
    urls += re.findall(r'<img[^>]+(?:data-src|src)="(https?://[^"]+\.(?:jpe?g|png|webp)[^"]*)"', page, re.I)
    return [html.unescape(u) for u in dict.fromkeys(urls) if not IMG_SKIP.search(u)][:12]


def from_url(url: str, config: dict) -> Listing:
    page = _get(url)
    meta = dict(re.findall(r'<meta[^>]+(?:property|name)="([^"]+)"[^>]+content="([^"]*)"', page, re.I))
    title = html.unescape(meta.get("og:title") or (re.findall(r"<title>(.*?)</title>", page, re.S) or [""])[0])
    desc = html.unescape(meta.get("og:description") or meta.get("description") or "")
    rec = {"title": title.strip(), "description": desc, "url": url, "source": _source_from_url(url)}
    for b in _jsonld_blocks(page):
        rec.setdefault("posted_date", b.get("datePosted") or b.get("dateModified") or b.get("datePublished"))
        offers = b.get("offers") if isinstance(b.get("offers"), dict) else {}
        rec.setdefault("rent", b.get("price") or offers.get("price"))
        size = b.get("floorSize")
        if isinstance(size, dict):
            rec.setdefault("area_sqft", f'{size.get("value")} {size.get("unitText") or size.get("unitCode") or "sqft"}')
        addr = b.get("address")
        if isinstance(addr, dict):
            rec.setdefault("address", " ".join(str(v) for v in addr.values() if isinstance(v, str)))
    rec["photos"] = photo_urls(page, meta)
    body = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I))
    rec["description"] = (desc + " " + html.unescape(re.sub(r"\s+", " ", body))[:3000]).strip()
    rec = {k: v for k, v in rec.items() if v not in (None, "")}
    return from_record(rec, config)


def load_watch_urls(path: Path, config: dict, delay: float = 3.0, log=print) -> list[Listing]:
    if not path.exists():
        return []
    out = []
    urls = [u.strip() for u in path.read_text().splitlines() if u.strip() and not u.startswith("#")]
    for i, url in enumerate(urls):
        try:
            out.append(from_url(url, config))
        except Exception as e:  # network errors, blocks, layout changes
            log(f"  ! could not fetch {url}: {e}")
        if i < len(urls) - 1:
            time.sleep(delay)  # be polite to the portals
    return out
