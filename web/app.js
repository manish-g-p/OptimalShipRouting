/* Nautilus front-end logic */
let map, waveOverlay = null, info = null;
let routeLines = [], routeMarkers = [], wpMarkers = [], flowTimer = null;
let META = null, scenario = "typical";

const DARK_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#0b1a2b" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#7d93b0" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0b1a2b" }] },
  { featureType: "water", elementType: "geometry",
    stylers: [{ color: "#08243d" }] },
  { featureType: "landscape", elementType: "geometry",
    stylers: [{ color: "#0f2033" }] },
  { featureType: "administrative", elementType: "geometry.stroke",
    stylers: [{ color: "#1c3350" }] },
  { featureType: "road", stylers: [{ visibility: "off" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
];

const $ = (id) => document.getElementById(id);

/* Google Maps calls this if the API key is rejected (bad key, referrer
   restriction, or billing not enabled). */
window.__gmAuthFailed = false;
window.gm_authFailure = function () {
  window.__gmAuthFailed = true;
  toast("Google Maps auth failed — check the key's website restriction " +
        "(add http://localhost:8000/*) and that billing is enabled.");
};

function toast(msg) {
  const t = $("toast");
  t.textContent = msg; t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 5000);
}
function loading(on, text) {
  $("loading-text").textContent = text || "Computing optimal route…";
  $("loading").classList.toggle("hidden", !on);
}

/* Google Maps entry point */
window.initApp = async function () {
  const c = { lat: 13.5, lng: 80 };
  map = new google.maps.Map($("map"), {
    center: c, zoom: 5, styles: DARK_STYLE,
    mapTypeControl: true, streetViewControl: false, fullscreenControl: false,
    mapTypeControlOptions: {
      style: google.maps.MapTypeControlStyle.HORIZONTAL_BAR,
      mapTypeIds: ["roadmap", "hybrid"],
      position: google.maps.ControlPosition.TOP_RIGHT,
    },
    zoomControl: true,
    zoomControlOptions: { position: google.maps.ControlPosition.RIGHT_CENTER },
  });
  info = new google.maps.InfoWindow();
  await loadMeta();
  bindUI();
  loadWeather();
};

async function loadMeta() {
  const r = await fetch("/api/meta");
  META = await r.json();
  const vsel = $("vessel"), osel = $("origin"), dsel = $("dest");
  META.vessels.forEach((v) => vsel.add(new Option(v.name, v.name)));
  META.ports.forEach((p) => {
    osel.add(new Option(p.name, p.name));
    dsel.add(new Option(p.name, p.name));
  });
  vsel.value = "Container Ship";
  osel.value = "Cochin (Kerala)";
  dsel.value = "Dubai / Jebel Ali (UAE)";
  updateVesselInfo();
}

function updateVesselInfo() {
  const v = META.vessels.find((x) => x.name === $("vessel").value);
  $("vessel-info").textContent =
    `Service ${v.speed} kn · draft ${v.draft} m · length ${v.length} m`;
}

function bindUI() {
  $("vessel").addEventListener("change", updateVesselInfo);
  document.querySelectorAll("#scenario button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#scenario button")
        .forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      scenario = b.dataset.val;
      loadWeather();
    });
  });
  $("use-waves").addEventListener("change", () => {
    if (waveOverlay) waveOverlay.setMap($("use-waves").checked ? map : null);
  });
  $("go").addEventListener("click", findRoute);
}

async function loadWeather() {
  if (waveOverlay) { waveOverlay.setMap(null); waveOverlay = null; }
  $("legend").classList.add("hidden");
  const live = scenario === "live";
  if (live) loading(true, "Fetching live marine weather…");
  try {
    const r = await fetch(`/api/weather?scenario=${scenario}`);
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    const b = d.bounds;
    const bounds = { north: b.north, south: b.south, east: b.east, west: b.west };
    const url = `/api/weather_image?scenario=${scenario}&t=${Date.now()}`;
    waveOverlay = new google.maps.GroundOverlay(url, bounds, { opacity: 0.6 });
    waveOverlay.setMap($("use-waves").checked ? map : null);
    $("legend-max").textContent = d.max + " m";
    $("legend").classList.remove("hidden");
  } catch (e) {
    toast("Weather: " + e.message);
  } finally {
    if (live) loading(false);
  }
}

function clearRoutes() {
  routeLines.forEach((l) => l.setMap(null)); routeLines = [];
  routeMarkers.forEach((m) => m.setMap(null)); routeMarkers = [];
  wpMarkers.forEach((m) => m.setMap(null)); wpMarkers = [];
  if (flowTimer) { clearInterval(flowTimer); flowTimer = null; }
}

