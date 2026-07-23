#!/usr/bin/env python3
"""
stats.py — distribution of thread sizes (page counts) across topics.csv,
plus a thread-count-per-category breakdown.

Buckets threads into ranges (default: <10, <50, <100, <500, <1000,
<5000, >=5000 pages) so you can see at a glance how many threads are
small vs. how much of the total work is a handful of enormous ones.
Also shows how many threads exist in each category.

USAGE:
    python3 stats.py
    python3 stats.py --category-id 59
    python3 stats.py --csv topics.csv --buckets 10,50,100,500,1000,5000
    python3 stats.py --sort-by name        # sort the per-category table
"""

import csv
import argparse
from collections import defaultdict


def print_bucket_stats(rows, bounds, args):
    unknown = 0
    known_pages = []
    for r in rows:
        tp = (r.get("total_pages") or "").strip()
        if tp:
            known_pages.append(int(tp))
        else:
            unknown += 1

    bucket_counts = [0] * (len(bounds) + 1)
    bucket_sums = [0] * (len(bounds) + 1)
    for p in known_pages:
        placed = False
        for i, b in enumerate(bounds):
            if p < b:
                bucket_counts[i] += 1
                bucket_sums[i] += p
                placed = True
                break
        if not placed:
            bucket_counts[-1] += 1
            bucket_sums[-1] += p

    total_threads = len(rows)
    total_known = len(known_pages)
    total_pages_sum = sum(known_pages)

    scope = f"category {args.category_id}" if args.category_id else "all categories"
    print(f"Stats for {scope} ({args.csv})")
    print(f"Threads: {total_threads}  (total_pages known: {total_known}, pending: {unknown})")
    print()
    print("-- Page-count distribution --")
    print(f"{'Range':<15}{'Threads':>10}{'% of known':>12}{'Total pages':>14}")
    prev = 0
    for i, b in enumerate(bounds):
        label = f"{prev}-{b - 1}"
        count = bucket_counts[i]
        pct = (count / total_known * 100) if total_known else 0
        print(f"{label:<15}{count:>10}{pct:>11.1f}%{bucket_sums[i]:>14}")
        prev = b
    label = f"{bounds[-1]}+"
    count = bucket_counts[-1]
    pct = (count / total_known * 100) if total_known else 0
    print(f"{label:<15}{count:>10}{pct:>11.1f}%{bucket_sums[-1]:>14}")
    print("-" * 51)
    print(f"{'TOTAL known':<15}{total_known:>10}{'100.0%':>12}{total_pages_sum:>14}")

    if unknown:
        print(f"\n{unknown} threads still have no total_pages — run "
              f"`python3 1_discover.py --fill-page-counts {args.csv}` to fill them "
              f"in first if you want complete stats.")


def print_category_counts(rows, sort_by):
    by_cat = defaultdict(lambda: {"name": "", "count": 0})
    for r in rows:
        c = by_cat[r["category_id"]]
        c["name"] = r["category_name"]
        c["count"] += 1

    items = list(by_cat.items())
    if sort_by == "name":
        items.sort(key=lambda kv: kv[1]["name"])
    elif sort_by == "id":
        items.sort(key=lambda kv: int(kv[0]))
    else:  # count, descending
        items.sort(key=lambda kv: kv[1]["count"], reverse=True)

    print()
    print("-- Threads per category --")
    print(f"{'ID':>6}  {'Category':<30}{'Threads':>10}")
    total = 0
    for cid, c in items:
        print(f"{cid:>6}  {c['name'][:30]:<30}{c['count']:>10}")
        total += c["count"]
    print("-" * 48)
    print(f"{'TOTAL':>6}  {'':<30}{total:>10}  ({len(items)} categories)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="topics.csv")
    ap.add_argument("--category-id", help="Only show stats for this category")
    ap.add_argument("--buckets", default="10,50,100,500,1000,5000",
                     help="Comma-separated ascending upper bounds, e.g. 10,50,100,500")
    ap.add_argument("--sort-by", choices=["count", "id", "name"], default="count",
                     help="How to sort the per-category thread-count table (default: count, descending)")
    args = ap.parse_args()

    bounds = [int(b) for b in args.buckets.split(",")]

    with open(args.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.category_id:
        rows = [r for r in rows if r["category_id"] == str(args.category_id)]

    if not rows:
        print("No rows matched.")
        return

    print_bucket_stats(rows, bounds, args)

    if not args.category_id:  # a per-category table doesn't make sense once already filtered to one
        print_category_counts(rows, args.sort_by)


if __name__ == "__main__":
    main()

