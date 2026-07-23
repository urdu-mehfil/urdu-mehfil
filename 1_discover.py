#!/usr/bin/env python3
"""
Stage 1: Discover categories (subforums) and topics (threads) on
urduweb.org/mehfil.

Two modes:

  1. DISCOVERY (default) — crawl category/thread listings and write
     categories.csv + topics.csv. Use --no-page-counts for a fast
     pass that leaves total_pages blank.

  2. FILL PAGE COUNTS (--fill-page-counts) — go back through an
     existing topics.csv and fill in total_pages for whatever rows
     don't have it yet. Resumable: progress is saved to the CSV
     itself as it goes, so if you stop it (Ctrl+C, crash, whatever)
     and re-run the same command, it picks up where it left off —
     rows that already have total_pages are simply skipped.

URL structure (confirmed against a live thread page):
    Category:        /mehfil/forums/<slug>.<id>/
    Thread, page 1:  /mehfil/threads/<slug>.<id>/
    Thread, page N:  /mehfil/threads/<slug>.<id>/page-N
A thread's page-1 HTML has a pagination link with title="Last" (and/or
text like "30 از 51") that gives the total page count directly.

USAGE:
    pip install requests beautifulsoup4 lxml

    # normal discovery
    python3 1_discover.py
    python3 1_discover.py --no-page-counts

    # check where you stand, no network calls
    python3 1_discover.py --fill-page-counts topics.csv --progress

    # backfill everything still missing
    python3 1_discover.py --fill-page-counts topics.csv

    # backfill just one category (see categories.csv for ids)
    python3 1_discover.py --fill-page-counts topics.csv --category-id 59

    # backfill/fix a single thread
    python3 1_discover.py --fill-page-counts topics.csv --thread-id 2080
"""

import csv
import os
import re
import sys
import time
import random
import argparse
from collections import defaultdict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.urduweb.org/mehfil/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-archive/1.0; contact: YOUR-EMAIL-HERE)"}

FORUM_RE = re.compile(r"/mehfil/forums/([^/\"]+)\.(\d+)/?$")
THREAD_RE = re.compile(r"/mehfil/threads/([^/\"]+)\.(\d+)/")
PAGE_NUM_RE = re.compile(r"/page-(\d+)")
OF_TOTAL_RE = re.compile(r"(\d+)\s*از\s*(\d+)")  # Urdu "X of Y"

TOPICS_FIELDS = ["category_id", "category_name", "thread_id", "thread_title",
                  "thread_slug", "url", "total_pages"]

session = requests.Session()
session.headers.update(HEADERS)


def get(url, retries=3):
    """GET with polite delay + automatic retry on transient failures
    (timeouts, connection resets, 5xx, etc). Raises the last error if
    all retries are exhausted, so callers can still decide to skip."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            time.sleep(1.5 + random.random())
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_exc = e
            if attempt < retries:
                wait = 5 * attempt
                print(f"    ! request failed ({e}) — retry {attempt}/{retries} in {wait}s")
                time.sleep(wait)
    raise last_exc


def canonical_thread_url(slug: str, tid: str) -> str:
    return urljoin(BASE, f"threads/{slug}.{tid}/")


def get_total_pages(thread_url: str) -> int:
    """Fetch a thread's page 1 and read off its total page count."""
    try:
        html = get(thread_url)
    except requests.HTTPError:
        return 1
    soup = BeautifulSoup(html, "lxml")

    last_link = soup.find("a", title="Last")
    if last_link and last_link.get("href"):
        m = PAGE_NUM_RE.search(last_link["href"])
        if m:
            return int(m.group(1))

    m = OF_TOTAL_RE.search(soup.get_text())
    if m:
        return int(m.group(2))

    return 1  # no pagination nav -> single-page thread


# ---------------------------------------------------------------- discovery