async function findRoute() {
  const algorithms = [];
  if ($("use-dijkstra").checked) algorithms.push("dijkstra");
  if ($("use-astar").checked) algorithms.push("astar");
  if (!algorithms.length) return toast("Pick at least one algorithm.");
  if ($("origin").value === $("dest").value)
    return toast("Origin and destination are the same.");

  loading(true, scenario === "live"
    ? "Fetching live weather + routing…" : "Computing optimal route…");
  $("status").textContent = "";
  try {
    const r = await fetch("/api/route", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: $("origin").value, dest: $("dest").value,
        vessel: $("vessel").value, scenario,
        use_ml: $("use-ml").checked, algorithms,
      }),
    });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    drawResults(d);
  } catch (e) {
    toast("Routing failed: " + e.message);
  } finally {
    loading(false);
  }
}

/* Chaikin corner-cutting: turns the blocky grid path into a smooth,
   realistic-looking ship track (purely visual; stats use the real path). */
function smoothPath(pts, iterations) {
  let p = pts;
  for (let it = 0; it < iterations; it++) {
    if (p.length < 3) break;
    const out = [p[0]];
    for (let i = 0; i < p.length - 1; i++) {
      const a = p[i], b = p[i + 1];
      out.push({ lat: a.lat * 0.75 + b.lat * 0.25, lng: a.lng * 0.75 + b.lng * 0.25 });
      out.push({ lat: a.lat * 0.25 + b.lat * 0.75, lng: a.lng * 0.25 + b.lng * 0.75 });
    }
    out.push(p[p.length - 1]);
    p = out;
  }
  return p;
}

function drawResults(d) {
  clearRoutes();
  const bounds = new google.maps.LatLngBounds();

  const drawLine = (res, color, glow, animate) => {
    if (!res || !res.found) return;
    const raw = res.path.map((p) => ({ lat: p[0], lng: p[1] }));
    const path = smoothPath(raw, 3);
    if (glow) {
      routeLines.push(new google.maps.Polyline({
        path, map, geodesic: true, strokeColor: color,
        strokeOpacity: 0.25, strokeWeight: 11,
      }));
    }
    const line = new google.maps.Polyline({
      path, map, geodesic: true, strokeColor: color,
      strokeOpacity: 0.95, strokeWeight: 4,
    });
    routeLines.push(line);
    path.forEach((p) => bounds.extend(p));
    if (animate) animateFlow(line, color);
  };

  drawLine(d.dijkstra, "#38bdf8", false, false);
  drawLine(d.astar, "#f43f5e", true, true);

  // Weather tooltips along the proposed (or available) route.
  const wpSrc = (d.astar && d.astar.found) ? d.astar
    : (d.dijkstra && d.dijkstra.found ? d.dijkstra : null);
  if (wpSrc) drawWaypoints(wpSrc.waypoints);

  // Endpoint markers.
  const vname = d.vessel || "";
  addMarker(d.origin.lat, d.origin.lon,
    "Origin: " + d.origin.name, "#34d399", SHIP_PATH, vname);
  addMarker(d.dest.lat, d.dest.lon,
    "Destination: " + d.dest.name, "#f43f5e", ANCHOR_PATH, vname);
  bounds.extend({ lat: d.origin.lat, lng: d.origin.lon });
  bounds.extend({ lat: d.dest.lat, lng: d.dest.lon });
  map.fitBounds(bounds, 80);

  renderCards(d);
}

/* A circular badge with a white ship glyph, as an SVG marker icon. */
const SHIP_PATH = "M20 21c-1.39 0-2.78-.47-4-1.32-2.44 1.71-5.56 1.71-8 0C6.78 " +
  "20.53 5.39 21 4 21H2v2h2c1.38 0 2.74-.35 4-.99 2.52 1.29 5.48 1.29 8 0 " +
  "1.26.65 2.62.99 4 .99h2v-2h-2zM3.95 19H4c1.6 0 3.02-.88 4-2 .98 1.12 2.4 " +
  "2 4 2s3.02-.88 4-2c.98 1.12 2.4 2 4 2h.05l1.89-6.68c.08-.26.06-.54-.06-.78" +
  "s-.34-.42-.6-.5L20 10.62V6c0-1.1-.9-2-2-2h-3V1H9v3H6c-1.1 0-2 .9-2 2v4.62l" +
  "-1.29.42c-.26.08-.48.26-.6.5s-.15.52-.06.78L3.95 19zM6 6h12v3.97L12 8 6 " +
  "9.97V6z";

const ANCHOR_PATH = "M17 15l1.55 1.55c-.96 1.69-3.66 3.61-6.55 3.94V10.9c1.16" +
  "-.41 2-1.52 2-2.82 0-1.65-1.35-3-3-3S8 6.43 8 8.08c0 1.3.84 2.4 2 2.82v9.59" +
  "c-2.89-.33-5.59-2.25-6.55-3.94L5 15l-4-3v9l1.24-1.24C4.01 21.11 7.24 23 12 " +
  "23s7.99-1.89 9.76-3.24L23 21v-9l-4 3zM12 6.5c.83 0 1.5.67 1.5 1.5s-.67 1.5" +
  "-1.5 1.5-1.5-.67-1.5-1.5.67-1.5 1.5-1.5z";

