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

def slug(name, lat, lng):
    """Stable filename for a place's cached photo. MUST match fetch_photos.py."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"{s}-{round(lat, 4)}_{round(lng, 4)}"

PHOTO_DIR = os.path.join(HERE, "photos")

def photo_for(name, lat, lng):
    """Relative URL if a cached photo exists (from fetch_photos.py), else ''."""
    fn = slug(name, lat, lng) + ".jpg"
    return f"photos/{fn}" if os.path.exists(os.path.join(PHOTO_DIR, fn)) else ""

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
            "photo": photo_for(row["name"].strip(), lat, lng),
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
.card .photo{width:100%;height:132px;object-fit:cover;border-radius:12px;margin:0 0 10px;
  display:block;background:var(--line)}
.card h3{margin:0 0 2px;font-size:17px;letter-spacing:-.01em}
.card .meta{color:var(--sub);font-size:13px;margin-bottom:6px}
.card .addr{color:var(--sub);font-size:12px;margin:6px 0 10px}
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
let VIS = [];   // markers currently shown (set each render, used by declutter)

// --- visited state (saved on THIS device only) ---
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
  inertia:true, inertiaDeceleration:2200, inertiaMaxSpeed:3200, easeLinearity:0.22,
}).setView([34.06,-118.30], 11);
L.control.zoom({position:"bottomleft"}).addTo(map);

// --- Apple-style custom vector basemap (MapLibre GL, via maplibre-gl-leaflet) ---
// Free OpenFreeMap 'positron' vector tiles restyled to our palette: grey land/roads,
// green parks, blue water, and PURPLE shopping/commercial districts. Light & dark.
const darkUI = window.matchMedia("(prefers-color-scheme: dark)").matches;
const PAL = darkUI ? {
  land:"#23262b", landuse:"#282b30", park:"#213d29", building:"#2c3037",
  water:"#183a4e", road:"#3e434b", casing:"#2a2e35", boundary:"#474c54",
  commercial:"rgba(128,98,170,.42)", label:"#c7ccd3", halo:"#141619"
} : {
  land:"#eeeeec", landuse:"#e7e6e3", park:"#cfe6c5", building:"#e2e1dd",
  water:"#a7d3e8", road:"#ffffff", casing:"#dddbd6", boundary:"#ceccc7",
  commercial:"rgba(150,120,205,.32)", label:"#5b6067", halo:"#ffffff"
};

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
        else if(sl === "building") m.setPaintProperty(id, "fill-color", PAL.building);
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

function popupHtml(p){
  const photo = p.photo ? `<img class="photo" src="${p.photo}" alt="" loading="lazy">` : "";
  const known = p.known ? `<div class="known"><b>Known for:</b> ${esc(p.known)}</div>` : "";
  const why = p.why ? `<div class="why">“${esc(p.why)}”</div>` : "";
  const price = p.price ? ` · ${esc(p.price)}` : "";
  const on = VISITED[pkey(p)] ? " on" : "";
  return `<div class="card">
    ${photo}
    <span class="tag ${p.type}">${p.emoji} ${p.type}</span>
    <h3>${esc(p.name)}</h3>
    <div class="meta">${esc(p.cat)}${price}</div>
    ${known}${why}
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
  m.bindPopup(popupHtml(p), {maxWidth:300, minWidth:230});
  byKey[pkey(p)] = m;
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
  VIS = vis;
  cluster.addLayers(vis);
  document.getElementById("count").textContent = shown + " places";
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

# Mirror cached photos into deploy/ so the served build can show them.
if os.path.isdir(PHOTO_DIR):
    dst = os.path.join(deploy_dir, "photos")
    shutil.copytree(PHOTO_DIR, dst, dirs_exist_ok=True)
    n = len([f for f in os.listdir(PHOTO_DIR) if f.endswith(".jpg")])
    print(f"Copied {n} photos -> {dst}")
else:
    print("No photos/ yet — run fetch_photos.py to add food photos (see README).")
