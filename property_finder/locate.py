"""Estimates where a shop is when the listing hides the exact address.

Claude looks at the listing photos for location clues: signboards and shop names, building or
complex names, Hyderabad Metro pillar numbers (printed on every pillar, e.g. "P-1034"), bank or
brand outlets, road dividers, flyovers and the skyline. It returns the clues it found plus search
queries. Each query is checked against OpenStreetMap (Nominatim) to get map coordinates.

The result is an ESTIMATE with a confidence level. Confirm it with the owner or broker, or on a visit,
before committing to anything.

Needs: ANTHROPIC_API_KEY (as a GitHub secret) and `pip install anthropic`.
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse
import urllib.request

from .models import Listing

MODEL = "claude-opus-5-5"
MAX_PHOTOS = 6
MAX_PHOTO_BYTES = 4_500_000
UA = "chilli-theory-property-finder/1.0"   # generic client name for OpenStreetMap's usage policy
HYD_VIEWBOX = "78.20,17.62,78.62,17.30"    # lon/lat box around west & north-west Hyderabad

SCHEMA = {
    "type": "object",
    "properties": {
        "visible_text": {"type": "array", "items": {"type": "string"},
                         "description": "Readable signboards, shop names, building names, metro pillar numbers, road signs"},
        "landmarks": {"type": "array", "items": {"type": "string"},
                      "description": "Recognisable places or features: metro line, flyover, mall, temple, junction"},
        "frontage": {"type": "string",
                     "description": "What is directly in front of the shop: open setback, footpath, parking, main road, service lane"},
        "outdoor_space": {"type": "string", "enum": ["visible", "maybe", "not_visible", "no_photos"]},
        "outdoor_space_notes": {"type": "string",
                                "description": "Approximate depth/width of open space in front, and whether it looks private or public footpath"},
        "likely_location": {"type": "string",
                            "description": "Best guess of the street / area / near-what, in plain words"},
        "search_queries": {"type": "array", "items": {"type": "string"},
                           "description": "2-4 map search queries, most specific first, each ending in the locality and 'Hyderabad'"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reasoning": {"type": "string"},
    },
    "required": ["visible_text", "landmarks", "frontage", "outdoor_space", "outdoor_space_notes",
                 "likely_location", "search_queries", "confidence", "reasoning"],
    "additionalProperties": False,
}

PROMPT = """These photos come from a commercial shop-for-rent listing in {locality}, Hyderabad, India.
The listing does not give the exact address. The renter wants to visit this site for a wok and kebab
restaurant, so work out as precisely as you can where the shop is.

Listing text:
{text}

Look closely at every photo for:
- readable text: shop signboards next door or opposite, building or apartment names, banks, ATMs, pharmacies, brand outlets
- Hyderabad Metro pillar numbers (stencilled on each pillar, e.g. "P-1034" or "C-890"), metro stations, the elevated track
- road features: medians, flyovers, bus stops, junctions, traffic signals, wide arterial road or narrow lane
- skyline: IT towers, malls, temples, water tanks, hills
- the space directly in front of the shop: is there open setback space for tables, or only the public footpath?

Rules:
- Only report text you can actually read. Do not invent shop names.
- Confidence: "high" only when a readable name or pillar number pins it down. "low" when you only have the general area.
- Search queries should use what you actually saw (e.g. "Ratnadeep Supermarket Miyapur X Roads Hyderabad")."""


def _download(url: str) -> tuple[str, str] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get_content_type()
            data = r.read(MAX_PHOTO_BYTES + 1)
    except Exception:
        return None
    if len(data) > MAX_PHOTO_BYTES or ctype not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        return None
    return ctype, base64.standard_b64encode(data).decode()


def _image_blocks(urls: list[str]) -> list[dict]:
    blocks = []
    for url in urls[:MAX_PHOTOS]:
        img = _download(url)
        if img:  # portals' image CDNs often refuse other servers, so send the bytes ourselves
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": img[0], "data": img[1]}})
    return blocks


def analyse_photos(listing: Listing, client=None) -> dict | None:
    """Ask Claude for location clues. Returns the parsed SCHEMA dict, or None if there's nothing to analyse."""
    photos = listing.extra.get("photos") or []
    images = _image_blocks(photos)
    if not images:
        return None
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    text = "\n".join(x for x in [listing.title, listing.address, listing.description[:1500]] if x)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            *images,
            {"type": "text", "text": PROMPT.format(locality=listing.locality or "west Hyderabad", text=text)},
        ]}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        return None
    raw = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(raw) if raw else None


def geocode(query: str) -> dict | None:
    """Look a query up on OpenStreetMap Nominatim, restricted to the Hyderabad area. Max 1 request/sec."""
    params = urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "in",
                                     "viewbox": HYD_VIEWBOX, "bounded": 1})
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{params}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            hits = json.load(r)
    except Exception:
        return None
    finally:
        time.sleep(1.1)
    if not hits:
        return None
    h = hits[0]
    return {"lat": float(h["lat"]), "lon": float(h["lon"]), "display_name": h.get("display_name", ""), "query": query}


def maps_link(guess: dict) -> str:
    if guess.get("point"):
        p = guess["point"]
        return f"https://www.google.com/maps/search/?api=1&query={p['lat']},{p['lon']}"
    q = (guess.get("search_queries") or [guess.get("likely_location", "")])[0]
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote_plus(q)


def needs_locating(l: Listing) -> bool:
    """True when the address is missing or just the locality name, and photos are available."""
    if l.extra.get("location_guess") or not l.extra.get("photos"):
        return False
    addr = re.sub(r"\W+", " ", (l.address or "")).strip().lower()
    vague = len(addr.split()) <= 3 or addr in ("", (l.locality or "").lower(), f"{(l.locality or '').lower()} hyderabad")
    return vague


def locate(listing: Listing, client=None, log=print) -> dict | None:
    guess = analyse_photos(listing, client)
    if not guess:
        return None
    for q in guess.get("search_queries", [])[:4]:
        hit = geocode(q)
        if hit:
            guess["point"] = hit
            break
    guess["map"] = maps_link(guess)
    listing.extra["location_guess"] = guess
    # A clear photo of open space in front is better evidence than listing text alone
    if guess.get("outdoor_space") == "visible" and listing.outdoor is None:
        listing.outdoor = True
    log(f"  located {listing.title[:50]!r}: {guess['likely_location'][:70]} ({guess['confidence']})")
    return guess