function badgeIcon(pathData, color) {
  const svg =
    "<svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' " +
    "viewBox='0 0 48 48'><defs><filter id='sh' x='-40%' y='-40%' " +
    "width='180%' height='180%'><feDropShadow dx='0' dy='1.5' " +
    "stdDeviation='1.6' flood-color='#000' flood-opacity='0.5'/></filter>" +
    "</defs><circle cx='24' cy='24' r='17' fill='" + color +
    "' stroke='#ffffff' stroke-width='3' filter='url(#sh)'/>" +
    "<g transform='translate(11,11)' fill='#ffffff'><path d='" + pathData +
    "'/></g></svg>";
  return {
    url: "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg),
    scaledSize: new google.maps.Size(48, 48),
    anchor: new google.maps.Point(24, 24),
    labelOrigin: new google.maps.Point(24, 61),   // label sits under badge
  };
}

function addMarker(lat, lng, title, color, pathData, labelText) {
  const m = new google.maps.Marker({
    position: { lat, lng }, map, title, zIndex: 999,
    icon: badgeIcon(pathData, color),
    label: labelText ? {
      text: labelText, className: "map-label", color: "#ffffff",
      fontSize: "11px", fontWeight: "600",
    } : undefined,
  });
  routeMarkers.push(m);
}

function drawWaypoints(wps) {
  wps.forEach((w) => {
    const color = w.swh < 1.5 ? "#34d399" : w.swh < 3 ? "#fbbf24" : "#f43f5e";
    const m = new google.maps.Marker({
      position: { lat: w.lat, lng: w.lon }, map,
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 4.5,
        fillColor: color, fillOpacity: 0.95, strokeColor: "#0b1220",
        strokeWeight: 1 },
    });
    m.addListener("click", () => {
      info.setContent(
        `<div class="wx-pop"><b>Wave conditions</b>` +
        `Height: ${w.swh} m<br>Period: ${w.mwp} s<br>From: ${w.mwd}°</div>`);
      info.open(map, m);
    });
    wpMarkers.push(m);
  });
}

function animateFlow(line, color) {
  const icons = [{
    icon: { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 3,
      strokeColor: "#fff", fillColor: color, fillOpacity: 1 },
    offset: "0%",
  }];
  line.set("icons", icons);
  let off = 0;
  flowTimer = setInterval(() => {
    off = (off + 1) % 200;
    icons[0].offset = (off / 2) + "%";
    line.set("icons", icons);
  }, 60);
}

function fmt(n) { return n.toLocaleString(undefined, { maximumFractionDigits: 0 }); }

function card(name, tag, cls, res) {
  if (!res || !res.found)
    return `<div class="card ${cls}"><div class="card-title"><b>${name}</b>
      <span>${tag}</span></div><div class="metric"><div class="v">—</div>
      <div class="k">no safe route</div></div></div>`;
  return `<div class="card ${cls}">
    <div class="card-title"><b>${name}</b><span>${tag}</span></div>
    <div class="metrics">
      <div class="metric"><div class="v">${fmt(res.distance_km)}</div><div class="k">km</div></div>
      <div class="metric"><div class="v">${fmt(res.time_hours)}</div><div class="k">hours</div></div>
      <div class="metric"><div class="v">${res.max_wave_m}</div><div class="k">max wave m</div></div>
      <div class="metric"><div class="v">${res.min_coast_km}</div><div class="k">min coast km</div></div>
      <div class="metric"><div class="v">${fmt(res.expanded)}</div><div class="k">cells explored</div></div>
      <div class="metric"><div class="v">${(res.time_hours/24).toFixed(1)}</div><div class="k">days</div></div>
    </div></div>`;
}

function renderCards(d) {
  let html = "";
  if (d.dijkstra) html += card("Dijkstra", "traditional", "dijkstra", d.dijkstra);
  if (d.astar) html += card("Weather-aware A*", "proposed", "astar", d.astar);
  $("cards").innerHTML = html;

  let verdict = "";
  if (d.dijkstra && d.astar && d.dijkstra.found && d.astar.found) {
    const dd = d.astar.distance_km - d.dijkstra.distance_km;
    const wd = d.dijkstra.max_wave_m - d.astar.max_wave_m;
    const eff = Math.round(100 * (1 - d.astar.expanded / d.dijkstra.expanded));
    if (Math.abs(dd) < 1 && Math.abs(wd) < 0.05) {
      verdict = `For this vessel and sea state, the shortest route is already ` +
        `the safest. A* reached the same route while exploring ${eff}% fewer cells.`;
    } else {
      verdict = `A* trades ${dd >= 0 ? "+" : ""}${fmt(dd)} km to cut peak waves ` +
        `by ${wd.toFixed(2)} m — calmer, safer water — and explored ${eff}% ` +
        `fewer cells than Dijkstra.`;
    }
  }
  $("verdict").textContent = verdict;
  $("results").classList.remove("hidden");
}
