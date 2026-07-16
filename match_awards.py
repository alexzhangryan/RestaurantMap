#!/usr/bin/env python3
"""Match places against researched Michelin/Infatuation/Beli award lists and
write specific badge text into featured.tsv.

Consumes structured JSON built by a separate research pass (WebSearch/WebFetch
— Michelin/Infatuation/Beli have no API, so that gathering step needs an
agent's judgment and is done elsewhere; this script is the deterministic
second half: match + merge). Expected schema, one file per source under
awards_cache/ (region MUST be exactly "LA / SoCal" or "Bay Area" — the same
two buckets build.py uses):

  michelin.json:     [{"name": str, "region": str, "award": "1 star"|"2 star"|
                        "3 star"|"bib gourmand"}]
  infatuation.json:  [{"name": str, "region": str, "list_title": str,
                        "rank": int|null}]
  beli.json:         [{"name": str, "region": str, "list_title": str,
                        "rank": int|null}]

Matching requires BOTH a name match (word-token subset, case/punctuation-
insensitive) AND a region match — this is the same two-factor guard used by
hand in earlier sessions to avoid false positives (e.g. "Cos" inside
"Tacos"). Anything that name-matches but fails the region check, or matches
ambiguously (multiple places, same region), is logged to awards_review.log
and NOT applied — no badge beats a wrong badge. A slug with no automated
match this run keeps whatever it already had in featured.tsv rather than
being wiped, so a transient miss (or a source page that failed to fetch)
can't regress already-verified data.

Usage:
    python3 match_awards.py                    # match against all places in places-raw.tsv
    python3 match_awards.py --only new_slugs.txt  # restrict to specific slugs (daily sync)
"""
import csv, json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "places-raw.tsv")
CACHE_DIR = os.path.join(HERE, "awards_cache")
FEATURED = os.path.join(HERE, "featured.tsv")
REVIEW_LOG = os.path.join(HERE, "awards_review.log")

SOURCES = ["michelin", "infatuation", "beli"]
STARS = {"1 star": "★", "2 star": "★★", "3 star": "★★★"}


