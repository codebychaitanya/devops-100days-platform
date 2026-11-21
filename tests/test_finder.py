import json
import shutil
import tempfile
import unittest
from pathlib import Path

from property_finder import cli, collectors, scoring
from property_finder.parse import parse_area, parse_money

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
