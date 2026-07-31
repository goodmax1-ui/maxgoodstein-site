#!/usr/bin/env python3
"""Commute enrichment for tdhouse listings.

Anchors: CUNY Law (2 Court Square), 120 Broadway (FiDi), 40 St-Lowery (Sunnyside).
Times are estimated off-peak subway minutes from each nearby station to each
anchor (ride + transfers + destination walk). Listing total = walk to station
+ 4 min avg platform wait + station time.

Geocoding via NYC Planning GeoSearch (free, no key), cached in
_scripts/tdhouse_geocache.json.
"""
import json, math, time, urllib.parse, urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "tdhouse_geocache.json"

# lat, lon, (to CUNY Law/Court Sq, to 120 Broadway, to 40 St-Lowery)
STATIONS = {
    "Astoria-Ditmars Blvd (N/W)":   (40.7752, -73.9124, (20, 40, 24)),
    "Astoria Blvd (N/W)":           (40.7700, -73.9179, (18, 38, 22)),
    "30 Av (N/W)":                  (40.7666, -73.9214, (16, 36, 20)),
    "Broadway (N/W)":               (40.7617, -73.9251, (14, 34, 18)),
    "36 Av (N/W)":                  (40.7566, -73.9299, (12, 32, 16)),
    "39 Av-Dutch Kills (N/W)":      (40.7527, -73.9328, (10, 30, 14)),
    "Queensboro Plaza (N/W/7)":     (40.7508, -73.9401, (4, 28, 6)),
    "Queens Plaza (E/M/R)":         (40.7489, -73.9370, (5, 22, 10)),
    "Court Sq (E/M/G/7)":           (40.7472, -73.9455, (2, 22, 8)),
    "21 St-Queensbridge (F)":       (40.7544, -73.9425, (12, 35, 16)),
    "Hunters Point Av (7)":         (40.7423, -73.9489, (5, 30, 10)),
    "Vernon Blvd-Jackson Av (7)":   (40.7426, -73.9535, (7, 30, 12)),
    "21 St (G)":                    (40.7440, -73.9497, (4, 28, 14)),
    "Greenpoint Av (G)":            (40.7313, -73.9542, (9, 38, 17)),
    "Nassau Av (G)":                (40.7245, -73.9514, (11, 40, 19)),
}
# fallback station per area when geocoding fails
FALLBACK = {
    "Astoria": "Broadway (N/W)",
    "Long Island City": "Court Sq (E/M/G/7)",
    "Greenpoint": "Greenpoint Av (G)",
}
WALK_M_PER_MIN = 80
PLATFORM_WAIT = 4


def _dist_m(lat1, lon1, lat2, lon2):
    dx = (lon2 - lon1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * 110540
    return math.hypot(dx, dy)


def _load_cache():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def _geocode(address, hood, cache):
    boro = "Brooklyn" if hood == "Greenpoint" else "Queens"
    # strip unit ("#4B") — GeoSearch wants just the street address
    street = address.split("#")[0].strip()
    key = f"{street}, {boro}"
    if key in cache:
        return cache[key], cache
    q = urllib.parse.quote(f"{street}, {boro}, NY")
    url = f"https://geosearch.planninglabs.nyc/v2/search?text={q}&size=1"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            feats = json.load(r).get("features", [])
        coord = feats[0]["geometry"]["coordinates"] if feats else None  # [lon, lat]
    except Exception:
        coord = None
    cache[key] = coord
    time.sleep(0.3)
    return coord, cache


def enrich(listings):
    cache = _load_cache()
    for l in listings:
        coord, cache = _geocode(l["address"], l.get("area") or l.get("hood"), cache)
        if coord:
            lon, lat = coord
            name, (slat, slon, times) = min(
                STATIONS.items(), key=lambda s: _dist_m(lat, lon, s[1][0], s[1][1])
            )
            walk = max(1, round(_dist_m(lat, lon, slat, slon) / WALK_M_PER_MIN))
            approx = False
        else:
            name = FALLBACK.get(l.get("area"), "Court Sq (E/M/G/7)")
            slat, slon, times = STATIONS[name]
            walk = 6
            approx = True
        base = walk + PLATFORM_WAIT
        l["commute"] = {
            "station": name,
            "walk": walk,
            "law": base + times[0],
            "fidi": base + times[1],
            "sunnyside": base + times[2],
            "approx": approx,
        }
    CACHE.write_text(json.dumps(cache, indent=1))
    return listings
