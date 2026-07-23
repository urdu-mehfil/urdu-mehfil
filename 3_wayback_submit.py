#!/usr/bin/env python3
"""
Submit thread URLs to the Internet Archive's Wayback Machine
(web.archive.org) so there's a permanent, publicly-hosted backup
independent of your own GitHub repo.

This version expands each thread into ALL of its pages using the
total_pages column from topics.csv (produced by 1_discover.py), so a
51-page thread submits 51 URLs, not just the first page.

Setup (free):
    1. Sign up at https://archive.org
    2. Get S3-style keys at https://archive.org/account/s3.php
    3. export SAVEPAGENOW_ACCESS_KEY=...
       export SAVEPAGENOW_SECRET_KEY=...

USAGE:
    pip install savepagenow
    python3 3_wayback_submit.py --category "بزم سخن"
    python3 3_wayback_submit.py --category-id 59
    python3 3_wayback_submit.py --all              # every thread in topics.csv

Authenticated requests are rate-limited by archive.org to roughly
6 captures/minute — this script paces itself accordingly. For a
whole category (let alone the whole forum) this can add up to a lot
of URLs, since it's now one submission per PAGE, not per thread —
expect this to take a while for anything beyond a small category.
"""

import csv
import time
import argparse
import os
from urllib.parse import urljoin

import savepagenow


def page_url_for(base_url: str, page_num: int) -> str:
    return base_url if page_num == 1 else urljoin(base_url, f"page-{page_num}")


def expand_to_page_urls(row) -> list:
    total_pages = int(row["total_pages"]) if row.get("total_pages") else 1
    return [page_url_for(row["url"], p) for p in range(1, total_pages + 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category")
    ap.add_argument("--category-id")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    authenticated = bool(os.environ.get("SAVEPAGENOW_ACCESS_KEY"))
    if not authenticated:
        print("WARNING: no SAVEPAGENOW_ACCESS_KEY set — running unauthenticated, "
              "which is slower and less reliable. See script docstring.")

    with open("topics.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.all:
        selected = rows
    elif args.category_id:
        selected = [r for r in rows if r["category_id"] == str(args.category_id)]
    elif args.category:
        selected = [r for r in rows if r["category_name"] == args.category]
    else:
        raise SystemExit("Pass --category, --category-id, or --all")

    if not selected:
        raise SystemExit("No matching topics found. Check categories.csv for exact names/ids.")

    all_urls = []
    for r in selected:
        all_urls.extend(expand_to_page_urls(r))

    print(f"{len(selected)} threads -> {len(all_urls)} total page URLs to submit")

    for i, url in enumerate(all_urls, 1):
        try:
            archived_url, captured = savepagenow.capture_or_cache(url, authenticate=authenticated)
            print(f"[{i}/{len(all_urls)}] {url} -> {archived_url}")
        except Exception as e:
            print(f"[{i}/{len(all_urls)}] FAILED {url}: {e}")
        time.sleep(10 if authenticated else 20)  # stay comfortably under ~6/min


if __name__ == "__main__":
    main()