def slug(name, lat, lng):
    """MUST match build.py / fetch_enrich.py / apply_photo_pick.py's inputs."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"{s}-{round(lat, 4)}_{round(lng, 4)}"


def region_of(lat):
    return "Bay Area" if lat > 36.5 else "LA / SoCal"


def norm_tokens(name):
    """Strip accents (Matu == Matū, Melisse == Mélisse) before tokenizing,
    so ASCII-typed source names still match names with diacritics."""
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return set(re.sub(r"[^a-z0-9]+", " ", stripped.lower()).split())


def names_match(a_tokens, b_tokens):
    """Word-token subset match, exact-equality-only for single-token names
    (guards against short/common words false-positiving, e.g. a lone
    "Union" matching inside an unrelated multi-word name)."""
    if not a_tokens or not b_tokens:
        return False
    smaller, larger = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    if len(smaller) == 1:
        return smaller == larger
    return smaller.issubset(larger)


def load_places(only_slugs=None):
    out = []
    with open(TSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if not row.get("name") or not row.get("lat"):
                continue
            try:
                lat, lng = float(row["lat"]), float(row["lng"])
            except (ValueError, TypeError):
                continue
            name = row["name"].strip()
            sl = slug(name, lat, lng)
            if only_slugs is not None and sl not in only_slugs:
                continue
            out.append({"slug": sl, "name": name, "region": region_of(lat),
                        "tokens": norm_tokens(name)})
    return out


def load_cache():
    cache = {}
    for src in SOURCES:
        path = os.path.join(CACHE_DIR, f"{src}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cache[src] = json.load(f)
        else:
            cache[src] = []
    return cache


def badge_text(src, entry):
    if src == "michelin":
        award = entry["award"]
        return f"Michelin {STARS[award]}" if award in STARS else "Michelin Bib Gourmand"
    if src == "infatuation":
        base = f"Infatuation {entry['list_title']}"
        return f"{base} — #{entry['rank']}" if entry.get("rank") else base
    if src == "beli":
        rank = entry.get("rank")
        return f"Beli — #{rank} {entry['list_title']}" if rank else f"Beli — {entry['list_title']}"
    raise ValueError(src)


def match_all(places, cache, log):
    # (slug, source) -> badge string. Keyed per-source (not just per-slug) so
    # the merge step can tell "this source found nothing this run" apart from
    # "this source confirmed there's nothing" — see main().
    hits = {}
    for src in SOURCES:
        for entry in cache[src]:
            e_tokens = norm_tokens(entry["name"])
            region_matches = [p for p in places if p["region"] == entry["region"]
                               and names_match(e_tokens, p["tokens"])]
            name_only_matches = [p for p in places if p["region"] != entry["region"]
                                  and names_match(e_tokens, p["tokens"])]
            for p in name_only_matches:
                log.append(f"NAME-ONLY (region mismatch): {src} '{entry['name']}' "
                           f"({entry['region']}) ~ '{p['name']}' ({p['region']}) — skipped")
            if len(region_matches) > 1:
                names = ", ".join(f"{p['name']} [{p['slug']}]" for p in region_matches)
                log.append(f"AMBIGUOUS: {src} '{entry['name']}' ({entry['region']}) "
                           f"matched {len(region_matches)} places: {names} — skipped")
                continue
            if len(region_matches) == 1:
                hits[(region_matches[0]["slug"], src)] = badge_text(src, entry)
    return hits


def classify_clause(clause):
    """Which source an existing free-text featured.tsv clause belongs to,
    by its leading word — matches the convention badge_text() writes in."""
    for src, prefix in (("michelin", "Michelin"), ("infatuation", "Infatuation"),
                         ("beli", "Beli")):
        if clause.strip().lower().startswith(prefix.lower()):
            return src
    return "other"


def load_featured():
    if not os.path.exists(FEATURED):
        return {}
    with open(FEATURED, newline="", encoding="utf-8") as f:
        return {row["slug"]: row["feat"] for row in csv.DictReader(f, delimiter="\t")}


def write_featured(feat_by_slug):
    with open(FEATURED, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["slug", "feat"])
        for sl in sorted(feat_by_slug):
            if feat_by_slug[sl]:
                w.writerow([sl, feat_by_slug[sl]])


def main():
    only = None
    if "--only" in sys.argv:
        with open(sys.argv[sys.argv.index("--only") + 1], encoding="utf-8") as f:
            only = {l.strip() for l in f if l.strip()}

    places = load_places(only)
    cache = load_cache()
    log = []
    hits = match_all(places, cache, log)
    touched_slugs = {sl for sl, _ in hits}

    existing = load_featured()
    merged = dict(existing)
    upgraded = added = 0
    for sl in touched_slugs:
        # start from whatever this slug already had, split by source, so a
        # fresh match for ONE source (say Infatuation) can't silently erase
        # an already-verified claim from another source (say Michelin) that
        # this run's cache simply didn't happen to re-confirm.
        old_by_src = {}
        if sl in existing:
            for clause in existing[sl].split("; "):
                old_by_src.setdefault(classify_clause(clause), []).append(clause)
        parts = []
        for src in SOURCES:
            fresh = hits.get((sl, src))
            if fresh:
                parts.append(fresh)
            else:
                parts.extend(old_by_src.get(src, []))
        parts.extend(old_by_src.get("other", []))
        text = "; ".join(parts)
        if sl in existing and existing[sl] != text:
            upgraded += 1
        elif sl not in existing:
            added += 1
        merged[sl] = text
    write_featured(merged)

    if log:
        with open(REVIEW_LOG, "a", encoding="utf-8") as f:
            f.write("\n".join(log) + "\n")

    print(f"Matched {len(touched_slugs)}/{len(places)} places checked.")
    print(f"featured.tsv: +{added} new, {upgraded} upgraded, "
          f"{len(merged) - added - upgraded} unchanged (total {len(merged)}).")
    if log:
        print(f"{len(log)} near-misses logged to {REVIEW_LOG} (not applied).")


if __name__ == "__main__":
    main()
