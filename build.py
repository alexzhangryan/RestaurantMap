#!/usr/bin/env python3
"""Build a single-file, phone-friendly map (index.html) from places-raw.tsv.

Re-run this whenever the data changes (e.g. after adding known-for / why notes):
    python3 build.py
"""
import csv, json, re, os

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
LEAFLET_JS = vendor("leaflet.js")
CLUSTER_JS = vendor("leaflet.markercluster.js")

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
    (r"Italian|French|Bistro|American|Soul Food|Peruvian|Malaysian|Bar", "🍽️"),
    (r"Dessert|Confection", "🍰"),
    (r"Cafe|Food Court|Sandwich|Deli|Smoothie|Farmers Market", "🍴"),
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
        places.append({
            "name": row["name"].strip(),
            "cat": cat,
            "price": (row.get("price") or "").strip(),
            "lat": lat, "lng": lng,
            "addr": (row.get("address") or "").strip(),
            "city": city,
            "region": region,
            "type": classify_type(cat),
            "emoji": emoji_for(cat),
            # enrichment fields (filled in a later pass)
            "known": (row.get("known") or "").strip(),
            "why": (row.get("why") or "").strip(),
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
/* --- app styles --- */
:root{
  --bg:#f7f5f2; --panel:#ffffff; --ink:#1c1c1e; --sub:#6b7280; --line:#e7e3dc;
  --eat:#e8590c; --shop:#7048e8; --see:#2b8a3e; --accent:#0a84ff; --shadow:0 6px 24px rgba(0,0,0,.12);
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#111214; --panel:#1c1d20; --ink:#f2f2f4; --sub:#9aa0a6; --line:#2c2e33;
         --shadow:0 6px 24px rgba(0,0,0,.5); }
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
.count{font-size:12px;color:var(--sub);padding:0 4px;white-space:nowrap}
.chips{display:flex;gap:8px;margin-top:10px;overflow-x:auto;pointer-events:auto;-webkit-overflow-scrolling:touch;padding-bottom:2px}
.chips::-webkit-scrollbar{display:none}
.chip{flex:0 0 auto;border:1px solid var(--line);background:var(--panel);color:var(--ink);
  border-radius:999px;padding:7px 13px;font-size:13px;font-weight:600;box-shadow:var(--shadow);cursor:pointer;user-select:none;
  display:flex;align-items:center;gap:6px;transition:transform .06s}
.chip:active{transform:scale(.96)}
.chip[aria-pressed="true"].eat{background:var(--eat);border-color:var(--eat);color:#fff}
.chip[aria-pressed="true"].shop{background:var(--shop);border-color:var(--shop);color:#fff}
.chip[aria-pressed="true"].see{background:var(--see);border-color:var(--see);color:#fff}
.chip[aria-pressed="true"].region{background:var(--ink);border-color:var(--ink);color:var(--bg)}

/* marker */
.pin{display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;
  background:var(--panel);border:2px solid var(--eat);font-size:15px;box-shadow:0 2px 6px rgba(0,0,0,.3)}
.pin.Shop{border-color:var(--shop)} .pin.See{border-color:var(--see)}
.leaflet-marker-icon .pin{transition:transform .1s}

/* cluster */
.cl{display:flex;align-items:center;justify-content:center;border-radius:50%;color:#fff;font-weight:700;
  background:rgba(10,132,255,.9);border:3px solid rgba(255,255,255,.7);box-shadow:0 2px 8px rgba(0,0,0,.35)}

/* popup */
.leaflet-popup-content-wrapper{border-radius:16px;box-shadow:var(--shadow);background:var(--panel);color:var(--ink)}
.leaflet-popup-content{margin:14px 16px;font-size:14px;line-height:1.4}
.leaflet-popup-tip{background:var(--panel)}
.card h3{margin:0 0 2px;font-size:17px;letter-spacing:-.01em}
.card .meta{color:var(--sub);font-size:13px;margin-bottom:6px}
.card .addr{color:var(--sub);font-size:12px;margin:6px 0 10px}
.card .known{margin:6px 0}
.card .why{margin:6px 0;font-style:italic;color:var(--sub)}
.card .tag{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;color:#fff;margin-bottom:6px}
.tag.Eat{background:var(--eat)} .tag.Shop{background:var(--shop)} .tag.See{background:var(--see)}
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
    <span class="count" id="count"></span>
  </div>
  <div class="chips" id="chips">
    <div class="chip eat" data-type="Eat" aria-pressed="true">🍴 Eat</div>
    <div class="chip shop" data-type="Shop" aria-pressed="false">🛍️ Shop</div>
    <div class="chip see" data-type="See" aria-pressed="false">🎡 See</div>
    <div class="chip region" data-region="all" aria-pressed="true">All areas</div>
    <div class="chip region" data-region="LA / SoCal" aria-pressed="false">LA</div>
    <div class="chip region" data-region="Bay Area" aria-pressed="false">Bay Area</div>
  </div>
</div>
<div class="locate" id="locate" title="Near me">◎</div>

<script>
// --- leaflet.js (vendored, inlined) ---
__LEAFLET_JS__
</script>
<script>
// --- leaflet.markercluster.js (vendored, inlined) ---
__CLUSTER_JS__
</script>
<script>
const PLACES = __DATA__;
const TYPE_ON = {Eat:true, Shop:false, See:false};
let REGION = "all";
let QUERY = "";

const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
const tiles = dark
  ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
  : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

const map = L.map("map", {zoomControl:false, attributionControl:true}).setView([34.06,-118.30], 11);
L.control.zoom({position:"bottomleft"}).addTo(map);
L.tileLayer(tiles, {maxZoom:20, subdomains:"abcd", updateWhenIdle:false, keepBuffer:3,
  attribution:'&copy; <a href="https://openstreetmap.org">OSM</a> &copy; <a href="https://carto.com">CARTO</a>'}).addTo(map);

const cluster = L.markerClusterGroup({
  maxClusterRadius:50, spiderfyOnMaxZoom:true, showCoverageOnHover:false,
  iconCreateFunction: c => {
    const n = c.getChildCount();
    const s = n < 10 ? 34 : n < 50 ? 42 : 50;
    return L.divIcon({html:`<div class="cl" style="width:${s}px;height:${s}px;font-size:${n<50?13:15}px">${n}</div>`,
      className:"", iconSize:[s,s]});
  }
});
map.addLayer(cluster);

function dirUrl(p){ return `https://maps.apple.com/?daddr=${p.lat},${p.lng}&q=${encodeURIComponent(p.name)}`; }
function gmapUrl(p){ return `https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}`; }

function popupHtml(p){
  const known = p.known ? `<div class="known"><b>Known for:</b> ${p.known}</div>` : "";
  const why = p.why ? `<div class="why">“${p.why}”</div>` : "";
  const price = p.price ? ` · ${p.price}` : "";
  return `<div class="card">
    <span class="tag ${p.type}">${p.emoji} ${p.type}</span>
    <h3>${p.name}</h3>
    <div class="meta">${p.cat}${price}</div>
    ${known}${why}
    <div class="addr">${p.addr}</div>
    <div class="btns">
      <a class="btn" href="${dirUrl(p)}" target="_blank" rel="noopener">Directions</a>
      <a class="btn sec" href="${gmapUrl(p)}" target="_blank" rel="noopener">Google</a>
    </div>
  </div>`;
}

const markers = PLACES.map(p => {
  const m = L.marker([p.lat,p.lng], {icon: L.divIcon({
    className:"", iconSize:[30,30], iconAnchor:[15,15], popupAnchor:[0,-14],
    html:`<div class="pin ${p.type}">${p.emoji}</div>`})});
  m.__p = p;
  m.bindPopup(popupHtml(p), {maxWidth:280, minWidth:220});
  return m;
});

function render(){
  cluster.clearLayers();
  const q = QUERY.trim().toLowerCase();
  let shown = 0;
  const vis = [];
  for (const m of markers){
    const p = m.__p;
    if (!TYPE_ON[p.type]) continue;
    if (REGION !== "all" && p.region !== REGION) continue;
    if (q && !(p.name.toLowerCase().includes(q) || p.cat.toLowerCase().includes(q) || p.city.toLowerCase().includes(q))) continue;
    vis.push(m); shown++;
  }
  cluster.addLayers(vis);
  document.getElementById("count").textContent = shown + " places";
}

// chips
document.getElementById("chips").addEventListener("click", e => {
  const chip = e.target.closest(".chip"); if(!chip) return;
  if (chip.dataset.type){
    const t = chip.dataset.type; TYPE_ON[t] = !TYPE_ON[t];
    chip.setAttribute("aria-pressed", TYPE_ON[t]);
  } else if (chip.dataset.region){
    REGION = chip.dataset.region;
    document.querySelectorAll(".chip.region").forEach(c =>
      c.setAttribute("aria-pressed", c.dataset.region === REGION));
  }
  render();
});
document.getElementById("q").addEventListener("input", e => { QUERY = e.target.value; render(); });

// locate
let meMarker=null;
document.getElementById("locate").addEventListener("click", () => {
  map.locate({setView:true, maxZoom:15, enableHighAccuracy:true});
});
map.on("locationfound", e => {
  if(meMarker) map.removeLayer(meMarker);
  meMarker = L.circleMarker(e.latlng, {radius:8, color:"#fff", weight:3, fillColor:"#0a84ff", fillOpacity:1}).addTo(map);
});
map.on("locationerror", () => alert("Couldn't get your location. Allow location access and try again."));

render();
</script>
</body>
</html>"""

html = (HTML
        .replace("__LEAFLET_CSS__", LEAFLET_CSS)
        .replace("__CLUSTER_CSS__", CLUSTER_CSS)
        .replace("__LEAFLET_JS__", LEAFLET_JS)
        .replace("__CLUSTER_JS__", CLUSTER_JS)
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
