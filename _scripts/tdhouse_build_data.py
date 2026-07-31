#!/usr/bin/env python3
"""Normalize raw scraped listings and write tdhouse/data.json.

Usage: python3 _scripts/tdhouse_build_data.py <raw_listings.json>

- Fixes bed-count parse artifacts (digits glued from adjacent price text).
- Drops anything outside target neighborhoods or over budget
  (base > $3800 with no net-effective <= $3800).
- Carries firstSeen dates over from the existing data.json so the
  dashboard can badge new listings.
"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tdhouse_commute import enrich

TARGET = {"Astoria", "Ditmars-Steinway", "Long Island City", "Hunters Point", "Greenpoint"}
GROUP = {"Ditmars-Steinway": "Astoria", "Hunters Point": "Long Island City"}
OUT = Path(__file__).resolve().parent.parent / "tdhouse" / "data.json"

raw = json.loads(Path(sys.argv[1]).read_text())
today = time.strftime("%Y-%m-%d")

prev_seen = {}
if OUT.exists():
    for l in json.loads(OUT.read_text())["listings"]:
        prev_seen[l["url"] + "|" + l["address"]] = l.get("firstSeen", today)

listings, seen = [], set()
for l in raw:
    if not l.get("url") or not l.get("price"):
        continue
    key = l["url"] + "|" + l["address"]
    if key in seen:
        continue
    seen.add(key)
    beds = l.get("beds") or 1
    if beds > 4:  # glued-digit artifact; trailing digit is the real count
        beds = beds % 10 or 1
    if l.get("hood") not in TARGET:
        continue
    net = l.get("netPrice")
    if l["price"] > 3800 and not (net and net <= 3800):
        continue
    listings.append({
        **l,
        "beds": beds,
        "area": GROUP.get(l["hood"], l["hood"]),
        "firstSeen": prev_seen.get(key, today),
    })

listings = enrich(listings)
listings.sort(key=lambda x: x.get("netPrice") or x["price"])
data = {
    "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "criteria": {
        "maxPrice": 3800,
        "minBeds": 1,
        "amenity": "washer/dryer in unit",
        "areas": ["Astoria", "Long Island City", "Greenpoint"],
        "source": "StreetEasy",
    },
    "count": len(listings),
    "listings": listings,
}
OUT.write_text(json.dumps(data, indent=1))
print(f"wrote {OUT} with {len(listings)} listings, {sum(1 for l in listings if l['firstSeen'] == today)} first seen today")

added = [l for l in listings if (l["url"] + "|" + l["address"]) not in prev_seen]
if prev_seen and added:
    print(f"NEW_THIS_RUN {len(added)}")
    for l in added:
        p = l.get("netPrice") or l["price"]
        print(f"NEW: {l['address']} ({l['hood']}) ${p:,}")
