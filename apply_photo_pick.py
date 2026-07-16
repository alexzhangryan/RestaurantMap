#!/usr/bin/env python3
"""Apply a chosen food-photo candidate as a place's cover photo + gallery.

Fills a gap the repo never actually closed: fetch_enrich.py --candidates
downloads alternates to photos_cand/{slug}__{2..N+1}.jpg, but nothing
copied a chosen one into photos/{slug}.jpg — that step was done by hand.
This automates it (e.g. driven by an agent's vision judgment on new places):
the chosen candidate becomes the cover photo, and every other downloaded
candidate for that slug becomes an extra gallery image.

Usage:
    python3 apply_photo_pick.py --slug soowon-galbi-34.0564_-118.2914 --pick 4
    python3 apply_photo_pick.py --picks picks.tsv
                                # picks.tsv: two columns, slug<TAB>chosen_index
"""
import csv, glob, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAND_DIR = os.path.join(HERE, "photos_cand")
PHOTO_DIR = os.path.join(HERE, "photos")
GALLERY_DIR = os.path.join(HERE, "gallery")


def apply_pick(slug, chosen):
    cand_paths = sorted(
        glob.glob(os.path.join(CAND_DIR, f"{slug}__*.jpg")),
        key=lambda p: int(re.search(r"__(\d+)\.jpg$", p).group(1)),
    )
    if not cand_paths:
        print(f"SKIP {slug}: no candidates downloaded")
        return False
    chosen_path = os.path.join(CAND_DIR, f"{slug}__{chosen}.jpg")
    if not os.path.exists(chosen_path):
        print(f"SKIP {slug}: chosen candidate #{chosen} not found")
        return False

    os.makedirs(PHOTO_DIR, exist_ok=True)
    os.makedirs(GALLERY_DIR, exist_ok=True)
    shutil.copyfile(chosen_path, os.path.join(PHOTO_DIR, f"{slug}.jpg"))

    # every other downloaded candidate becomes an extra gallery shot,
    # renumbered contiguously starting at 2 (gallery_for() in build.py scans
    # gallery/{slug}-{2..11}.jpg, so numbering must have no gaps)
    extras = [p for p in cand_paths if p != chosen_path]
    for i, p in enumerate(extras, start=2):
        shutil.copyfile(p, os.path.join(GALLERY_DIR, f"{slug}-{i}.jpg"))

    print(f"OK {slug}: cover=#{chosen}, {len(extras)} gallery extras")
    return True


def load_picks(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [(row[0].strip(), int(row[1].strip()))
                for row in csv.reader(f, delimiter="\t") if row and row[0].strip()]


if __name__ == "__main__":
    if "--picks" in sys.argv:
        picks = load_picks(sys.argv[sys.argv.index("--picks") + 1])
    elif "--slug" in sys.argv and "--pick" in sys.argv:
        picks = [(sys.argv[sys.argv.index("--slug") + 1],
                  int(sys.argv[sys.argv.index("--pick") + 1]))]
    else:
        sys.exit("Usage: apply_photo_pick.py --slug SLUG --pick N | --picks picks.tsv")

    ok = sum(apply_pick(s, n) for s, n in picks)
    print(f"\nApplied {ok}/{len(picks)} picks.")
