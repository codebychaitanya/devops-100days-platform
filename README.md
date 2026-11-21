# Chilli Theory: shop finder

Finds and ranks rental shops for **Chilli Theory, a wok and kebab QSR**, and produces a daily
shortlist of at least 10 options.

| Requirement | Setting |
|---|---|
| Areas | Narsingi, Miyapur, KPHB, Kukatpally |
| Recommended high-yield areas | Nizampet, Bachupally, Chandanagar, Kondapur, Manikonda |
| Rent | ₹20,000 to ₹60,000 a month (sweet spot ₹25k to ₹45k) |
| Size | 500 sqft or more (ideal 500 to 900) |
| Outdoor or sit-out space | Preferred, worth 15 points |

All of these settings live in `config.json`.

## How it works

```
data/inbox/*.csv|json|txt ─┐
data/watch_urls.txt ───────┼─▶ de-duplicate + history ─▶ score /100 ─▶ shortlist (≥10) ─▶ reports/
added via add-text/add-url ┘      (data/listings.json)
```

**Score out of 100**

| Factor | Points |
|---|---|
| Rent fit | 20 |
| Size fit | 15 |
| Outdoor space | 15 |
| Location (target or recommended area) | 15 |
| Visibility (ground floor, main road or corner, near metro, college or IT park) | 15 |
| Kitchen readiness (exhaust, gas, water, 3-phase power, previously a restaurant) | 10 |
| Value (rent per sqft compared with the area's usual rate) | 10 |
| Red flags (basement, "veg only", "no cooking", …) | minus points |

**Profit check.** For each listing the report shows the orders per day needed, at ₹320 average order
value, to keep rent at 12% of sales. Under about 60 orders a day is comfortable for a QSR.
You can change these assumptions at the top of `property_finder/scoring.py`.

**Getting to at least 10.** Shops that meet every requirement come first, labelled *Full match*. If there
are fewer than 10, the list is filled with *Close* options (within about 10% of a limit, or missing one
detail) and then *Stretch* options. Every listing is labelled with its tier, so the report never passes
off a weaker option as a full match.

## Daily use

1. In your MagicBricks and NoBroker premium accounts, search the areas (run `python -m property_finder links`
   for ready-made searches). Then do one or more of the following:
   - export or copy the results into a CSV in `data/inbox/`. Column names are flexible: Title, Locality,
     Rent, Area, Floor, Description, URL, Contact.
   - paste listing text, or broker WhatsApp messages, into a `.txt` file in `data/inbox/`, with a line
     containing only `---` between listings.
   - add listing URLs to `data/watch_urls.txt`.
2. Run the search:
   ```bash
   python -m property_finder run          # writes reports/YYYY-MM-DD/ and reports/latest.html
   ```
3. Open `reports/latest.html`. `reports/YYYY-MM-DD/all_ranked.csv` has every listing for Excel.

Quick adds:
```bash
python -m property_finder add-text listing.txt
python -m property_finder add-url "https://…"
```

**Automatic daily run.** `.github/workflows/daily-property-search.yml` runs every day at 08:47 IST and
commits the new report to the repo. Once this branch is merged to the default branch, it can also be
run by hand from the Actions tab.

No installs are needed: plain Python 3.10 or newer. Run the tests with `python -m unittest discover -s tests`.
Files in `examples/` are made-up sample data for the tests and are never used in real reports.

## About your premium accounts

Don't put MagicBricks or NoBroker passwords into this repo or any automated job. Logging in from a bot
breaks both sites' terms of use and can get the paid accounts blocked. Use the accounts the way they're
meant to be used: their saved searches and alerts, contact unlocks and exports. Then pass the results to
this tool through `data/inbox/`.
