#!/usr/bin/env python3
"""Fetch enrichment data per place: editorial summary, top reviews, rating,
review count, price level, and the candidate photo list.

One Text Search (Enterprise SKU, ~$0.035/call — ~$10 for all 294, covered by
Google's monthly free credit) per place. Raw responses cached in details/ so
re-runs are free. Then --digest condenses everything into digests.tsv for the
blurb-writing pass, and --candidates N downloads alternate photos for places
whose current photo needs replacing.

Usage:
    python3 fetch_enrich.py --limit 3      # smoke test
    python3 fetch_enrich.py                # fetch all (skips cached)
    python3 fetch_enrich.py --digest       # build digests.tsv from cache
    python3 fetch_enrich.py --candidates 3 --only flagged.txt
                                           # download alt photos 2..4 for slugs
                                           # listed in flagged.txt
"""
import csv, json, os, re, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "places-raw.tsv")
DETAILS_DIR = os.path.join(HERE, "details")
CAND_DIR = os.path.join(HERE, "photos_cand")
DIGESTS = os.path.join(HERE, "digests.tsv")
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ("places.id,places.displayName,places.rating,places.userRatingCount,"
          "places.priceLevel,places.editorialSummary,places.reviews,places.photos")


def load_key():
    k = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if k:
        return k
    envf = os.path.join(HERE, ".env")
    if os.path.exists(envf):
        with open(envf, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, val = line.partition("=")
                name = name.strip().lower().replace("-", "_").replace(" ", "")
                if name in ("google_places_api_key", "google_place_api",
                            "google_places_api", "places_api_key", "google_api_key"):
                    return val.strip().strip('"').strip("'")
    return ""


KEY = load_key()


def slug(name, lat, lng):
    """MUST match build.py / fetch_photos.py."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"{s}-{round(lat, 4)}_{round(lng, 4)}"


def city_hint(addr):
    m = re.search(r",\s*([^,]+),\s*[A-Z]{2}\b", addr or "")
    return m.group(1).strip() if m else ""


def post_json(url, payload, headers):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def load_places():
    rows = []
    with open(TSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if not (row.get("name") and row.get("lat")):
                continue
            try:
                lat, lng = float(row["lat"]), float(row["lng"])
            except (ValueError, TypeError):
                continue
            rows.append((row, lat, lng))
    return rows


def fetch_all(limit=None):
    os.makedirs(DETAILS_DIR, exist_ok=True)
    rows = load_places()
    if limit:
        rows = rows[:limit]
    got = skipped = failed = 0
    for i, (row, lat, lng) in enumerate(rows, 1):
        name = row["name"].strip()
        dest = os.path.join(DETAILS_DIR, slug(name, lat, lng) + ".json")
        if os.path.exists(dest):
            skipped += 1
            continue
        body = {"textQuery": f"{name} {city_hint(row.get('address',''))}".strip(),
                "maxResultCount": 1,
                "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng},
                                             "radius": 500.0}}}
        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": KEY,
                   "X-Goog-FieldMask": FIELDS}
        try:
            res = post_json(SEARCH_URL, body, headers)
            place = (res.get("places") or [{}])[0]
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(place, f, ensure_ascii=False)
            got += 1
            print(f"[{i}/{len(rows)}] ok: {name}")
        except Exception as e:  # noqa: BLE001 — keep going
            failed += 1
            msg = e.read()[:150] if isinstance(e, urllib.error.HTTPError) else e
            print(f"[{i}/{len(rows)}] FAIL {name}: {msg}")
        time.sleep(0.12)
    print(f"\nDone. fetched={got} cached={skipped} failed={failed}")


def clean(s, n):
    """One line, no tabs, truncated."""
    s = re.sub(r"\s+", " ", s or "").strip()
    return s[:n]


def digest():
    rows = load_places()
    out = []
    missing = 0
    for row, lat, lng in rows:
        name = row["name"].strip()
        sl = slug(name, lat, lng)
        path = os.path.join(DETAILS_DIR, sl + ".json")
        if not os.path.exists(path):
            missing += 1
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        revs = d.get("reviews") or []
        out.append("\t".join([
            sl, name, clean(row.get("category", ""), 40),
            city_hint(row.get("address", "")),
            str(d.get("rating", "")), str(d.get("userRatingCount", "")),
            clean((d.get("editorialSummary") or {}).get("text", ""), 170),
            clean(((revs[0].get("text") or {}).get("text", "") if len(revs) > 0 else ""), 230),
            clean(((revs[1].get("text") or {}).get("text", "") if len(revs) > 1 else ""), 230),
        ]))
    with open(DIGESTS, "w", encoding="utf-8") as f:
        f.write("slug\tname\tcat\tcity\trating\tcount\tsummary\tr1\tr2\n")
        f.write("\n".join(out) + "\n")
    print(f"Wrote {DIGESTS}: {len(out)} rows ({missing} missing details)")


def candidates(n, only_file=None):
    os.makedirs(CAND_DIR, exist_ok=True)
    want = None
    if only_file:
        with open(only_file, encoding="utf-8") as f:
            want = {l.strip() for l in f if l.strip()}
    rows = load_places()
    got = 0
    for row, lat, lng in rows:
        sl = slug(row["name"].strip(), lat, lng)
        if want is not None and sl not in want:
            continue
        path = os.path.join(DETAILS_DIR, sl + ".json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            photos = json.load(f).get("photos") or []
        for i, ph in enumerate(photos[1:1 + n], start=2):   # skip #1 (already have it)
            dest = os.path.join(CAND_DIR, f"{sl}__{i}.jpg")
            if os.path.exists(dest):
                continue
            url = f"https://places.googleapis.com/v1/{ph['name']}/media?maxWidthPx=800&key={KEY}"
            try:
                with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
                    img = r.read()
                with open(dest, "wb") as f:
                    f.write(img)
                got += 1
            except Exception as e:  # noqa: BLE001
                print(f"cand FAIL {sl} #{i}: {e}")
            time.sleep(0.1)
    print(f"Downloaded {got} candidate photos -> {CAND_DIR}")


if __name__ == "__main__":
    if not KEY:
        sys.exit("ERROR: no Google API key found (env or .env).")
    if "--digest" in sys.argv:
        digest()
    elif "--candidates" in sys.argv:
        n = int(sys.argv[sys.argv.index("--candidates") + 1])
        only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
        candidates(n, only)
    else:
        limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        fetch_all(limit)
