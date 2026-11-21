"""Writes the daily report as HTML (for reading), Markdown (for GitHub) and CSV (for Excel)."""
from __future__ import annotations

import csv
import html
from pathlib import Path

from .scoring import Scored

TIER_LABEL = {"match": "Full match", "close": "Close (verify)", "stretch": "Stretch option"}


def _money(v):
    return f"₹{v:,}" if v else "?"


def write_csv(rows: list[Scored], path: Path):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "score", "tier", "new", "locality", "title", "rent", "area_sqft", "rent_psf",
                    "outdoor", "floor", "posted_date", "orders_per_day_needed", "url", "contact", "why", "watch_out"])
        for i, s in enumerate(rows, 1):
            l = s.listing
            w.writerow([i, s.score, s.tier, l.extra.get("new", False), l.locality, l.title, l.rent, l.area_sqft,
                        s.rent_psf, l.outdoor, l.floor, l.posted_date, s.orders_per_day_needed, l.url, l.contact,
                        "; ".join(s.reasons), "; ".join(s.warnings)])


def write_markdown(rows: list[Scored], meta: dict, path: Path):
    lines = [f"# {meta['concept']}: shop shortlist for {meta['date']}", "",
             f"Scanned {meta['total']} active listings. **{meta['matches']} full matches**, "
             f"{meta['new']} new today. Showing the top {len(rows)}.", ""]
    if meta.get("shortfall"):
        lines += [f"> ⚠️ {meta['shortfall']}", ""]
    lines += ["| # | Score | Tier | Area | Rent | Sqft | Outdoor | Floor | Orders/day* | Listing |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for i, s in enumerate(rows, 1):
        l = s.listing
        name = (l.title or l.address or "listing")[:60].replace("|", "/")
        link = f"[{name}]({l.url})" if l.url else name
        new = " 🆕" if l.extra.get("new") else ""
        lines.append(f"| {i} | {s.score} | {TIER_LABEL[s.tier]}{new} | {l.locality or '?'} | {_money(l.rent)} | "
                     f"{l.area_sqft or '?'} | {'✅' if l.outdoor else ('❌' if l.outdoor is False else '?')} | "
                     f"{l.floor or '?'} | {s.orders_per_day_needed or '?'} | {link} |")
    lines += ["", "*Orders per day needed at ₹320 average order value to keep rent at 12% of sales.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


CSS = """
:root{--bg:#fbf7f2;--card:#fff;--ink:#2a1a12;--muted:#7a6558;--line:#eadfd5;--accent:#c2410c;--good:#15803d;--warn:#b45309}
@media (prefers-color-scheme:dark){:root{--bg:#17110d;--card:#221913;--ink:#f5ebe2;--muted:#b9a596;--line:#3a2c22;--accent:#fb923c;--good:#4ade80;--warn:#fbbf24}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}
.sub{color:var(--muted);margin:0 0 20px}.stats{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:120px}
.stat b{display:block;font-size:22px}.stat span{color:var(--muted);font-size:13px}
.alert{border-left:4px solid var(--warn);background:var(--card);padding:10px 14px;border-radius:6px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px}
.top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.score{font-size:24px;font-weight:700;color:var(--accent);white-space:nowrap}.score small{font-size:12px;color:var(--muted);font-weight:400}
.title{font-weight:600;font-size:16px;margin:0}.title a{color:inherit}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.tag{border:1px solid var(--line);border-radius:999px;padding:1px 9px;font-size:13px}
.tag.match{border-color:var(--good);color:var(--good)}.tag.new{background:var(--accent);color:#fff;border-color:var(--accent)}
ul{margin:6px 0 0;padding-left:18px}li.w{color:var(--warn)}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid var(--line);padding:6px;text-align:left}
td a{color:var(--accent);margin-right:10px}.wrap{overflow-x:auto}
"""


def write_html(rows: list[Scored], meta: dict, links: dict, path: Path):
    e = html.escape
    out = [f"<!doctype html><html lang=en><head><meta charset=utf-8>"
           f"<meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>Chilli Theory Shortlist</title><style>{CSS}</style></head><body><main>",
           f"<h1>{e(meta['concept'])}: shop shortlist</h1>",
           f"<p class=sub>{e(meta['date'])} · Rent ₹{meta['rent_min']:,} to ₹{meta['rent_max']:,} · "
           f"{meta['area_min']}+ sqft · outdoor space preferred</p>",
           "<div class=stats>"
           f"<div class=stat><b>{meta['matches']}</b><span>full matches</span></div>"
           f"<div class=stat><b>{meta['new']}</b><span>new today</span></div>"
           f"<div class=stat><b>{meta['total']}</b><span>active listings scanned</span></div>"
           f"<div class=stat><b>{len(rows)}</b><span>in this shortlist</span></div></div>"]
    if meta.get("shortfall"):
        out.append(f"<div class=alert>{e(meta['shortfall'])}</div>")
    for i, s in enumerate(rows, 1):
        l = s.listing
        title = e(l.title or l.address or "Untitled listing")
        if l.url:
            title = f"<a href='{e(l.url)}' target=_blank rel=noopener>{title}</a>"
        tags = [f"<span class='tag {s.tier}'>{TIER_LABEL[s.tier]}</span>"]
        if l.extra.get("new"):
            tags.append("<span class='tag new'>NEW</span>")
        tags += [f"<span class=tag>{e(x)}</span>" for x in [
            l.locality or "area ?", _money(l.rent) + "/mo", f"{l.area_sqft or '?'} sqft",
            f"₹{s.rent_psf}/sqft" if s.rent_psf else "", "Outdoor ✓" if l.outdoor else "",
            f"floor: {l.floor}" if l.floor else "", f"posted {l.posted_date}" if l.posted_date else "", f"~{s.orders_per_day_needed} orders/day to cover rent"
            if s.orders_per_day_needed else "", l.source, l.contact] if x]
        items = "".join(f"<li>{e(r)}</li>" for r in s.reasons) + "".join(
            f"<li class=w>{e(w)}</li>" for w in s.warnings)
        out.append(f"<div class=card><div class=top><div><p class=title>#{i} · {title}</p>"
                   f"<div class=tags>{''.join(tags)}</div></div>"
                   f"<div class=score>{s.score}<small>/100</small></div></div><ul>{items}</ul></div>")
    out.append("<h2>Search these daily on your premium accounts</h2><div class=wrap><table>"
               "<tr><th>Area</th><th>Searches</th></tr>")
    for loc, ls in links.items():
        cells = "".join(f"<a href='{e(u)}' target=_blank rel=noopener>{e(p)}</a>" for p, u in ls.items())
        out.append(f"<tr><td>{e(loc)}</td><td>{cells}</td></tr>")
    out.append("</table></div><p class=sub>Orders per day = orders needed at ₹320 average order value to keep "
               "rent at 12% of sales. Below 60 is comfortable for a wok and kebab QSR.</p></main></body></html>")
    path.write_text("".join(out), encoding="utf-8")
