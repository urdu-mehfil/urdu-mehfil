#!/usr/bin/env python3
"""
build_indexes.py — regenerates the browsable listing pages:

    archive/categories/index.html          — every category with any
                                              archived threads, + counts
    archive/categories/<category>/index.html — every archived thread
                                                in that category

Both are rebuilt by scanning the FILESYSTEM (which thread folders
actually have an index.html on disk), not by trusting "what this run
just did" — so a resumed/partial extraction run still produces a
correct, complete listing that includes everything archived so far,
not just what changed this session.

The landing page (archive/index.html) is NOT touched by this script —
that one is standalone and hand-maintained (holds the Pagefind search
UI), since it doesn't depend on how much has been archived.

USAGE:
    # after an extraction run, rebuild just that category + the top-level list
    python3 build_indexes.py --category-id 59

    # or rebuild everything from topics.csv, e.g. after moving files around
    python3 build_indexes.py --all
"""

import csv
import argparse
from pathlib import Path

from extract_common import safe_dirname, sanitize_category_dir_name

CATEGORY_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{category_name}</title>
<link rel="stylesheet" href="../../assets/style.css">
</head>
<body data-pagefind-ignore>
<h1>{category_name}</h1>
<p class="meta">ابھی تک {count} موضوع محفوظ ہوئے ہیں</p>
<ul>
{links}
</ul>
<p><a href="../index.html">&laquo; تمام زمرے دیکھیں</a></p>
</body>
</html>
"""

CATEGORIES_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All categories</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body data-pagefind-ignore>
<h1>زمرہجات</h1>
<ul>
{links}
</ul>
<p><a href="../index.html">&laquo; واپس</a></p>
</body>
</html>
"""


def rebuild_category_index(cat_rows, category_name: str, out_root: Path):
    """cat_rows: topics.csv rows belonging to ONE category."""
    cat_dir_name = sanitize_category_dir_name(category_name)
    cat_dir = out_root / "categories" / cat_dir_name
    cat_dir.mkdir(parents=True, exist_ok=True)

    items = []
    for r in cat_rows:
        dir_name = safe_dirname(r["thread_title"], r["thread_id"])
        if (cat_dir / dir_name / "index.html").exists():
            items.append((dir_name, r["thread_title"]))

    items.sort(key=lambda x: x[1])
    links = "\n".join(f'  <li><a href="{d}/index.html">{t}</a></li>' for d, t in items)

    html = CATEGORY_INDEX_TEMPLATE.format(
        category_name=category_name, count=len(items), links=links
    )
    (cat_dir / "index.html").write_text(html, encoding="utf-8")
    return len(items)


def rebuild_categories_index(all_rows, out_root: Path):
    """all_rows: every row in topics.csv (all categories)."""
    cats = {}
    for r in all_rows:
        cid = r["category_id"]
        if cid not in cats:
            cats[cid] = r["category_name"]

    entries = []
    for cid, name in cats.items():
        cat_dir_name = sanitize_category_dir_name(name)
        cat_dir = out_root / "categories" / cat_dir_name
        count = len(list(cat_dir.glob("*/index.html"))) if cat_dir.exists() else 0
        if count > 0:  # only list categories that actually have something archived
            entries.append((cat_dir_name, name, count))

    entries.sort(key=lambda e: e[1])
    links = "\n".join(
        f'  <li><a href="{d}/index.html">{n}</a> ({c} موضوع{"ات" if c != 1 else ""})</li>'
        for d, n, c in entries
    )

    out_dir = out_root / "categories"
    out_dir.mkdir(parents=True, exist_ok=True)
    html = CATEGORIES_INDEX_TEMPLATE.format(links=links)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    return len(entries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category-id", help="Only rebuild this category's index (plus the top-level list)")
    ap.add_argument("--all", action="store_true", help="Rebuild every category's index + the top-level list")
    ap.add_argument("--topics-csv", default="topics.csv")
    ap.add_argument("--out", default="archive")
    args = ap.parse_args()

    if not args.category_id and not args.all:
        raise SystemExit("Pass --category-id ID or --all")

    with open(args.topics_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_root = Path(args.out)

    if args.all:
        by_cat = {}
        for r in rows:
            by_cat.setdefault(r["category_id"], []).append(r)
        for cid, cat_rows in by_cat.items():
            n = rebuild_category_index(cat_rows, cat_rows[0]["category_name"], out_root)
            print(f"  {cat_rows[0]['category_name']}: {n} threads")
    else:
        cat_rows = [r for r in rows if r["category_id"] == str(args.category_id)]
        if not cat_rows:
            raise SystemExit(f"No rows found for category_id={args.category_id}")
        n = rebuild_category_index(cat_rows, cat_rows[0]["category_name"], out_root)
        print(f"  {cat_rows[0]['category_name']}: {n} threads")

    n_cats = rebuild_categories_index(rows, out_root)
    print(f"Rebuilt categories/index.html — {n_cats} categories listed")


if __name__ == "__main__":
    main()
