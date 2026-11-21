import json
import shutil
import tempfile
import unittest
from pathlib import Path

from datetime import date

from property_finder import cli, collectors, mailbox, notify, scoring
from property_finder.parse import parse_area, parse_money, parse_posted_date

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())


class ParseTests(unittest.TestCase):
    def test_money(self):
        self.assertEqual(parse_money("₹ 35,000"), 35000)
        self.assertEqual(parse_money("45k"), 45000)
        self.assertEqual(parse_money("0.55 lakh"), 55000)
        self.assertEqual(parse_money("1.2 Lac"), 120000)

    def test_area(self):
        self.assertEqual(parse_area("650 sq. ft"), 650)
        self.assertEqual(parse_area("60 sq m"), 646)
        self.assertEqual(parse_area("100 sq yd"), 900)

    def test_text_listing(self):
        l = collectors.from_text("Shop in Miapur, rent 40k per month, 600 sft ground floor with sit out", CFG)
        self.assertEqual((l.locality, l.rent, l.area_sqft, l.floor, l.outdoor), ("Miyapur", 40000, 600, "ground", True))


class DateAndAlertTests(unittest.TestCase):
    def test_posted_dates(self):
        today = date(2026, 11, 21)
        self.assertEqual(parse_posted_date("Posted on 18 Nov 2026", today), "2026-11-18")
        self.assertEqual(parse_posted_date("Nov 19", today), "2026-11-19")
        self.assertEqual(parse_posted_date("19/11/2026", today), "2026-11-19")
        self.assertEqual(parse_posted_date("3 days ago", today), "2026-11-18")
        self.assertEqual(parse_posted_date("yesterday", today), "2026-11-20")
        self.assertEqual(parse_posted_date("2 hours ago", today), "2026-11-21")

    def test_alert_email_parsing(self):
        html = """<table><tr><td><a href="https://www.magicbricks.com/propertyDetails/shop-for-rent-Miyapur&id=4d4234567">
        Shop for rent in Miyapur</a><br>Rent: Rs 40,000 | 620 sqft | Ground floor | front open space</td></tr>
        <tr><td><a href="https://www.magicbricks.com/unsubscribe">Unsubscribe</a></td></tr></table>"""
        ls = mailbox.listings_from_email(html, CFG, "2026-11-20", "magicbricks")
        self.assertEqual(len(ls), 1)
        l = ls[0]
        self.assertEqual((l.locality, l.rent, l.area_sqft, l.outdoor, l.posted_date),
                         ("Miyapur", 40000, 620, True, "2026-11-20"))

    def test_old_listings_filtered_and_alerts_once(self):
        work = Path(tempfile.mkdtemp())
        (work / "data" / "inbox").mkdir(parents=True)
        (work / "data" / "inbox" / "x.csv").write_text(
            "Title,Locality,Rent,Area,Floor,Description,Posted on,URL\n"
            "New shop,Miyapur,40000,650,Ground,main road with sit out,19 Nov 2026,https://e.com/1\n"
            "Old shop,KPHB,40000,650,Ground,main road with sit out,10 Nov 2026,https://e.com/2\n")
        sent = []
        orig = notify.send
        notify.send = lambda m, c, log=print: sent.append([s.listing.title for s in m]) or 1
        try:
            args = ["--data", str(work / "data"), "--reports", str(work / "reports"), "run", "--offline", "--notify"]
            cli.main(args + ["--date", "2026-11-21"])
            cli.main(args + ["--date", "2026-11-21"])
        finally:
            notify.send = orig
        self.assertEqual(sent, [["New shop"]])   # old one filtered out; no repeat alert
        csv_text = (work / "reports" / "2026-11-21" / "all_ranked.csv").read_text()
        self.assertNotIn("Old shop", csv_text)


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.inbox = Path(tempfile.mkdtemp())
        for f in (ROOT / "examples").iterdir():
            shutil.copy(f, self.inbox)
        self.listings = collectors.load_inbox(self.inbox, CFG)

    def test_tiers(self):
        tiers = {l.title: scoring.score(l, CFG).tier for l in self.listings}
        self.assertEqual(tiers["EXAMPLE Ground floor shop on main road"], "match")
        self.assertEqual(tiers["EXAMPLE Small shop"], "stretch")
        self.assertEqual(tiers["EXAMPLE Commercial shop Chandanagar near bus stop"], "close")

    def test_floor_column_is_normalised(self):
        floors = {l.title: l.floor for l in self.listings}
        self.assertEqual(floors["EXAMPLE Ground floor shop on main road"], "ground")
        self.assertEqual(floors["EXAMPLE Commercial space 1st floor"], "1")

    def test_outdoor_ground_floor_beats_upper_floor(self):
        ranked = scoring.rank(self.listings, CFG)
        titles = [s.listing.title for s in ranked]
        self.assertLess(titles.index("EXAMPLE Ground floor shop on main road"),
                        titles.index("EXAMPLE Commercial space 1st floor"))

    def test_shortlist_tops_up_to_minimum(self):
        cfg = dict(CFG, min_results=6)
        top = scoring.shortlist(scoring.rank(self.listings, cfg), cfg)
        self.assertEqual(len(top), 6)
        self.assertEqual(top[0].tier, "match")

    def test_full_run_writes_reports(self):
        work = Path(tempfile.mkdtemp())
        shutil.copytree(self.inbox, work / "data" / "inbox")
        rc = cli.main(["--data", str(work / "data"), "--reports", str(work / "reports"),
                       "run", "--offline", "--date", "2026-11-21"])
        self.assertEqual(rc, 0)
        self.assertTrue((work / "reports" / "2026-11-21" / "report.html").exists())
        self.assertTrue((work / "reports" / "latest.md").exists())


if __name__ == "__main__":
    unittest.main()
