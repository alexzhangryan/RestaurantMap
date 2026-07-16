#!/usr/bin/env python3
"""Build a single-file, phone-friendly map (index.html) from places-raw.tsv.

Re-run this whenever the data changes (e.g. after adding known-for / why notes):
    python3 build.py
"""
import csv, json, re, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "places-raw.tsv")
OUT = os.path.join(HERE, "index.html")
VENDOR = os.path.join(HERE, "vendor")

def vendor(name):
    """Read a vendored library file to inline into the single-file build."""
    with open(os.path.join(VENDOR, name), encoding="utf-8") as fh:
        return fh.read()

LEAFLET_CSS = vendor("leaflet.css")
CLUSTER_CSS = vendor("MarkerCluster.css")
MAPLIBRE_CSS = vendor("maplibre-gl.css")
LEAFLET_JS = vendor("leaflet.js")
CLUSTER_JS = vendor("leaflet.markercluster.js")
MAPLIBRE_JS = vendor("maplibre-gl.js")
MAPLIBRE_LEAFLET_JS = vendor("maplibre-gl-leaflet.js")

# ---- classification ---------------------------------------------------------
FOOD_RE = re.compile(
    r"Restaurant|Cuisine|Bakery|Cafe|Coffee|Ice Cream|Dessert|Sushi|Ramen|Pizza|"
    r"\bBar\b|Tea|Gelato|Donut|Dim Sum|Hot Pot|Udon|Noodle|Poke|Taco|Burger|"
    r"Steakhouse|Bistro|Izakaya|Patisserie|Pastry|Confectionery|Food|Dumpling|"
    r"Waffle|Sandwich|Deli|Creamery|Smoothie|Boulangerie|Cake|Milk Bar|Soul Food|"
    r"Kopitiam|Snow Shop|Shaved Ice", re.I)
SEE_RE = re.compile(
    r"Museum|Garden|Historic|Community|Art Studio|Hotel|Internet Cafe|"
    r"Sporting Goods|Farmers Market", re.I)

# emoji by category, first match wins
EMOJI = [
    (r"Handroll|Temaki|Sushi|Conveyor", "🍣"),
    (r"Ramen|Udon|Noodle", "🍜"),
    (r"Neapolitan|Pizza", "🍕"),
    (r"Donut", "🍩"),
    (r"Bakery|Pastry|Patisserie|Boulangerie|Confectionery|Cake|Waffle|Bread", "🥐"),
    (r"Ice Cream|Gelato|Frozen Yogurt|Creamery|Shaved Ice|Snow Shop", "🍦"),
    (r"Bubble Tea|Tea Room|Tea", "🧋"),
    (r"Coffee|Internet Cafe", "☕"),
    (r"Dim Sum|Dumpling", "🥟"),
    (r"Hot Pot", "🍲"),
    (r"Korean BBQ|BBQ", "🍖"),
    (r"Steakhouse", "🥩"),
    (r"Seafood|Oyster", "🦪"),
    (r"Taco|Mexican", "🌮"),
    (r"Burger", "🍔"),
    (r"Poke|Hawaiian", "🐟"),
    (r"Vietnamese", "🥖"),
    (r"Indian|Pakistani", "🍛"),
    (r"Greek|Mediterranean|Middle Eastern", "🥙"),
    (r"Thai", "🍜"),
    (r"Korean", "🍲"),
    (r"Japanese|Izakaya", "🍱"),
    (r"Chinese|Cantonese|Szechuan|Taiwanese|Asian", "🥢"),
    (r"Italian", "🍝"),
    (r"French|Bistro", "🍷"),
    (r"Soul Food", "🍗"),
    (r"Peruvian", "🐟"),
    (r"Malaysian|Singapore", "🍜"),
    (r"Sandwich|Deli", "🥪"),
    (r"Juice|Smoothie", "🥤"),
    (r"Farmers Market|Street Food", "🧺"),
    (r"American|Bar", "🍽️"),
    (r"Dessert|Confection", "🍰"),
    (r"Cafe|Food Court", "☕"),
    # non-food
    (r"Museum|Historic", "🏛️"),
    (r"Garden", "🌿"),
    (r"Hotel", "🏨"),
    (r"Art Studio", "🎨"),
    (r"Sporting Goods", "🏓"),
    (r"Community", "📍"),
    (r"Shoe|Skate|Sportswear|Outdoor", "👟"),
    (r"Cosmetics|Perfume|Hair Salon", "💄"),
    (r"Jewelry", "💍"),
    (r"Sunglasses", "🕶️"),
    (r"Toy|Collectibles|Pop-Up", "🧸"),
    (r"Grocery|Market|Department|Mall|Shopping|Vitamin", "🛒"),
    (r"Clothing|Fashion|Vintage|Thrift|Boutique|Store", "🛍️"),
]

def classify_type(cat):
    if FOOD_RE.search(cat) and not SEE_RE.search(cat):
        return "Eat"
    if SEE_RE.search(cat):
        return "See"
    return "Shop"

# coarse "kind" bucket, independent of Eat/Shop/See — first match wins
KIND_RULES = [
    (r"Bakery Cafe|Themed Cafe|Internet Cafe|Coffee Shop|\bCafe\b", "Cafe"),
    (r"Bakery|Cake Shop|Confectionery|Pastry Shop|Patisserie|Donut Shop", "Bakery"),
    (r"Ice Cream|Gelato|Frozen Yogurt|Shaved Ice|Snow Shop|Dessert Shop", "Dessert"),
    (r"Bubble Tea|Juice and Smoothie|Tea Room", "Drinks"),
    (r"Izakaya", "Bar"),
    (r"BBQ", "BBQ"),
    (r"Food Court|Street Food", "Fast Food"),
    (r"Farmers Market|Grocery Store", "Market"),
    (r"Restaurant|Cuisine|Bistro|Steakhouse|Soul Food|Sandwich Shop", "Restaurant"),
    (r"Hair Salon|Cosmetics Store|Perfume Store", "Beauty"),
    (r"Outdoor Sports Store|Sporting Goods Store", "Sporting Goods"),
    (r"Clothing Store|Fashion Accessory|Shoe Store|Sunglasses Store|Sportswear|Skate Shop|Thrift Store", "Clothing"),
    (r"Toy Store|Collectibles Store|Pop-Up Shop|Jewelry Store|Vitamin and Supplement", "Specialty Shop"),
    (r"Department Store|Shopping Center|Shopping Mall", "Shopping Center"),
    (r"Japanese Garden", "Garden & Park"),
    (r"Hotel", "Hotel"),
    (r"Museum|Art Studio|Historic Place|Unincorporated Community", "Landmark"),
]

# cuisine tag — only meaningful for food places; empty string when not applicable
CUISINE_RULES = [
    (r"Korean BBQ Restaurant|Korean Cuisine", "Korean"),
    (r"Izakaya|Japanese Cuisine|Conveyor-Belt Sushi|Temaki Sushi|Sushi Restaurant|Ramen Restaurant|Udon Restaurant", "Japanese"),
    (r"Cantonese Cuisine|Chinese Cuisine|Szechuan Cuisine|Dim Sum Restaurant|Hot Pot Restaurant|Dumpling Restaurant", "Chinese"),
    (r"Taiwanese Cuisine", "Taiwanese"),
    (r"Thai Cuisine", "Thai"),
    (r"Vietnamese Cuisine", "Vietnamese"),
    (r"Malaysian Cuisine", "Malaysian"),
    (r"Asian Fusion Cuisine", "Asian Fusion"),
    (r"Asian Cuisine", "Asian"),
    (r"Indian Cuisine|Pakistani Cuisine", "Indian/Pakistani"),
    (r"Italian Cuisine|Neapolitan Pizza Restaurant|Pizza Restaurant", "Italian"),
    (r"French Cuisine", "French"),
    (r"Greek Cuisine", "Greek"),
    (r"Mediterranean Cuisine", "Mediterranean"),
    (r"Middle Eastern Cuisine", "Middle Eastern"),
    (r"Mexican Cuisine|Taco Restaurant", "Mexican"),
    (r"Peruvian Cuisine", "Peruvian"),
    (r"Hawaiian Cuisine|Poke Restaurant", "Hawaiian"),
    (r"Soul Food Restaurant", "Soul Food"),
    (r"BBQ Restaurant", "BBQ"),
    (r"Steakhouse", "Steakhouse"),
    (r"Seafood Restaurant", "Seafood"),
    (r"American Cuisine|Burger Restaurant|Sandwich Shop|Waffle Restaurant", "American"),
]

