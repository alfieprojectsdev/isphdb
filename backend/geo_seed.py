#!/usr/bin/env python3
"""Dev-only seed script. Refreshes frontend/src/lib/hop-geo.json from a public geo API
using the distinct mappable hop IPs already captured in traceroute_hops.

NOT part of the daemon: prober.py never imports or calls this. Run it by hand whenever the
route changes and you want fresh coordinates:

    cd backend && uv run geo_seed.py            # read hops from the DB
    cd backend && uv run geo_seed.py 161.49.4.6 # or seed specific IPs

Geolocation uses ip-api.com (free, no key, ~45 req/min). Entries are keyed by /16 so
per-run host variance within a block resolves via prefix match in geo.mjs.
"""
import ipaddress
import json
import os
import sqlite3
import sys
import time
import urllib.request

DB_PATH = os.path.join(os.path.dirname(__file__), "network_metrics.db")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "lib", "hop-geo.json")
API = "http://ip-api.com/json/{ip}?fields=status,lat,lon,isp,city,country"


def distinct_hop_ips():
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT DISTINCT hop_ip FROM traceroute_hops WHERE hop_ip IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def geolocate(ip):
    with urllib.request.urlopen(API.format(ip=ip), timeout=5) as resp:
        data = json.load(resp)
    if data.get("status") != "success":
        return None
    return data


def block_key(ip):
    """Group by the containing /16 so nearby hops share one curated entry."""
    net = ipaddress.ip_network(f"{ip}/16", strict=False)
    return str(net)


def main(argv):
    ips = argv[1:] or distinct_hop_ips()
    if not ips:
        print("No hop IPs to seed (run the prober first or pass IPs as arguments).")
        return 1

    table = {
        "_comment": "Curated IP/CIDR -> {lat, lon, label} for the stable public hops on "
                    "this connection's route. CIDR keys are matched by prefix. "
                    "Regenerate with backend/geo_seed.py."
    }
    for ip in ips:
        try:
            geo = geolocate(ip)
        except Exception as e:
            print(f"  {ip}: lookup failed ({e})")
            continue
        if not geo:
            print(f"  {ip}: not geolocatable, skipping")
            continue
        key = block_key(ip)
        label = " — ".join(p for p in (geo.get("isp"), geo.get("city")) if p) or ip
        table[key] = {"lat": geo["lat"], "lon": geo["lon"], "label": label}
        print(f"  {ip} -> {key}: {label} ({geo['lat']}, {geo['lon']})")
        time.sleep(1.5)  # stay under the free-tier rate limit

    with open(OUT_PATH, "w") as f:
        json.dump(table, f, indent=2)
        f.write("\n")
    print(f"Wrote {len([k for k in table if not k.startswith('_')])} entries to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
