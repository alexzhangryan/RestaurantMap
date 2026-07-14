#!/usr/bin/env python3
"""Fetch one food/place photo per restaurant into photos/  (run locally, then commit).

Uses the Google Places API (New). Your API key is read from the environment so it
NEVER lands in the repo or the deployed site — the photos are downloaded once here,
committed as plain .jpg files, and served statically. The live map needs no key.

Setup (one time):
  1. Google Cloud console -> enable "Places API (New)" -> create an API key.
  2. Run:
        export GOOGLE_PLACES_API_KEY="your-key-here"
        python3 fetch_photos.py            # all places (skips ones already cached)
        python3 fetch_photos.py --limit 10 # just try 10 first
        python3 fetch_photos.py --force    # re-fetch even if cached
  3. python3 build.py    (picks up photos/ automatically)
  4. Commit photos/ and push.

Cost: ~250 Text Search + Photo calls, comfortably inside Google's $200/mo free credit.
"""
import csv, json, os, re, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "places-raw.tsv")
PHOTO_DIR = os.path.join(HERE, "photos")
KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()

MAX_WIDTH = 800          # px; plenty for a phone card, keeps files small
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


def slug(name, lat, lng):
    """MUST match build.py's slug()."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"{s}-{round(lat, 4)}_{round(lng, 4)}"


def post_json(url, payload, headers):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def find_photo_name(name, city_hint, lat, lng):
    """Return the first photo resource name for this place, or None."""
    body = {
        "textQuery": f"{name} {city_hint}".strip(),
        "maxResultCount": 1,
        "locationBias": {"circle": {
            "center": {"latitude": lat, "longitude": lng}, "radius": 500.0}},
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": KEY,
        "X-Goog-FieldMask": "places.photos,places.displayName",
    }
    res = post_json(SEARCH_URL, body, headers)
    places = res.get("places") or []
    if not places:
        return None
    photos = places[0].get("photos") or []
    return photos[0]["name"] if photos else None   # e.g. "places/ABC/photos/XYZ"


def download_photo(photo_name, dest):
    url = (f"https://places.googleapis.com/v1/{photo_name}/media"
           f"?maxWidthPx={MAX_WIDTH}&key={KEY}")
    req = urllib.request.Request(url)                # follows redirect to the image
    with urllib.request.urlopen(req, timeout=30) as r:
        img = r.read()
    with open(dest, "wb") as f:
        f.write(img)


def city_hint(addr):
    m = re.search(r",\s*([^,]+),\s*[A-Z]{2}\b", addr or "")
    return m.group(1).strip() if m else ""


def main():
    if not KEY:
        sys.exit("ERROR: set GOOGLE_PLACES_API_KEY in your environment first "
                 "(see the header of this file).")
    force = "--force" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    os.makedirs(PHOTO_DIR, exist_ok=True)
    rows = []
    with open(TSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("name") and row.get("lat"):
                rows.append(row)
    if limit:
        rows = rows[:limit]

    got = skipped = missed = failed = 0
    for i, row in enumerate(rows, 1):
        name = row["name"].strip()
        try:
            lat, lng = float(row["lat"]), float(row["lng"])
        except (ValueError, TypeError):
            continue
        dest = os.path.join(PHOTO_DIR, slug(name, lat, lng) + ".jpg")
        if os.path.exists(dest) and not force:
            skipped += 1
            continue
        try:
            pname = find_photo_name(name, city_hint(row.get("address", "")), lat, lng)
            if not pname:
                missed += 1
                print(f"[{i}/{len(rows)}] no photo: {name}")
                continue
            download_photo(pname, dest)
            got += 1
            print(f"[{i}/{len(rows)}] ok: {name}")
        except urllib.error.HTTPError as e:
            failed += 1
            print(f"[{i}/{len(rows)}] HTTP {e.code} for {name}: {e.read()[:200]!r}")
        except Exception as e:                       # noqa: BLE001 — keep going
            failed += 1
            print(f"[{i}/{len(rows)}] error for {name}: {e}")
        time.sleep(0.12)                             # be polite to the API

    print(f"\nDone. downloaded={got} cached={skipped} no-photo={missed} failed={failed}")
    print("Next: python3 build.py  &&  commit photos/  &&  push.")


if __name__ == "__main__":
    main()