def discover_categories():
    html = get(BASE)
    soup = BeautifulSoup(html, "lxml")
    cats = {}
    for a in soup.find_all("a", href=True):
        m = FORUM_RE.search(a["href"])
        if m:
            slug, fid = m.groups()
            name = a.get_text(strip=True)
            if name and fid not in cats:
                cats[fid] = {
                    "category_id": fid,
                    "category_name": name,
                    "category_slug": slug,
                    "url": urljoin(BASE, a["href"]),
                }

    if not cats:
        # Save what we actually got so it's possible to tell whether this
        # was a block/CAPTCHA/rate-limit page vs. a real site change.
        debug_path = "debug_homepage.html"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(html)
        snippet = re.sub(r"\s+", " ", soup.get_text())[:200]
        print(f"  ! Got 0 categories from the homepage. Saved raw response to "
              f"{debug_path} ({len(html)} bytes) for inspection.")
        print(f"  ! Page text snippet: {snippet!r}")
        for marker in ["captcha", "cloudflare", "just a moment", "attention required",
                       "access denied", "too many requests", "rate limit"]:
            if marker in html.lower():
                print(f"  ! Response body contains '{marker}' — looks like a block/challenge page, "
                      f"not the real homepage. Try again later, or slow down further.")
                break

    return list(cats.values())


def discover_topics_for_category(cat, max_pages=None):
    topics = {}
    page = 1
    url = cat["url"]
    while True:
        page_url = url if page == 1 else urljoin(url, f"page-{page}")
        try:
            html = get(page_url)
        except requests.HTTPError:
            break
        soup = BeautifulSoup(html, "lxml")
        found_this_page = 0
        for a in soup.find_all("a", href=True):
            m = THREAD_RE.search(a["href"])
            if m:
                slug, tid = m.groups()
                if tid not in topics:
                    name = a.get_text(strip=True)
                    if name:
                        topics[tid] = {
                            "category_id": cat["category_id"],
                            "category_name": cat["category_name"],
                            "thread_id": tid,
                            "thread_title": name,
                            "thread_slug": slug,
                            "url": canonical_thread_url(slug, tid),
                        }
                        found_this_page += 1
        if found_this_page == 0:
            break
        page += 1
        if max_pages and page > max_pages:
            break
    return list(topics.values())


def run_discovery(max_pages_per_category, no_page_counts, topics_path="topics.csv"):
    print("Discovering categories...")
    categories = discover_categories()

    categories_path = "categories.csv"
    existing_categories = []
    if os.path.exists(categories_path):
        with open(categories_path, encoding="utf-8") as f:
            existing_categories = list(csv.DictReader(f))

    if not categories:
        if existing_categories:
            print(f"Found 0 categories this run, but {categories_path} already has "
                  f"{len(existing_categories)} from before — keeping the existing file "
                  f"untouched rather than overwriting it with an empty one.")
            print("This is almost always a temporary block/rate-limit, not a real site "
                  "change. Wait a while and try again; see debug_homepage.html meanwhile.")
            categories = existing_categories
        else:
            raise SystemExit(
                f"Found 0 categories and there's no existing {categories_path} to fall "
                f"back on. Check debug_homepage.html (just saved) and your network access "
                f"before re-running."
            )
    else:
        with open(categories_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["category_id", "category_name", "category_slug", "url"])
            w.writeheader()
            w.writerows(categories)
        print(f"Found {len(categories)} categories -> {categories_path}")

    # Resume support: if topics.csv already exists (e.g. a previous run
    # crashed partway through), don't re-discover categories it already
    # has rows for. Coarse-grained (whole category, not per-thread) but
    # cheap and means a crash never throws away completed categories.
    all_topics = []
    done_category_ids = set()
    if os.path.exists(topics_path):
        with open(topics_path, encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))
        all_topics.extend(existing_rows)
        done_category_ids = {r["category_id"] for r in existing_rows}
        if done_category_ids:
            print(f"Found existing {topics_path} with {len(existing_rows)} rows across "
                  f"{len(done_category_ids)} categories already done — skipping those, resuming the rest.")

    for cat in categories:
        if cat["category_id"] in done_category_ids:
            continue

        print(f"Discovering topics in: {cat['category_name']}")
        try:
            topics = discover_topics_for_category(cat, max_pages=max_pages_per_category)
        except Exception as e:
            print(f"  ! FAILED to discover this category ({e}) — skipping for now, "
                  f"re-run the same command later to retry it.")
            continue
        print(f"  -> {len(topics)} threads")

        if not no_page_counts:
            for i, t in enumerate(topics, 1):
                try:
                    t["total_pages"] = get_total_pages(t["url"])
                except Exception as e:
                    print(f"    ! couldn't get page count for thread {t['thread_id']} ({e}) — leaving blank")
                    t["total_pages"] = ""
                if i % 25 == 0:
                    print(f"    ...page counts: {i}/{len(topics)}")
        else:
            for t in topics:
                t["total_pages"] = ""

        all_topics.extend(topics)

        # Save after EVERY category, not just at the end — this is the
        # actual fix for "crashed and topics.csv was never written".
        write_topics_csv_atomic(topics_path, all_topics, TOPICS_FIELDS)
        print(f"  saved ({len(all_topics)} total rows so far) -> {topics_path}")

    print(f"Done. {len(all_topics)} total threads -> {topics_path}")


