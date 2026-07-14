#!/usr/bin/env python3
"""Build quad pick-sheets: for each Eat place, show candidate photos #2-#5
(from photos_cand/) as a 2x2 quad. 8 places per page, sized so one 800x400
screenshot captures a full page. Reviewer picks the best FOOD shot per place
(position TL=2, TR=3, BL=4, BR=5); apply_picks.py then swaps it in.
"""
import csv, os, glob, html

HERE = os.path.dirname(os.path.abspath(__file__))
eat = [l.strip() for l in open(os.path.join(HERE, "eat_slugs.txt")) if l.strip()]
names = {r["slug"]: r["name"] for r in csv.DictReader(open(os.path.join(HERE, "digests.tsv")), delimiter="\t")}

for f in glob.glob(os.path.join(HERE, "sheets", "pick*.html")):
    os.remove(f)

PER = 8   # 4 quads x 2 rows
pages = 0
skipped = []
items = []
for i, slug in enumerate(eat, 1):
    cands = [n for n in (2, 3, 4, 5)
             if os.path.exists(os.path.join(HERE, "photos_cand", f"{slug}__{n}.jpg"))]
    if not cands:
        skipped.append(slug)
        continue
    items.append((i, slug, cands))

for start in range(0, len(items), PER):
    chunk = items[start:start+PER]
    quads = []
    for i, slug, cands in chunk:
        cells = "".join(
            f'<img src="../photos_cand/{slug}__{n}.jpg">' if n in cands
            else '<div class="x">–</div>'
            for n in (2, 3, 4, 5))
        quads.append(f'<div class="q"><div class="qq">{cells}</div>'
                     f'<div class="l"><b>{i}</b> {html.escape(names.get(slug, slug)[:18])}</div></div>')
    pages += 1
    with open(os.path.join(HERE, "sheets", f"pick{pages:02}.html"), "w") as f:
        f.write(f'''<!doctype html><meta charset="utf-8">
<style>body{{margin:0;background:#111;font:10px sans-serif;color:#eee;width:795px}}
.g{{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;padding:3px}}
.qq{{display:grid;grid-template-columns:1fr 1fr;gap:2px}}
.qq img,.x{{width:100%;height:82px;object-fit:cover;display:block}}
.x{{display:flex;align-items:center;justify-content:center;background:#222;color:#555}}
.l{{padding:1px 3px;background:#222;white-space:nowrap;overflow:hidden}} b{{color:#ffd54a;font-size:12px}}
</style><div class="g">{"".join(quads)}</div>''')

print(f"{pages} pick sheets ({len(items)} places, {len(skipped)} with no candidates)")
if skipped:
    print("no candidates:", ", ".join(skipped[:10]), "..." if len(skipped) > 10 else "")
