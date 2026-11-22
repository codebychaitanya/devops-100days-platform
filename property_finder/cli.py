"""Usage:
  python -m property_finder run              # collect, score, write today's report
  python -m property_finder add-text FILE    # add a pasted listing (or '-' for stdin)
  python -m property_finder add-url URL      # fetch one public listing page
  python -m property_finder links            # print search links per area
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

from . import collectors, links as links_mod, locate as locate_mod, mailbox, notify, report, scoring
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_run(args, cfg) -> int:
    today = args.date or date.today().isoformat()
    data = Path(args.data)
    store = Store(data / "listings.json")

    print("Collecting listings…")
    found = collectors.load_inbox(data / "inbox", cfg)
    print(f"  inbox files: {len(found)}")
    if not args.offline:
        web = collectors.load_watch_urls(data / "watch_urls.txt", cfg)
        print(f"  watch URLs : {len(web)}")
        found += web
        try:
            found += mailbox.fetch_alert_listings(cfg, since=cfg.get("min_posted_date", today))
        except Exception as e:
            print(f"  ! mailbox: unexpected error, skipped this time: {e}")

    new = store.upsert(found, today)
    new_keys = {l.key for l in new}

    min_posted = cfg.get("min_posted_date", "")
    active = [l for l in store.active(today) if not (min_posted and l.posted_date and l.posted_date < min_posted)]
    for l in active:
        l.extra["new"] = l.key in new_keys or l.first_seen == today
    ranked = scoring.rank(active, cfg)
    top = scoring.shortlist(ranked, cfg)

    if args.locate:
        todo = [s.listing for s in top if locate_mod.needs_locating(s.listing)][: args.locate_limit]
        if todo and not os.environ.get("ANTHROPIC_API_KEY"):
            print("  locate: ANTHROPIC_API_KEY not set, skipping photo analysis")
        elif todo:
            print(f"Estimating locations from photos for {len(todo)} listing(s)…")
            for l in todo:
                try:
                    locate_mod.locate(l)
                except Exception as e:
                    print(f"  ! could not analyse {l.title[:50]!r}: {e}")
            ranked = scoring.rank(active, cfg)   # outdoor space seen in photos can change scores
            top = scoring.shortlist(ranked, cfg)
    matches = sum(1 for s in ranked if s.tier == "match")

    need = cfg.get("min_results", 10)
    shortfall = ""
    if matches < need:
        shortfall = (f"Only {matches} listings meet every requirement today, so the list is topped up with "
                     f"close and stretch options, labelled as such.")
    if len(top) < need:
        shortfall += (f" There are only {len(top)} listings in total. Add more to data/inbox/ (exports or "
                      f"pastes from MagicBricks or NoBroker) or use the search links at the bottom of the report.")

    meta = {"concept": cfg["concept"], "date": today, "total": len(active), "matches": matches,
            "new": len(new_keys), "shortfall": shortfall.strip(),
            "rent_min": cfg["rent"]["min"], "rent_max": cfg["rent"]["max"], "area_min": cfg["area_sqft"]["min"]}

    if args.notify:
        a = cfg.get("alerts", {})
        fresh = [s for s in ranked
                 if not s.listing.extra.get("notified")
                 and s.tier in a.get("tiers", ["match"])
                 and s.score >= a.get("min_score", 60)
                 and not (a.get("skip_if_no_outdoor") and s.listing.outdoor is False)
                 and s.listing.posted_date and s.listing.posted_date >= min_posted]
        if fresh and notify.send(fresh, cfg["concept"]):
            for s in fresh:
                s.listing.extra["notified"] = today
    store.save()

    out = Path(args.reports)
    day_dir = out / today
    day_dir.mkdir(parents=True, exist_ok=True)
    report.write_html(top, meta, links_mod.search_links(cfg), day_dir / "report.html")
    report.write_markdown(top, meta, day_dir / "report.md")
    report.write_csv(ranked, day_dir / "all_ranked.csv")
    for name in ("report.html", "report.md"):
        shutil.copy(day_dir / name, out / f"latest.{name.split('.')[1]}")

    print(f"\n{matches} full matches, {len(new_keys)} new, {len(top)} in shortlist")
    for i, s in enumerate(top, 1):
        l = s.listing
        print(f" {i:>2}. [{s.score:>5}] {s.tier:<7} {l.locality or '?':<11} "
              f"{report._money(l.rent):>9}  {l.area_sqft or '?':>5} sqft  "
              f"{'outdoor' if l.outdoor else '':<7} {(l.title or '')[:45]}")
    print(f"\nReport: {day_dir / 'report.html'}")
    if args.strict and len(top) < need:
        return 2
    return 0


def _save_to_inbox(listing, data: Path):
    path = data / "inbox" / "added.json"
    rows = json.loads(path.read_text()) if path.exists() else []
    rows.append({k: v for k, v in listing.to_dict().items() if v not in (None, "", {})})
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"Added: {listing.locality or '?'} | {report._money(listing.rent)} | {listing.area_sqft or '?'} sqft | "
          f"outdoor={listing.outdoor} | {listing.title[:60]}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="property_finder", description="Chilli Theory shop finder")
    p.add_argument("--config", default=str(ROOT / "config.json"))
    p.add_argument("--data", default=str(ROOT / "data"))
    p.add_argument("--reports", default=str(ROOT / "reports"))
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--date", help="override today's date (YYYY-MM-DD)")
    r.add_argument("--offline", action="store_true", help="skip fetching watch URLs")
    r.add_argument("--locate", action="store_true", help="estimate hidden addresses from listing photos (Claude)")
    r.add_argument("--locate-limit", type=int, default=10, help="max listings to analyse per run")
    r.add_argument("--notify", action="store_true", help="send email/Telegram alerts for new matches")
    r.add_argument("--strict", action="store_true", help="exit 2 if fewer than min_results listings")
    t = sub.add_parser("add-text")
    t.add_argument("file", help="text file with the listing, or - for stdin")
    u = sub.add_parser("add-url")
    u.add_argument("url")
    sub.add_parser("links")
    sub.add_parser("test-notify", help="send a test alert to check email/Telegram setup")
    args = p.parse_args(argv)
    cfg = load_config(Path(args.config))

    if args.cmd == "run":
        return cmd_run(args, cfg)
    if args.cmd == "add-text":
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
        _save_to_inbox(collectors.from_text(text, cfg), Path(args.data))
    elif args.cmd == "add-url":
        _save_to_inbox(collectors.from_url(args.url, cfg), Path(args.data))
    elif args.cmd == "test-notify":
        from .models import Listing
        demo = Listing(title="TEST ALERT: your Chilli Theory property finder is connected", locality="Miyapur",
                       rent=40000, area_sqft=600, outdoor=True, floor="ground")
        sent = notify.send([scoring.score(demo, cfg)], cfg["concept"] + " (test)")
        return 0 if sent else 1
    elif args.cmd == "links":
        for loc, ls in links_mod.search_links(cfg).items():
            print(f"\n{loc}")
            for portal, url in ls.items():
                print(f"  {portal:<17} {url}")
    return 0