# --------------------------------------------------------- fill page counts

def read_topics_csv(path):
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or TOPICS_FIELDS
    if "total_pages" not in fieldnames:
        fieldnames = fieldnames + ["total_pages"]
        for r in rows:
            r["total_pages"] = ""
    return rows, fieldnames


def write_topics_csv_atomic(path, rows, fieldnames):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp_path, path)  # atomic on POSIX — avoids a corrupt file if interrupted mid-write


def print_progress_report(rows):
    by_cat = defaultdict(lambda: {"name": "", "total": 0, "done": 0})
    for r in rows:
        c = by_cat[r["category_id"]]
        c["name"] = r["category_name"]
        c["total"] += 1
        if r.get("total_pages", "").strip():
            c["done"] += 1

    print(f"{'ID':>6}  {'Category':<30} {'Done':>7} / {'Total':<7}")
    grand_total, grand_done = 0, 0
    for cid, c in sorted(by_cat.items(), key=lambda kv: int(kv[0])):
        print(f"{cid:>6}  {c['name'][:30]:<30} {c['done']:>7} / {c['total']:<7}")
        grand_total += c["total"]
        grand_done += c["done"]
    print("-" * 60)
    print(f"{'TOTAL':>6}  {'':<30} {grand_done:>7} / {grand_total:<7}"
          f"  ({grand_done/grand_total*100:.1f}%)" if grand_total else "No rows found.")


def fill_page_counts(csv_path, category_id=None, thread_id=None, save_every=20, progress_only=False):
    rows, fieldnames = read_topics_csv(csv_path)

    if progress_only:
        print_progress_report(rows)
        return

    targets = []
    for r in rows:
        if category_id and r["category_id"] != str(category_id):
            continue
        if thread_id and r["thread_id"] != str(thread_id):
            continue
        if not r.get("total_pages", "").strip():
            targets.append(r)

    if not targets:
        print("Nothing to do — every matching row already has total_pages. "
              "Use --progress to see the full breakdown.")
        return

    print(f"{len(targets)} row(s) need total_pages. Filling in, saving every {save_every}...")
    print("(Ctrl+C any time — progress made so far is saved before exit.)")

    processed = 0
    try:
        for row in targets:
            row["total_pages"] = str(get_total_pages(row["url"]))
            processed += 1
            if processed % save_every == 0:
                write_topics_csv_atomic(csv_path, rows, fieldnames)
                print(f"  ...{processed}/{len(targets)} done, saved.")
    except KeyboardInterrupt:
        print("\nInterrupted — saving progress...")
    finally:
        write_topics_csv_atomic(csv_path, rows, fieldnames)
        print(f"Saved. {processed}/{len(targets)} filled in this run.")


# ---------------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages-per-category", type=int, default=None,
                     help="[discovery mode] Cap listing pages per category (quick test run)")
    ap.add_argument("--no-page-counts", action="store_true",
                     help="[discovery mode] Skip per-thread page-count lookup during discovery")

    ap.add_argument("--fill-page-counts", metavar="TOPICS_CSV",
                     help="Switch to fill mode: backfill total_pages in an existing topics.csv")
    ap.add_argument("--category-id", help="[fill mode] Only process this category")
    ap.add_argument("--thread-id", help="[fill mode] Only process this single thread")
    ap.add_argument("--save-every", type=int, default=20,
                     help="[fill mode] Write progress to disk every N threads (default 20)")
    ap.add_argument("--progress", action="store_true",
                     help="[fill mode] Just report done/remaining per category, no network calls")

    args = ap.parse_args()

    if args.fill_page_counts:
        fill_page_counts(
            args.fill_page_counts,
            category_id=args.category_id,
            thread_id=args.thread_id,
            save_every=args.save_every,
            progress_only=args.progress,
        )
    else:
        run_discovery(args.max_pages_per_category, args.no_page_counts)


if __name__ == "__main__":
    main()