def kind_for(cat):
    for pat, k in KIND_RULES:
        if re.search(pat, cat, re.I):
            return k
    return "Other"

def cuisine_for(cat):
    for pat, c in CUISINE_RULES:
        if re.search(pat, cat, re.I):
            return c
    return ""

def emoji_for(cat):
    for pat, e in EMOJI:
        if re.search(pat, cat, re.I):
            return e
    return "📍"

def city_of(addr):
    m = re.search(r",\s*([^,]+),\s*CA", addr)
    if m:
        return m.group(1).strip()
    m = re.search(r"([A-Za-z][A-Za-z .'-]+),\s*CA", addr)
    return m.group(1).strip() if m else "?"

def slug(name, lat, lng):
    """Stable filename for a place's cached photo. MUST match fetch_photos.py."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"{s}-{round(lat, 4)}_{round(lng, 4)}"

PHOTO_DIR = os.path.join(HERE, "photos")
GALLERY_DIR = os.path.join(HERE, "gallery")

def photo_for(name, lat, lng):
    """Relative URL if a cached photo exists (from fetch_photos.py), else ''."""
    fn = slug(name, lat, lng) + ".jpg"
    return f"photos/{fn}" if os.path.exists(os.path.join(PHOTO_DIR, fn)) else ""

def gallery_for(name, lat, lng):
    """Ordered photo list: the food cover first, then extra shots (Google order)."""
    sl = slug(name, lat, lng)
    out = []
    cover = photo_for(name, lat, lng)
    if cover:
        out.append(cover)
    for i in range(2, 12):
        fn = f"{sl}-{i}.jpg"
        if os.path.exists(os.path.join(GALLERY_DIR, fn)):
            out.append(f"gallery/{fn}")
    return out

# ---- enrichment -------------------------------------------------------------
# enrich.tsv (authored blurbs): slug, known, why, emoji
# digests.tsv (from fetch_enrich.py): includes rating + review count per slug
ENRICH = {}
enrich_path = os.path.join(HERE, "enrich.tsv")
if os.path.exists(enrich_path):
    with open(enrich_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ENRICH[row["slug"]] = row
digests_path = os.path.join(HERE, "digests.tsv")
if os.path.exists(digests_path):
    with open(digests_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            d = ENRICH.setdefault(row["slug"], {})
            d.setdefault("rating", row.get("rating", ""))
            d.setdefault("count", row.get("count", ""))
# featured.tsv: verified Michelin / Infatuation / etc. badges (slug -> feat line)
featured_path = os.path.join(HERE, "featured.tsv")
if os.path.exists(featured_path):
    with open(featured_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ENRICH.setdefault(row["slug"], {})["feat"] = row["feat"]

# hours (from fetch_enrich.py --hours, cached in details/*.json). Compact form
# per place: "24" for a place open 24/7, else a list of [openDay, openH, openM,
# closeDay, closeH, closeM] periods (closeDay may be openDay+1 for overnight hours).
HOURS = {}
DETAILS_DIR = os.path.join(HERE, "details")
if os.path.isdir(DETAILS_DIR):
    for fn in os.listdir(DETAILS_DIR):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(DETAILS_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        periods = (d.get("regularOpeningHours") or {}).get("periods") or []
        if any("close" not in p for p in periods):
            HOURS[fn[:-5]] = "24"
        elif periods:
            HOURS[fn[:-5]] = [
                [p["open"]["day"], p["open"]["hour"], p["open"].get("minute", 0),
                 p["close"]["day"], p["close"]["hour"], p["close"].get("minute", 0)]
                for p in periods
            ]

# ---- load -------------------------------------------------------------------
places = []
with open(TSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        if not row.get("name") or not row.get("lat"):
            continue
        try:
            lat = float(row["lat"]); lng = float(row["lng"])
        except (ValueError, TypeError):
            continue
        cat = row.get("category", "") or ""
        city = city_of(row.get("address", "") or "")
        region = "Bay Area" if lat > 36.5 else "LA / SoCal"
        name = row["name"].strip()
        en = ENRICH.get(slug(name, lat, lng), {})
        try:
            pop = int(en.get("count") or 0)
        except ValueError:
            pop = 0
        places.append({
            "name": name,
            "cat": cat,
            "price": (row.get("price") or "").strip(),
            "lat": lat, "lng": lng,
            "addr": (row.get("address") or "").strip(),
            "city": city,
            "region": region,
            "type": classify_type(cat),
            "kind": kind_for(cat),
            "cuisine": cuisine_for(cat),
            # per-place icon from the enrichment pass (tailored to the signature
            # dish) wins over the coarse category fallback
            "emoji": (en.get("emoji") or "").strip() or emoji_for(cat),
            "photo": photo_for(name, lat, lng),
            "gallery": gallery_for(name, lat, lng),
            "known": (en.get("known") or row.get("known") or "").strip(),
            "why": (en.get("why") or row.get("why") or "").strip(),
            "feat": (en.get("feat") or "").strip(),
            "rating": (en.get("rating") or "").strip(),
            "pop": pop,
            "hours": HOURS.get(slug(name, lat, lng), []),
        })

places.sort(key=lambda p: (p["region"], p["city"], p["name"]))
data_json = json.dumps(places, ensure_ascii=False)

counts = {}
for p in places:
    counts[p["type"]] = counts.get(p["type"], 0) + 1
print(f"Built {len(places)} places -> {counts}")

# ---- html -------------------------------------------------------------------
HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="My Places">
<meta name="theme-color" content="#f7f5f2">
<title>My Places</title>
<link rel="preconnect" href="https://a.basemaps.cartocdn.com" crossorigin>
<link rel="preconnect" href="https://b.basemaps.cartocdn.com" crossorigin>
<link rel="preconnect" href="https://c.basemaps.cartocdn.com" crossorigin>
<style>
/* --- leaflet.css (vendored, inlined) --- */
__LEAFLET_CSS__
/* --- MarkerCluster.css (vendored, inlined) --- */
__CLUSTER_CSS__
/* --- maplibre-gl.css (vendored, inlined) --- */
__MAPLIBRE_CSS__
/* --- app styles --- */
:root{
  --bg:#f7f5f2; --panel:#ffffff; --ink:#1c1c1e; --sub:#6b7280; --line:#e7e3dc;
  --eat:#e8590c; --shop:#7048e8; --see:#2b8a3e; --visited:#2fb344;
  --accent:#0a84ff; --shadow:0 6px 24px rgba(0,0,0,.12);
  --lbl:#1c1c1e; --lbl-halo:#ffffff; --lbl-visited:#178a3c;   /* labels on the light map */
}
@media (prefers-color-scheme: dark){
  /* The vector basemap is recolored per-theme in JS (styleBasemap). Here we only
     theme the app chrome + the place labels. */
  :root{ --bg:#1a1c1f; --panel:#26282c; --ink:#f2f2f4; --sub:#aab0b6; --line:#3a3d43;
         --visited:#37d05f; --shadow:0 6px 24px rgba(0,0,0,.5);
         --lbl:#f2f2f4; --lbl-halo:#141518; --lbl-visited:#37d05f; }
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg)}
#map{position:absolute;inset:0;z-index:0}
.leaflet-container{background:var(--bg)}

/* top bar */
.topbar{position:absolute;top:0;left:0;right:0;z-index:1000;padding:calc(env(safe-area-inset-top) + 10px) 12px 10px;
  background:linear-gradient(180deg, var(--bg) 62%, transparent);pointer-events:none}
.searchrow{display:flex;gap:8px;align-items:center;pointer-events:auto}
.search{flex:1;display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:11px 14px;box-shadow:var(--shadow)}
.search input{border:0;outline:0;background:transparent;color:var(--ink);font-size:16px;width:100%}
.search svg{flex:0 0 auto;opacity:.5}
.count{font-size:12px;color:var(--sub);padding:0 2px;white-space:nowrap;margin-top:9px;pointer-events:none}

/* filters button (opens the bottom sheet) */
.filterbtn{position:relative;flex:0 0 auto;width:44px;height:44px;border-radius:14px;background:var(--panel);
  border:1px solid var(--line);box-shadow:var(--shadow);display:flex;align-items:center;justify-content:center;
  cursor:pointer;color:var(--ink);pointer-events:auto}
.filterbtn:active{transform:scale(.94)}
.filterbtn .badge{position:absolute;top:-5px;right:-5px;min-width:18px;height:18px;padding:0 4px;
  border-radius:9px;background:var(--accent);color:#fff;font-size:11px;font-weight:700;line-height:18px;
  text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.4);border:1.5px solid var(--bg)}

/* filters bottom sheet */
#fsheet{position:fixed;inset:0;z-index:3000;display:none}
#fsheet.open{display:block}
#fsheet .backdrop{position:absolute;inset:0;background:rgba(0,0,0,.4)}
#fsheet .sheet{position:absolute;left:0;right:0;bottom:0;max-height:82vh;display:flex;flex-direction:column;
  background:var(--panel);border-radius:20px 20px 0 0;box-shadow:0 -8px 30px rgba(0,0,0,.3)}
#fsheet .fhead{display:flex;align-items:center;justify-content:space-between;padding:14px 8px 12px 18px;
  border-bottom:1px solid var(--line)}
#fsheet .fhead h2{margin:0;font-size:16px}
#fsheet .fclear{background:none;border:0;color:var(--accent);font-size:14px;font-weight:600;cursor:pointer;padding:6px 4px}
#fsheet .fclose{background:none;border:0;color:var(--sub);font-size:20px;cursor:pointer;padding:4px 10px}
#fsheet .fbody{overflow-y:auto;-webkit-overflow-scrolling:touch;padding:14px 18px 6px}
.fsec{margin-bottom:20px}
.fsec h3{margin:0 0 9px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--sub)}
.fchips{display:flex;flex-wrap:wrap;gap:8px}
.fchip{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:999px;
  padding:7px 13px;font-size:13px;font-weight:600;cursor:pointer;user-select:none}
.fchip[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.fchip.eat[aria-pressed="true"]{background:var(--eat);border-color:var(--eat);color:#fff}
.fchip.shop[aria-pressed="true"]{background:var(--shop);border-color:var(--shop);color:#fff}
.fchip.see[aria-pressed="true"]{background:var(--see);border-color:var(--see);color:#fff}
.hourrow{display:flex;flex-direction:column;gap:2px}
.hropt{display:flex;align-items:center;gap:10px;padding:8px 2px;font-size:14px;cursor:pointer}
.hropt input{width:17px;height:17px;accent-color:var(--accent)}
.pickrow{display:flex;gap:8px;margin:2px 0 6px 27px}
.pickrow select, .pickrow input{flex:1;border:1px solid var(--line);background:var(--bg);color:var(--ink);
  border-radius:8px;padding:8px;font-size:13px;min-width:0}
#fsheet .ffoot{padding:10px 18px calc(10px + env(safe-area-inset-bottom));border-top:1px solid var(--line)}
.fapply{display:block;width:100%;text-align:center;padding:13px;border-radius:12px;border:0;
  background:var(--accent);color:#fff;font-weight:700;font-size:15px;cursor:pointer}
.fapply:active{transform:scale(.98)}

/* marker + always-on label */
.mk{position:relative;width:22px;height:22px}
.pin{display:flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;
  background:#fff;border:2px solid var(--eat);font-size:12px;box-shadow:0 1px 4px rgba(0,0,0,.4)}
.pin.Shop{border-color:var(--shop)} .pin.See{border-color:var(--see)}
.mk.visited .pin{border-color:var(--visited)}
.leaflet-marker-icon .pin{transition:transform .1s}
/* label: dark text + white halo (map is always the colorful basemap).
   The declutter pass picks each label's side — right/left/top/bottom — to fit the most. */
.lbl{position:absolute;white-space:nowrap;font-size:11px;font-weight:600;letter-spacing:-.01em;
  color:var(--lbl);pointer-events:auto;cursor:pointer;
  text-shadow:0 0 3px var(--lbl-halo),0 0 3px var(--lbl-halo),0 0 4px var(--lbl-halo),0 1px 2px var(--lbl-halo)}
.mk.visited .lbl{color:var(--lbl-visited)}
.lbl.hide{display:none}
.lbl.pos-r{left:24px;top:11px;transform:translateY(-50%);text-align:left}
.lbl.pos-l{right:24px;left:auto;top:11px;transform:translateY(-50%);text-align:right}
.lbl.pos-t{left:11px;bottom:24px;top:auto;transform:translateX(-50%);text-align:center}
.lbl.pos-b{left:11px;top:24px;transform:translateX(-50%);text-align:center}

/* my-location dot + orientation cone (shows which way you're facing) */
.me{position:relative;width:120px;height:120px}
.me-cone{position:absolute;left:0;top:0;transform-origin:60px 60px;opacity:0;
  transition:transform .12s ease-out, opacity .3s}
.me-dot{position:absolute;left:50%;top:50%;width:16px;height:16px;border-radius:50%;
  background:#0a84ff;border:3px solid #fff;box-shadow:0 0 5px rgba(0,0,0,.5);transform:translate(-50%,-50%)}

/* cluster: a representative pin wearing a little "+N covered" badge */
.cbadge{position:absolute;top:-6px;right:-11px;min-width:16px;height:16px;padding:0 4px;
  border-radius:9px;background:var(--accent);color:#fff;font-size:10px;font-weight:700;
  line-height:16px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.4);border:1.5px solid #fff}

/* popup */
.leaflet-popup-content-wrapper{border-radius:16px;box-shadow:var(--shadow);background:var(--panel);color:var(--ink)}
.leaflet-popup-content{margin:14px 16px;font-size:14px;line-height:1.4}
.leaflet-popup-tip{background:var(--panel)}
.card .photowrap{position:relative;margin:0 0 10px;cursor:zoom-in}
.card .photo{width:100%;height:132px;object-fit:cover;border-radius:12px;display:block;background:var(--line)}
.card .pcount{position:absolute;right:8px;bottom:8px;background:rgba(0,0,0,.62);color:#fff;
  font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;backdrop-filter:blur(2px)}

/* photo viewer: a centered card overlaid on the (dimmed) map, not edge-to-edge.
   Opens with a scale+fade from the tapped thumbnail's on-screen rect (JS sets the
   from/to inline transform+opacity+background directly — see openViewer/closeViewer),
   so it reads as the thumbnail expanding into the full view rather than an abrupt
   appear; reverses the same way on close. The transition is defined only under
   no-preference, so prefers-reduced-motion users get an instant snap for free. */
#viewer{position:fixed;inset:0;z-index:4000;background:rgba(0,0,0,0);
  display:none;align-items:center;justify-content:center;padding:24px}
#viewer.open{display:flex}
#vbox{position:relative;width:min(94vw,520px);height:min(70vh,640px);
  background:#000;border-radius:18px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.5);
  opacity:0}
@media (prefers-reduced-motion:no-preference){
  #viewer{transition:background-color .28s ease}
  #vbox{transition:transform .32s cubic-bezier(.22,.61,.36,1), opacity .28s ease}
}
#vtrack{position:absolute;inset:0;display:flex;overflow-x:auto;overflow-y:hidden;
  scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;scrollbar-width:none}
#vtrack::-webkit-scrollbar{display:none}
#vtrack img{flex:0 0 100%;width:100%;height:100%;object-fit:contain;scroll-snap-align:center;background:#000}
#vclose{position:absolute;top:10px;right:10px;z-index:2;
  width:32px;height:32px;border-radius:50%;border:0;background:rgba(0,0,0,.55);color:#fff;
  font-size:17px;line-height:32px;text-align:center;cursor:pointer}
#vcount{position:absolute;left:50%;transform:translateX(-50%);bottom:12px;z-index:2;
  color:#fff;font-size:12px;font-weight:600;background:rgba(0,0,0,.55);
  padding:4px 11px;border-radius:999px;pointer-events:none}
.card h3{margin:0 0 2px;font-size:17px;letter-spacing:-.01em}
.card .meta{color:var(--sub);font-size:13px;margin-bottom:6px}
.card .addr{color:var(--sub);font-size:12px;margin:6px 0 10px}
.card .feat{margin:6px 0;font-size:12.5px;font-weight:700;color:#b8860b;
  background:color-mix(in srgb,#b8860b 10%,transparent);border-radius:8px;padding:5px 8px}
@media (prefers-color-scheme: dark){.card .feat{color:#e6b84c;
  background:color-mix(in srgb,#e6b84c 12%,transparent)}}
.card .known{margin:6px 0}
.card .why{margin:6px 0;font-style:italic;color:var(--sub)}
.card .tag{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;color:#fff;margin-bottom:6px}
.tag.Eat{background:var(--eat)} .tag.Shop{background:var(--shop)} .tag.See{background:var(--see)}
.visited-btn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;margin:2px 0 9px;
  padding:10px;border-radius:10px;border:1px solid var(--line);background:transparent;color:var(--ink);
  font-weight:600;font-size:13px;cursor:pointer;-webkit-tap-highlight-color:transparent}
.visited-btn .box{width:17px;height:17px;border-radius:5px;border:2px solid var(--sub);
  display:flex;align-items:center;justify-content:center;font-size:12px;line-height:1;color:#fff}
.visited-btn.on{border-color:var(--visited);color:var(--visited);background:color-mix(in srgb,var(--visited) 12%,transparent)}
.visited-btn.on .box{background:var(--visited);border-color:var(--visited)}
.btns{display:flex;gap:8px;margin-top:4px}
.btn{flex:1;text-align:center;text-decoration:none;font-weight:600;font-size:13px;padding:9px;border-radius:10px;
  background:var(--accent);color:#fff}
.btn.sec{background:transparent;border:1px solid var(--line);color:var(--ink)}

/* locate button */
.locate{position:absolute;right:14px;bottom:calc(env(safe-area-inset-bottom) + 20px);z-index:1000;
  width:52px;height:52px;border-radius:50%;background:var(--panel);border:1px solid var(--line);
  box-shadow:var(--shadow);display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:22px}
.locate:active{transform:scale(.94)}
.leaflet-control-attribution{font-size:10px;background:rgba(255,255,255,.6)}
@media (prefers-color-scheme: dark){.leaflet-control-attribution{background:rgba(0,0,0,.5)!important;color:#888}
  .leaflet-control-attribution a{color:#aaa}}
</style>
</head>
<body>
<div id="map"></div>
<div class="topbar">
  <div class="searchrow">
    <label class="search">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input id="q" type="search" placeholder="Search my places…" autocomplete="off">
    </label>
    <div class="filterbtn" id="filterBtn" title="Filters">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16M7 12h10M10 19h4"/></svg>
      <span class="badge" id="filterBadge" hidden>0</span>
    </div>
  </div>
  <div class="count" id="count"></div>
</div>
<div id="fsheet" aria-hidden="true">
  <div class="backdrop" id="fsheetBackdrop"></div>
  <div class="sheet">
    <div class="fhead">
      <button class="fclear" id="fclear">Clear all</button>
      <h2>Filters</h2>
      <button class="fclose" id="fclose" aria-label="Close">✕</button>
    </div>
    <div class="fbody">
      <div class="fsec">
        <h3>Type</h3>
        <div class="fchips" id="fType">
          <div class="fchip eat" data-type="Eat" aria-pressed="true">🍴 Eat</div>
          <div class="fchip shop" data-type="Shop" aria-pressed="false">🛍️ Shop</div>
          <div class="fchip see" data-type="See" aria-pressed="false">🎡 See</div>
        </div>
      </div>
      <div class="fsec">
        <h3>Region</h3>
        <div class="fchips" id="fRegion">
          <div class="fchip" data-region="all" aria-pressed="true">All areas</div>
          <div class="fchip" data-region="LA / SoCal" aria-pressed="false">LA</div>
          <div class="fchip" data-region="Bay Area" aria-pressed="false">Bay Area</div>
        </div>
      </div>
      <div class="fsec">
        <h3>Hours</h3>
        <div class="hourrow" id="fHours">
          <label class="hropt"><input type="radio" name="hmode" value="any" checked> Any time</label>
          <label class="hropt"><input type="radio" name="hmode" value="now"> Open now</label>
          <label class="hropt"><input type="radio" name="hmode" value="pick"> Pick a day &amp; time</label>
          <div class="pickrow" id="fPickRow" hidden>
            <select id="fDay">
              <option value="today">Today</option>
              <option value="0">Sunday</option>
              <option value="1">Monday</option>
              <option value="2">Tuesday</option>
              <option value="3">Wednesday</option>
              <option value="4">Thursday</option>
              <option value="5">Friday</option>
              <option value="6">Saturday</option>
            </select>
            <input type="time" id="fTime" value="18:00">
          </div>
        </div>
      </div>
      <div class="fsec">
        <h3>Cuisine</h3>
        <div class="fchips" id="fCuisine"></div>
      </div>
      <div class="fsec">
        <h3>Category</h3>
        <div class="fchips" id="fKind"></div>
      </div>
    </div>
    <div class="ffoot">
      <button class="fapply" id="fapply">Show places</button>
    </div>
  </div>
</div>
<div class="locate" id="locate" title="Near me">◎</div>
<div id="viewer" aria-hidden="true">
  <div id="vbox">
    <div id="vtrack"></div>
    <button id="vclose" aria-label="Close">✕</button>
    <div id="vcount"></div>
  </div>
</div>

<script>
// --- leaflet.js (vendored, inlined) ---
__LEAFLET_JS__
</script>
<script>
// --- leaflet.markercluster.js (vendored, inlined) ---
__CLUSTER_JS__
</script>
<script>
// --- maplibre-gl.js (vendored, inlined) ---
__MAPLIBRE_JS__
</script>
<script>
// --- maplibre-gl-leaflet.js (vendored, inlined) ---
__MAPLIBRE_LEAFLET_JS__
</script>
<script>
const PLACES = __DATA__;
const TYPE_ON = {Eat:true, Shop:false, See:false};
let REGION = "all";
let QUERY = "";
let CUISINE_ON = new Set();   // empty = any cuisine
let KIND_ON = new Set();      // empty = any category
let HOURS_MODE = "any";       // any | now | pick
let PICK_DAY = "today";       // "today" or 0-6 (0=Sunday, matches Date#getDay)
let PICK_TIME = "18:00";
let VIS = [];   // markers currently shown (set each render, used by declutter)

// --- visited state (saved on THIS device only) ---
// Ask the browser to keep our storage (iOS can evict localStorage for
// home-screen web apps otherwise — the usual cause of "visited resets").
try { if (navigator.storage && navigator.storage.persist) navigator.storage.persist(); } catch(e){}
const VKEY = "visited_v1";
let VISITED = {};
try { VISITED = JSON.parse(localStorage.getItem(VKEY) || "{}"); } catch(e){}
const pkey = p => p.name + "|" + p.lat.toFixed(5) + "," + p.lng.toFixed(5);
const esc = s => (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const map = L.map("map", {
  zoomControl:false, attributionControl:true,
  // The vector basemap (unlike the old raster layer) doesn't set the map's zoom range;
  // markercluster needs a finite maxZoom to build its grid, so set it here explicitly.
  maxZoom:20, minZoom:3,
  // Pan-release glide: Leaflet's inertia coasts a distance/duration of
  // speed/(inertiaDeceleration*easeLinearity) after a flick. Lowering just
  // inertiaDeceleration (only) scales that uniformly across all flick speeds
  // without touching the max-speed cap, so hard flicks don't get disproportionately
  // floaty. 2200->1830 is a ~20% longer coast — noticeably glidier, not overshooty.
  inertia:true, inertiaDeceleration:1830, inertiaMaxSpeed:3200, easeLinearity:0.22,
}).setView([34.06,-118.30], 11);
L.control.zoom({position:"bottomleft"}).addTo(map);

// --- Apple-style custom vector basemap (MapLibre GL, via maplibre-gl-leaflet) ---
// Free OpenFreeMap 'positron' vector tiles restyled to our palette: grey land/roads,
// green parks, blue water, and PURPLE shopping/commercial districts. Light & dark.
const darkUI = window.matchMedia("(prefers-color-scheme: dark)").matches;
const PAL = darkUI ? {
  land:"#23262b", landuse:"#282b30", park:"#213d29", building:"#2c3037", bldgLine:"#41464e",
  water:"#183a4e", road:"#3e434b", casing:"#2a2e35", boundary:"#474c54",
  commercial:"rgba(128,98,170,.42)", label:"#c7ccd3", halo:"#141619"
} : {
  land:"#eeeeec", landuse:"#e7e6e3", park:"#cfe6c5", building:"#e2e1dd", bldgLine:"#d8d6d1",
  water:"#a7d3e8", road:"#ffffff", casing:"#dddbd6", boundary:"#ceccc7",
  commercial:"rgba(150,120,205,.32)", label:"#5b6067", halo:"#ffffff"
};

// PERF: maplibre-gl-leaflet's _pinchZoom calls glMap.jumpTo() — a synchronous
// full re-render of the vector scene — on every raw Leaflet 'zoom' event. During
// a touch pinch gesture that event fires once per touchmove, often far faster
// than the screen can actually paint, so the GL layer was redrawing many more
// times per second than useful and starving the main thread (measured: 20 rapid
// zoom events -> 20 redundant jumpTo calls, 1:1, no coalescing). Patch the
// prototype (before the layer is created, so getEvents() picks it up) to batch
// same-frame calls via requestAnimationFrame: at most one redraw per frame,
// always using the latest zoom/center, instead of one per input event.
(function(){
  let raf = 0, pendingZoom = null, pendingCenter = null;
  L.MaplibreGL.prototype._pinchZoom = function(){
    pendingZoom = this._map.getZoom() - 1;
    const c = this._map.getCenter();
    pendingCenter = [c.lng, c.lat];
    if (raf) return;
    const gl = this._glMap;
    raf = requestAnimationFrame(() => {
      raf = 0;
      gl.jumpTo({ zoom: pendingZoom, center: pendingCenter });
    });
  };
})();

const glLayer = L.maplibreGL({
  style:"https://tiles.openfreemap.org/styles/positron",
  attribution:'&copy; <a href="https://openfreemap.org">OpenFreeMap</a> &copy; <a href="https://openmaptiles.org">OpenMapTiles</a> &copy; OSM'
}).addTo(map);

function styleBasemap(m){
  for(const layer of m.getStyle().layers){
    const id = layer.id, t = layer.type, sl = layer["source-layer"];
    try{
      if(t === "background") m.setPaintProperty(id, "background-color", PAL.land);
      else if(t === "fill"){
        if(sl === "water") m.setPaintProperty(id, "fill-color", PAL.water);
        else if(sl === "park" || /wood|grass|landcover|park/i.test(id)) m.setPaintProperty(id, "fill-color", PAL.park);
        else if(sl === "building"){
          m.setPaintProperty(id, "fill-color", PAL.building);
          // outline only appears once you're zoomed in close — fades out by z14
          m.setPaintProperty(id, "fill-outline-color",
            ["interpolate", ["linear"], ["zoom"], 14, "rgba(0,0,0,0)", 16, PAL.bldgLine]);
        }
        else if(sl === "landuse") m.setPaintProperty(id, "fill-color", PAL.landuse);
      } else if(t === "line"){
        if(sl === "water" || sl === "waterway") m.setPaintProperty(id, "line-color", PAL.water);
        else if(/casing/.test(id)) m.setPaintProperty(id, "line-color", PAL.casing);
        else if(sl === "transportation") m.setPaintProperty(id, "line-color", PAL.road);
        else if(sl === "boundary") m.setPaintProperty(id, "line-color", PAL.boundary);
      } else if(t === "symbol"){
        m.setPaintProperty(id, "text-color", PAL.label);
        m.setPaintProperty(id, "text-halo-color", PAL.halo);
      }
    }catch(e){}
  }
  // positron has no commercial layer — add Apple-style purple shopping districts
  if(!m.getLayer("commercial-areas")){
    try{ m.addLayer({
      id:"commercial-areas", type:"fill", source:"openmaptiles", "source-layer":"landuse",
      filter:["match", ["get","class"], ["commercial","retail"], true, false],
      paint:{"fill-color":PAL.commercial}
    }, "building"); }catch(e){}
  }
}
const glMap = glLayer.getMaplibreMap();
glMap.on("load", () => styleBasemap(glMap));

const cluster = L.markerClusterGroup({
  maxClusterRadius:22, spiderfyOnMaxZoom:true, showCoverageOnHover:false,
  // Leaflet.markercluster defaults to removing markers/clusters outside the
  // viewport and only recomputing on moveend — with only ~300 pins total
  // (not the tens-of-thousands this default is meant for) that trade is pure
  // loss: it's what causes pins to "pop in" once you stop panning. Keeping
  // everything always mounted costs a few hundred DOM nodes and buys smooth
  // panning with zero pop-in.
  removeOutsideVisibleBounds:false,
  // Don't hide everything behind a number bubble: show the most popular place's pin,
  // with a small "+N" for how many others are stacked under it.
  iconCreateFunction: c => {
    const kids = c.getAllChildMarkers();
    let rep = kids[0].__p;
    for (const k of kids) if ((k.__p.pop||0) > (rep.pop||0)) rep = k.__p;
    const more = kids.length - 1;
    return L.divIcon({className:"", iconSize:[22,22], iconAnchor:[11,11], popupAnchor:[0,-11],
      html:`<div class="mk"><div class="pin ${rep.type}">${rep.emoji}</div>`
         + `<span class="cbadge">+${more}</span></div>`});
  }
});
map.addLayer(cluster);

function dirUrl(p){ return `https://maps.apple.com/?daddr=${p.lat},${p.lng}&q=${encodeURIComponent(p.name)}`; }
function gmapUrl(p){ return `https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}`; }

function fmtCount(n){ return n >= 1000 ? (n/1000).toFixed(1).replace(/\.0$/,"") + "k" : "" + n; }
function popupHtml(p){
  const nphotos = (p.gallery && p.gallery.length) || (p.photo ? 1 : 0);
  const badge = nphotos > 1 ? `<span class="pcount">▦ ${nphotos}</span>` : "";
  const photo = p.photo
    ? `<div class="photowrap" data-k="${esc(pkey(p))}"><img class="photo" src="${p.photo}" alt="" loading="lazy">${badge}</div>`
    : "";
  const feat = p.feat ? `<div class="feat">🏅 ${esc(p.feat)}</div>` : "";
  const known = p.known ? `<div class="known"><b>Known for:</b> ${esc(p.known)}</div>` : "";
  const price = p.price ? ` · ${esc(p.price)}` : "";
  const stars = p.rating ? ` · ★ ${p.rating}${p.pop ? " (" + fmtCount(p.pop) + ")" : ""}` : "";
  const on = VISITED[pkey(p)] ? " on" : "";
  return `<div class="card">
    ${photo}
    <span class="tag ${p.type}">${p.emoji} ${p.type}</span>
    <h3>${esc(p.name)}</h3>
    <div class="meta">${esc(p.cat)}${price}${stars}</div>
    ${feat}${known}
    <div class="addr">${esc(p.addr)}</div>
    <button class="visited-btn${on}" data-k="${esc(pkey(p))}">
      <span class="box">${on ? "✓" : ""}</span><span class="lab">${on ? "Visited" : "Mark visited"}</span>
    </button>
    <div class="btns">
      <a class="btn" href="${dirUrl(p)}" target="_blank" rel="noopener">Directions</a>
      <a class="btn sec" href="${gmapUrl(p)}" target="_blank" rel="noopener">Google</a>
    </div>
  </div>`;
}

function iconFor(p){
  const v = VISITED[pkey(p)] ? " visited" : "";
  return L.divIcon({className:"", iconSize:[22,22], iconAnchor:[11,11], popupAnchor:[0,-11],
    html:`<div class="mk${v}"><div class="pin ${p.type}">${p.emoji}</div>`
       + `<span class="lbl hide">${esc(p.name)}</span></div>`});
}

const byKey = {};
const markers = PLACES.map(p => {
  const m = L.marker([p.lat,p.lng], {icon: iconFor(p)});
  m.__p = p;
  m.bindPopup(popupHtml(p), {maxWidth:300, minWidth:230, autoPan:false});
  byKey[pkey(p)] = m;
  return m;
});

// --- hours filtering: periods are [openDay,openH,openM,closeDay,closeH,closeM]
// in Google's weekday convention (0=Sunday, matches Date#getDay). Checking the
// query instant against 3 week-shifted copies of each period handles the one
// case that needs it: hours that wrap past midnight into the next day.
function isOpenAt(hours, dayIdx, mins){
  if (hours === "24") return true;
  if (!hours || !hours.length) return false;
  const q = dayIdx * 1440 + mins;
  for (const per of hours){
    const start = per[0]*1440 + per[1]*60 + per[2];
    let end = per[3]*1440 + per[4]*60 + per[5];
    if (end <= start) end += 10080;   // overnight wrap (e.g. 6pm–2am)
    for (const qq of [q, q + 10080, q - 10080]){
      if (qq >= start && qq < end) return true;
    }
  }
  return false;
}
function hoursMatch(p){
  if (HOURS_MODE === "any") return true;
  const now = new Date();
  let dayIdx, mins;
  if (HOURS_MODE === "now"){
    dayIdx = now.getDay(); mins = now.getHours()*60 + now.getMinutes();
  } else {
    dayIdx = PICK_DAY === "today" ? now.getDay() : parseInt(PICK_DAY, 10);
    const [hh, mm] = (PICK_TIME || "00:00").split(":").map(Number);
    mins = hh*60 + (mm || 0);
  }
  return isOpenAt(p.hours, dayIdx, mins);
}

function activeFilterCount(){
  let n = 0;
  const defaultType = TYPE_ON.Eat && !TYPE_ON.Shop && !TYPE_ON.See;
  if (!defaultType) n++;
  if (REGION !== "all") n++;
  if (CUISINE_ON.size) n++;
  if (KIND_ON.size) n++;
  if (HOURS_MODE !== "any") n++;
  return n;
}
function updateFilterBadge(){
  const n = activeFilterCount();
  const b = document.getElementById("filterBadge");
  b.hidden = n === 0;
  if (n) b.textContent = n;
}

function render(){
  cluster.clearLayers();
  const q = QUERY.trim().toLowerCase();
  let shown = 0;
  const vis = [];
  for (const m of markers){
    const p = m.__p;
    if (!TYPE_ON[p.type]) continue;
    if (REGION !== "all" && p.region !== REGION) continue;
    if (CUISINE_ON.size && !CUISINE_ON.has(p.cuisine)) continue;
    if (KIND_ON.size && !KIND_ON.has(p.kind)) continue;
    if (!hoursMatch(p)) continue;
    if (q && !(p.name.toLowerCase().includes(q) || p.cat.toLowerCase().includes(q) || p.city.toLowerCase().includes(q))) continue;
    vis.push(m); shown++;
  }
  VIS = vis;
  cluster.addLayers(vis);
  document.getElementById("count").textContent = shown + " places";
  updateFilterBadge();
  scheduleDeclutter();
}

// --- Apple-Maps-style labels: show names, nudge each to whichever side fits, hide the rest ---
function overlaps(a, b){ return !(a.x2 < b.x1 || b.x2 < a.x1 || a.y2 < b.y1 || b.y2 < a.y1); }
function labelBox(pos, pt, w){
  const h = 15, gx = 13, gy = 13;            // gap from the pin center
  if (pos === "r") return {x1: pt.x+gx,   y1: pt.y-h/2,    x2: pt.x+gx+w, y2: pt.y+h/2};
  if (pos === "l") return {x1: pt.x-gx-w, y1: pt.y-h/2,    x2: pt.x-gx,   y2: pt.y+h/2};
  if (pos === "t") return {x1: pt.x-w/2,  y1: pt.y-gy-h,   x2: pt.x+w/2,  y2: pt.y-gy};
  return                 {x1: pt.x-w/2,  y1: pt.y+gy,     x2: pt.x+w/2,  y2: pt.y+gy+h};  // "b"
}
function declutter(){
  const sz = map.getSize(), cand = [];
  for (const m of VIS){
    const el = m.getElement();               // null while inside a cluster
    if (!el) continue;
    const lbl = el.querySelector(".lbl");
    if (!lbl) continue;
    let indiv = false;
    try { indiv = cluster.getVisibleParent(m) === m; } catch(e){ indiv = false; }
    const pt = indiv ? map.latLngToContainerPoint(m.getLatLng()) : null;
    const off = !pt || pt.x < -60 || pt.y < -30 || pt.x > sz.x + 60 || pt.y > sz.y + 30;
    if (!indiv || off){ lbl.classList.add("hide"); continue; }
    cand.push({lbl, pt, name: m.__p.name});
  }
  // seed the occupied list with every visible pin so labels never sit on top of a pin
  const placed = cand.map(c => ({x1: c.pt.x-12, y1: c.pt.y-12, x2: c.pt.x+12, y2: c.pt.y+12}));
  const SIDES = ["r", "l", "t", "b"];
  for (const c of cand){
    const w = 10 + Math.min(c.name.length, 24) * 6.3;
    let side = null;
    for (const s of SIDES){
      const box = labelBox(s, c.pt, w);
      if (box.x1 < -60 || box.x2 > sz.x + 60) continue;   // keep on-screen
      if (!placed.some(b => overlaps(b, box))){ placed.push(box); side = s; break; }
    }
    c.lbl.className = side ? ("lbl pos-" + side) : "lbl hide";
  }
}
let declRAF = 0;
function scheduleDeclutter(){
  if (declRAF) return;
  declRAF = requestAnimationFrame(() => { declRAF = 0; declutter(); });
}
map.on("zoomend moveend", scheduleDeclutter);
cluster.on("animationend", scheduleDeclutter);

// When a place is opened, slide the map so the whole expanded card is centered
map.on("popupopen", e => {
  const el = e.popup.getElement();
  if (!el) return;
  const sz = map.getSize();
  const target = L.point(sz.x/2, Math.min(sz.y/2 + el.offsetHeight/2, sz.y - 40));
  const d = map.latLngToContainerPoint(e.popup._latlng).subtract(target);
  if (Math.abs(d.x) > 2 || Math.abs(d.y) > 2) map.panBy(d, {animate:true, duration:0.3});
});

// --- filters bottom sheet ---
const CUISINES = [...new Set(PLACES.map(p => p.cuisine).filter(Boolean))].sort();
const KINDS = [...new Set(PLACES.map(p => p.kind))].sort();
document.getElementById("fCuisine").innerHTML = CUISINES.map(c =>
  `<div class="fchip" data-cuisine="${esc(c)}" aria-pressed="false">${esc(c)}</div>`).join("");
document.getElementById("fKind").innerHTML = KINDS.map(k =>
  `<div class="fchip" data-kind="${esc(k)}" aria-pressed="false">${esc(k)}</div>`).join("");

const fsheet = document.getElementById("fsheet");
function openSheet(){ fsheet.classList.add("open"); fsheet.setAttribute("aria-hidden", "false"); }
function closeSheet(){ fsheet.classList.remove("open"); fsheet.setAttribute("aria-hidden", "true"); }
document.getElementById("filterBtn").addEventListener("click", openSheet);
document.getElementById("fclose").addEventListener("click", closeSheet);
document.getElementById("fsheetBackdrop").addEventListener("click", closeSheet);
document.getElementById("fapply").addEventListener("click", closeSheet);

function syncSheetUI(){
  document.querySelectorAll("#fType .fchip").forEach(c => c.setAttribute("aria-pressed", TYPE_ON[c.dataset.type]));
  document.querySelectorAll("#fRegion .fchip").forEach(c => c.setAttribute("aria-pressed", c.dataset.region === REGION));
  document.querySelectorAll("#fCuisine .fchip").forEach(c => c.setAttribute("aria-pressed", CUISINE_ON.has(c.dataset.cuisine)));
  document.querySelectorAll("#fKind .fchip").forEach(c => c.setAttribute("aria-pressed", KIND_ON.has(c.dataset.kind)));
  document.querySelector(`input[name="hmode"][value="${HOURS_MODE}"]`).checked = true;
  document.getElementById("fPickRow").hidden = HOURS_MODE !== "pick";
  document.getElementById("fDay").value = PICK_DAY;
  document.getElementById("fTime").value = PICK_TIME;
}

document.getElementById("fclear").addEventListener("click", () => {
  TYPE_ON.Eat = true; TYPE_ON.Shop = false; TYPE_ON.See = false;
  REGION = "all"; CUISINE_ON.clear(); KIND_ON.clear();
  HOURS_MODE = "any"; PICK_DAY = "today"; PICK_TIME = "18:00";
  syncSheetUI();
  render();
});
document.getElementById("fType").addEventListener("click", e => {
  const c = e.target.closest(".fchip"); if(!c) return;
  const t = c.dataset.type; TYPE_ON[t] = !TYPE_ON[t];
  c.setAttribute("aria-pressed", TYPE_ON[t]);
  render();
});
document.getElementById("fRegion").addEventListener("click", e => {
  const c = e.target.closest(".fchip"); if(!c) return;
  REGION = c.dataset.region;
  document.querySelectorAll("#fRegion .fchip").forEach(x => x.setAttribute("aria-pressed", x.dataset.region === REGION));
  render();
});
document.getElementById("fCuisine").addEventListener("click", e => {
  const c = e.target.closest(".fchip"); if(!c) return;
  const v = c.dataset.cuisine;
  if (CUISINE_ON.has(v)) CUISINE_ON.delete(v); else CUISINE_ON.add(v);
  c.setAttribute("aria-pressed", CUISINE_ON.has(v));
  render();
});
document.getElementById("fKind").addEventListener("click", e => {
  const c = e.target.closest(".fchip"); if(!c) return;
  const v = c.dataset.kind;
  if (KIND_ON.has(v)) KIND_ON.delete(v); else KIND_ON.add(v);
  c.setAttribute("aria-pressed", KIND_ON.has(v));
  render();
});
document.querySelectorAll('input[name="hmode"]').forEach(r => r.addEventListener("change", e => {
  HOURS_MODE = e.target.value;
  document.getElementById("fPickRow").hidden = HOURS_MODE !== "pick";
  render();
}));
document.getElementById("fDay").addEventListener("change", e => { PICK_DAY = e.target.value; if (HOURS_MODE === "pick") render(); });
document.getElementById("fTime").addEventListener("change", e => { PICK_TIME = e.target.value; if (HOURS_MODE === "pick") render(); });

document.getElementById("q").addEventListener("input", e => { QUERY = e.target.value; render(); });

// visited toggle (inside popups) — flips the on-device flag + pin outline to green
document.addEventListener("click", e => {
  const b = e.target.closest(".visited-btn"); if(!b) return;
  const k = b.dataset.k, now = !VISITED[k];
  if (now) VISITED[k] = 1; else delete VISITED[k];
  try { localStorage.setItem(VKEY, JSON.stringify(VISITED)); } catch(err){}
  b.classList.toggle("on", now);
  b.querySelector(".box").textContent = now ? "✓" : "";
  b.querySelector(".lab").textContent = now ? "Visited" : "Mark visited";
  const m = byKey[k], el = m && m.getElement();
  if (el){ const mk = el.querySelector(".mk"); if (mk) mk.classList.toggle("visited", now); }
});

// --- fullscreen swipe photo viewer ---
const viewer = document.getElementById("viewer");
const vbox = document.getElementById("vbox");
const vtrack = document.getElementById("vtrack");
const vcount = document.getElementById("vcount");
function updateVCount(n){ vcount.textContent = (Math.round(vtrack.scrollLeft / vtrack.clientWidth) + 1) + " / " + n; }

// shared-element open/close: vbox animates between its natural centered rect
// and the tapped thumbnail's on-screen rect, so it reads as the thumbnail
// expanding into the full view (and collapsing back) rather than a hard cut.
let originRect = null;   // frozen at open time; reused (unchanged) for the close animation
let closeTimer = 0;
function transformToRect(from){
  const to = vbox.getBoundingClientRect();
  const sx = from.width / to.width, sy = from.height / to.height;
  const dx = (from.left + from.width / 2) - (to.left + to.width / 2);
  const dy = (from.top + from.height / 2) - (to.top + to.height / 2);
  return `translate(${dx}px,${dy}px) scale(${sx},${sy})`;
}
function openViewer(list, start, originEl){
  if (!list || !list.length) return;
  clearTimeout(closeTimer);
  vtrack.innerHTML = list.map(src => `<img src="${src}" alt="">`).join("");
  viewer.classList.add("open");
  originRect = originEl ? originEl.getBoundingClientRect() : null;

  // jump to the thumbnail-matching pose with transitions off, then let the
  // next frame transition it to the identity (full, centered) pose
  vbox.style.transition = "none";
  vbox.style.transform = originRect ? transformToRect(originRect) : "scale(.85)";
  vbox.style.opacity = "0";
  viewer.style.backgroundColor = "rgba(0,0,0,0)";
  void vbox.offsetHeight;   // force reflow so the jump above doesn't get coalesced into the transition
  vbox.style.transition = "";
  requestAnimationFrame(() => {
    vbox.style.transform = "none";
    vbox.style.opacity = "1";
    viewer.style.backgroundColor = "rgba(0,0,0,.55)";
  });

  const n = list.length;
  requestAnimationFrame(() => { vtrack.scrollLeft = (start || 0) * vtrack.clientWidth; updateVCount(n); });
  vtrack.onscroll = () => updateVCount(n);
}
function closeViewer(){
  if (!viewer.classList.contains("open")) return;
  clearTimeout(closeTimer);
  vbox.style.transform = originRect ? transformToRect(originRect) : "scale(.85)";
  vbox.style.opacity = "0";
  viewer.style.backgroundColor = "rgba(0,0,0,0)";
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  closeTimer = setTimeout(() => {
    viewer.classList.remove("open");
    vtrack.innerHTML = ""; vtrack.onscroll = null;
    vbox.style.transition = "none";
    vbox.style.transform = ""; vbox.style.opacity = ""; viewer.style.backgroundColor = "";
    void vbox.offsetHeight;
    vbox.style.transition = "";
  }, reduced ? 0 : 320);
}
document.getElementById("vclose").addEventListener("click", closeViewer);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeViewer(); });
// tapping the dimmed backdrop (outside the photo card) closes it
viewer.addEventListener("click", e => { if (e.target === viewer) closeViewer(); });
// tapping the letterbox bars around a contain-fit photo LOOKS like backdrop
// (same black) but is technically still inside the <img> box — treat a tap
// outside the photo's actual rendered pixels the same as a backdrop tap.
vtrack.addEventListener("click", e => {
  const img = e.target.closest("img");
  if (!img){ closeViewer(); return; }
  const iw = img.naturalWidth, ih = img.naturalHeight;
  if (!iw || !ih) return;
  const r = img.getBoundingClientRect();
  const scale = Math.min(r.width / iw, r.height / ih);
  const rw = iw * scale, rh = ih * scale;
  const offX = (r.width - rw) / 2, offY = (r.height - rh) / 2;
  const x = e.clientX - r.left, y = e.clientY - r.top;
  if (x < offX || x > offX + rw || y < offY || y > offY + rh) closeViewer();
});
// open the viewer from a card's photo
document.addEventListener("click", e => {
  const w = e.target.closest(".photowrap"); if (!w) return;
  const m = byKey[w.dataset.k]; if (!m) return;
  const g = (m.__p.gallery && m.__p.gallery.length) ? m.__p.gallery
          : (m.__p.photo ? [m.__p.photo] : []);
  openViewer(g, 0, w);
});

// locate + orientation cone ("where I'm looking")
let meMarker = null, currentHeading = 0, headingOn = false;

const CONE = `<svg class="me-cone" width="120" height="120" viewBox="-60 -60 120 120">
  <defs><radialGradient id="cg" cx="50%" cy="50%" r="50%">
    <stop offset="0%" stop-color="rgba(10,132,255,.55)"/>
    <stop offset="100%" stop-color="rgba(10,132,255,0)"/>
  </radialGradient></defs>
  <path d="M0,0 L-33,-48 A58,58 0 0 1 33,-48 Z" fill="url(#cg)"/></svg>`;

function updateCone(){
  if(!meMarker) return;
  const el = meMarker.getElement(); if(!el) return;
  const cone = el.querySelector(".me-cone");
  if(cone){ cone.style.transform = `rotate(${currentHeading}deg)`; cone.style.opacity = 1; }
}
function onOrient(e){
  let h = null;
  if(typeof e.webkitCompassHeading === "number") h = e.webkitCompassHeading;      // iOS
  else if(e.absolute === true && typeof e.alpha === "number") h = 360 - e.alpha;   // Android
  if(h == null || isNaN(h)) return;
  currentHeading = h; updateCone();
}
function startHeading(){
  if(headingOn) return; headingOn = true;
  window.addEventListener("deviceorientationabsolute", onOrient, true);
  window.addEventListener("deviceorientation", onOrient, true);
}

document.getElementById("locate").addEventListener("click", () => {
  const DOE = window.DeviceOrientationEvent;          // iOS needs permission on a user gesture
  if(DOE && typeof DOE.requestPermission === "function")
    DOE.requestPermission().then(s => { if(s === "granted") startHeading(); }).catch(()=>{});
  else startHeading();
  map.locate({setView:true, maxZoom:15, enableHighAccuracy:true});
});
map.on("locationfound", e => {
  if(meMarker){ meMarker.setLatLng(e.latlng); }
  else {
    meMarker = L.marker(e.latlng, {interactive:false, zIndexOffset:10000, icon: L.divIcon({
      className:"", iconSize:[120,120], iconAnchor:[60,60],
      html:`<div class="me">${CONE}<div class="me-dot"></div></div>`})}).addTo(map);
  }
  updateCone();
});
map.on("locationerror", () => alert("Couldn't get your location. Allow location access and try again."));

render();
</script>
</body>
</html>"""

