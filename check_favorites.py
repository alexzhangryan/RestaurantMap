#!/usr/bin/env python3
"""Detect new/removed places in the Apple Maps Favorites share list and sync
places-raw.tsv (plus any dependent per-place files) to match.

IMPORTANT — this needs a real browser, not a plain HTTP fetch. The share
page's HTML only server-renders the first ~20 places as real
<a class="mw-place-link"> anchors; the rest ship as inert
<div class="mw-place-holder"> placeholders that client-side JS hydrates
after load (confirmed via curl vs. a live browser session — a bare GET
returns 294 DOM-hydration placeholders but only 20 populated ones). The
client also has no plain-HTTP-friendly API: hydration goes through
maps.apple.com/data/place, an undocumented, session-bound internal
endpoint not meant for direct calls.

So the actual flow is two steps:
  1. A browser-capable step (e.g. the Claude Browser tool) navigates to
     SHARE_URL, waits for hydration (all 294 anchors appear within a couple
     seconds of load, no scrolling needed — verified), and runs EXTRACT_JS
     below to pull every place into a JSON array, which gets written to a
     file (see --live-json).
  2. This script (pure stdlib, no browser needed) reads that JSON and does
     the actual diff/sync against places-raw.tsv.

EXTRACT_JS (run via the browser tool's JS executor, result is the live list):
    Array.from(document.querySelectorAll('a.mw-place-link')).map(a => {
      const qs = new URL(a.href).searchParams;
      const cat = a.querySelector('.mw-place-category .mw-value');
      const price = a.querySelector('.mw-place-price-range .mw-value');
      return {
        name: qs.get('name') || '',
        address: qs.get('address') || '',
        coordinate: qs.get('coordinate') || '',
        category: cat ? cat.textContent.trim() : '',
        price: price ? price.textContent.trim() : '',
      };
    })

Usage:
    python3 check_favorites.py --live-json live.json
                                             # sync places-raw.tsv from the
                                             # browser-extracted JSON, print a summary
    python3 check_favorites.py --live-json live.json --dry-run
                                             # report only, touch nothing
    python3 check_favorites.py --live-json live.json --new-out new_slugs.txt
                                             # also write newly-added slugs, one per
                                             # line, for fetch_enrich.py --only /
                                             # --candidates and match_awards.py
"""
import csv, json, glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "places-raw.tsv")
FIELDS = ["name", "category", "price", "lat", "lng", "address"]
DEP_TSVS = ["enrich.tsv", "digests.tsv", "featured.tsv"]
DEP_GLOBS = [("photos", "{}.jpg"), ("gallery", "{}-*.jpg"),
             ("details", "{}.json"), ("photos_cand", "{}__*.jpg")]


def slug(name, lat, lng):
    """MUST match build.py / fetch_enrich.py / fetch_photos.py."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"{s}-{round(lat, 4)}_{round(lng, 4)}"


def load_live(live_json_path):
    with open(live_json_path, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for p in raw:
        name = (p.get("name") or "").strip()
        coord = p.get("coordinate") or ""
        if not name or "," not in coord:
            continue
        try:
            lat, lng = (float(x) for x in coord.split(",", 1))
        except ValueError:
            continue
        out.append({
            "name": name,
            "category": (p.get("category") or "").strip(),
            "price": (p.get("price") or "").strip(),
            "lat": f"{lat}", "lng": f"{lng}",
            "address": (p.get("address") or "").strip(),
        })
    return out


def load_existing():
    if not os.path.exists(TSV):
        return []
    with open(TSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(rows):
    with open(TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def remove_slug_everywhere(sl):
    for fn in DEP_TSVS:
        path = os.path.join(HERE, fn)
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            fieldnames = reader.fieldnames
            rows = [r for r in reader if r.get("slug") != sl]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            w.writeheader()
            w.writerows(rows)
    for d, pattern in DEP_GLOBS:
        for path in glob.glob(os.path.join(HERE, d, pattern.format(sl))):
            os.remove(path)


def main():
    if "--live-json" not in sys.argv:
        sys.exit("ERROR: --live-json PATH is required (see module docstring for how to "
                  "produce it via the browser tool's EXTRACT_JS).")
    live_json_path = sys.argv[sys.argv.index("--live-json") + 1]
    dry = "--dry-run" in sys.argv
    new_out = sys.argv[sys.argv.index("--new-out") + 1] if "--new-out" in sys.argv else None

    live = load_live(live_json_path)
    live_by_slug = {slug(p["name"], float(p["lat"]), float(p["lng"])): p for p in live}

    existing = load_existing()
    existing_by_slug = {}
    for r in existing:
        try:
            lat, lng = float(r["lat"]), float(r["lng"])
        except (ValueError, TypeError, KeyError):
            continue
        existing_by_slug[slug(r["name"].strip(), lat, lng)] = r

    new_slugs = [s for s in live_by_slug if s not in existing_by_slug]
    removed_slugs = [s for s in existing_by_slug if s not in live_by_slug]

    print(f"Live favorites: {len(live_by_slug)}  |  tracked: {len(existing_by_slug)}")
    print(f"+{len(new_slugs)} new, -{len(removed_slugs)} removed")
    for s in new_slugs:
        print(f"  NEW: {live_by_slug[s]['name']}")
    for s in removed_slugs:
        print(f"  REMOVED: {existing_by_slug[s]['name']}")

    if new_out:
        with open(new_out, "w", encoding="utf-8") as f:
            f.write("\n".join(new_slugs) + ("\n" if new_slugs else ""))

    if dry or (not new_slugs and not removed_slugs):
        return

    kept = [r for r in existing
            if slug(r["name"].strip(), float(r["lat"]), float(r["lng"])) not in removed_slugs]
    kept.extend(live_by_slug[s] for s in new_slugs)
    write_tsv(kept)

    for s in removed_slugs:
        remove_slug_everywhere(s)

    print(f"\nSynced {TSV} ({len(kept)} rows).")


if __name__ == "__main__":
    main()
