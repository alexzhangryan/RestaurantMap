#!/usr/bin/env python3
"""Montage JPEGs for photo picking (browser-free review).

Each montage: 8 places (4 cols x 2 rows). Each place is a 2x2 quad of its
candidate photos — TL=#2, TR=#3, BL=#4, BR=#5 — labeled with its index+name.
"""
import csv, os, glob
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "montages")
os.makedirs(OUT, exist_ok=True)
for f in glob.glob(os.path.join(OUT, "m*.jpg")):
    os.remove(f)

eat = [l.strip() for l in open(os.path.join(HERE, "eat_slugs.txt")) if l.strip()]
names = {r["slug"]: r["name"] for r in csv.DictReader(
    open(os.path.join(HERE, "digests.tsv")), delimiter="\t")}

TW, TH = 170, 128          # thumb size
GAP, LBL = 4, 26           # gap inside quad, label height
CW = TW*2 + GAP            # cell width  (344)
CH = TH*2 + GAP + LBL      # cell height (286)
COLS, ROWS = 4, 2
PAD = 6

try:
    font = ImageFont.load_default(size=17)
except TypeError:
    font = ImageFont.load_default()

items = []
for i, slug in enumerate(eat, 1):
    cands = [n for n in (2, 3, 4, 5)
             if os.path.exists(os.path.join(HERE, "photos_cand", f"{slug}__{n}.jpg"))]
    if cands:
        items.append((i, slug, cands))

PER = COLS*ROWS
pages = 0
for start in range(0, len(items), PER):
    chunk = items[start:start+PER]
    W = COLS*CW + (COLS+1)*PAD
    H = ROWS*CH + (ROWS+1)*PAD
    canvas = Image.new("RGB", (W, H), (16, 16, 18))
    d = ImageDraw.Draw(canvas)
    for k, (i, slug, cands) in enumerate(chunk):
        cx = PAD + (k % COLS) * (CW + PAD)
        cy = PAD + (k // COLS) * (CH + PAD)
        for n in (2, 3, 4, 5):
            px = cx + (0 if n in (2, 4) else TW + GAP)
            py = cy + (0 if n in (2, 3) else TH + GAP)
            p = os.path.join(HERE, "photos_cand", f"{slug}__{n}.jpg")
            if os.path.exists(p):
                try:
                    im = Image.open(p).convert("RGB")
                    # center-crop to thumb aspect then resize
                    ar, tar = im.width/im.height, TW/TH
                    if ar > tar:
                        w = int(im.height*tar); x0 = (im.width-w)//2
                        im = im.crop((x0, 0, x0+w, im.height))
                    else:
                        h = int(im.width/tar); y0 = (im.height-h)//2
                        im = im.crop((0, y0, im.width, y0+h))
                    canvas.paste(im.resize((TW, TH)), (px, py))
                except Exception:
                    d.rectangle([px, py, px+TW, py+TH], fill=(40, 20, 20))
            else:
                d.rectangle([px, py, px+TW, py+TH], fill=(34, 34, 36))
        ly = cy + 2*TH + GAP + 3
        d.text((cx+2, ly), str(i), fill=(255, 213, 74), font=font)
        d.text((cx+2 + 14*len(str(i)), ly), " " + names.get(slug, slug)[:30],
               fill=(230, 230, 230), font=font)
    pages += 1
    canvas.save(os.path.join(OUT, f"m{pages:02}.jpg"), quality=82)

print(f"{pages} montages of up to {PER} places -> montages/  ({len(items)} places)")
