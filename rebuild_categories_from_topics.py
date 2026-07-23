#!/usr/bin/env python3
"""
One-off recovery: if categories.csv got wiped (e.g. by a run that hit a
temporary block and found 0 categories), rebuild a usable version from
the category_id/category_name pairs already sitting in topics.csv.

This won't have category_slug or url — those aren't needed by
2_extract_category.py or 3_wayback_submit.py (they only match on
category_id/category_name), but ARE needed if 1_discover.py later
needs to find brand-new threads in that category. Once a normal
discovery run succeeds again, it'll overwrite this with the full
version including slug/url.

USAGE:
    python3 rebuild_categories_from_topics.py
"""
import csv

with open("topics.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

seen = {}
for r in rows:
    cid = r["category_id"]
    if cid not in seen:
        seen[cid] = {
            "category_id": cid,
            "category_name": r["category_name"],
            "category_slug": "",
            "url": "",
        }

with open("categories.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["category_id", "category_name", "category_slug", "url"])
    w.writeheader()
    w.writerows(seen.values())

print(f"Rebuilt categories.csv with {len(seen)} categories (slug/url left blank).")