html = (HTML
        .replace("__LEAFLET_CSS__", LEAFLET_CSS)
        .replace("__CLUSTER_CSS__", CLUSTER_CSS)
        .replace("__MAPLIBRE_CSS__", MAPLIBRE_CSS)
        .replace("__LEAFLET_JS__", LEAFLET_JS)
        .replace("__CLUSTER_JS__", CLUSTER_JS)
        .replace("__MAPLIBRE_JS__", MAPLIBRE_JS)
        .replace("__MAPLIBRE_LEAFLET_JS__", MAPLIBRE_LEAFLET_JS)
        .replace("__DATA__", data_json))
kb = len(html.encode("utf-8")) // 1024
# Write to the repo root (handy for `python3 -m http.server`) and to deploy/
# which is the folder the host serves (Cloudflare Pages "output directory").
deploy_dir = os.path.join(HERE, "deploy")
os.makedirs(deploy_dir, exist_ok=True)
for out in (OUT, os.path.join(deploy_dir, "index.html")):
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out} ({kb} KB, self-contained — 1 request)")

# Mirror cached photos + gallery into deploy/ so the served build can show them.
for name in ("photos", "gallery"):
    src = os.path.join(HERE, name)
    if os.path.isdir(src):
        dst = os.path.join(deploy_dir, name)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        n = len([f for f in os.listdir(src) if f.endswith(".jpg")])
        print(f"Copied {n} {name} -> {dst}")
if not os.path.isdir(PHOTO_DIR):
    print("No photos/ yet — run fetch_photos.py to add food photos (see README).")
