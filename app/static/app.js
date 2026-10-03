/* ================================================================
   AirRoute Kraków — app.js
   Talks to the Flask backend (roles/04 §4.4):
     POST /api/route, GET /api/scenarios, /api/conditions, /api/layers/shade
   Without data the backend still answers on mocks: `make mock`.
   ================================================================ */

"use strict";

// ── CONSTANTS ────────────────────────────────────────────────────
const API = "/api";
const MAX_POINTS = 5;            // API limit: start, up to 3 via points, end
const SHADE_MIN_ZOOM = 14;       // the discomfort map is street-level; below this the bbox is too big

const ROUTE_STYLE = {            // fastest under, healthier on top; width also tells them apart
  fastest: { weight: 4, dashArray: "8, 8", rank: 0 },
  eco:     { weight: 7, dashArray: null,   rank: 1 },
};

const REASON_LABELS = { ok: "Comfortable", heat: "Heat stress", air: "Air pollution", uv: "Strong UV" };
const SOURCE_LABELS = { live: "live data", scenario: "scenario data", fallback: "⚠ offline fallback", mock: "mock data" };

// ── MAP INIT ─────────────────────────────────────────────────────
const map = L.map("map", { preferCanvas: true }).setView([50.0614, 19.9366], 13);

// CARTO basemaps now need an API key (tiles say "API KEY REQUIRED"); OSM is the fallback from roles/05.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

// The discomfort map sits under the routes.
map.createPane("shadePane").style.zIndex = 350;
const shadeRenderer = L.canvas({ pane: "shadePane" });

// City boundary exported by the graph pipeline (Role 1); routing works only inside it.
fetch("krakow_boundary.geojson")
  .then((r) => (r.ok ? r.json() : null))
  .then((gj) => gj && L.geoJSON(gj, {
    style: { color: "#7c3aed", weight: 1.5, dashArray: "4, 6", fill: false },
    interactive: false,
  }).addTo(map))
  .catch(() => {});

// ── STATE ─────────────────────────────────────────────────────────
const state = {
  waypoints: [],    // [{lat, lng}]
  markers: [],      // Leaflet markers
  routeLayers: {},  // {id: L.FeatureGroup}
  lastResult: null, // last /api/route response
  activeRoute: "eco",
  fitNext: true,    // zoom to the routes after waypoints change, not after slider/profile changes
  scenarios: [],
  shadeLayer: null,
  debounceTimer: null,
  shadeTimer: null,
  reqId: 0,         // Prevent async race conditions
  shadeReqId: 0,
};

// ── HELPERS ───────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const pad = (n) => String(n).padStart(2, "0");
const letter = (i) => String.fromCharCode(65 + i);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function getColorForDiscomfort(val) {
  // 0 (green) -> 5 (yellow) -> 10 (red)
  if (val <= 5) {
    const r = Math.round(255 * (val / 5));
    return `rgb(${r}, 200, 50)`;
  }
  const g = Math.round(200 * (1 - ((val - 5) / 5)));
  return `rgb(255, ${g}, 50)`;
}

function formatPct(val) {
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(0)} %`;
}

// ── MAP CLICK ─────────────────────────────────────────────────────
map.on("click", (e) => addWaypoint(e.latlng));

function addWaypoint(latlng) {
  if (state.waypoints.length >= MAX_POINTS) {
    setStatus(`⚠ Max ${MAX_POINTS} waypoints (start, 3 via points, end)`, "error");
    return;
  }

  const label = letter(state.waypoints.length); // A, B, C…
  const m = L.marker(latlng, { draggable: true })
    .addTo(map)
    .bindTooltip(label, { permanent: true, direction: "top", offset: [0, -12], className: "wp-tooltip" });

  m.on("dragend", () => {
    state.waypoints[state.markers.indexOf(m)] = m.getLatLng();
    state.fitNext = true;
    renderWaypoints();
    debounceFind();
  });

  state.waypoints.push(latlng);
  state.markers.push(m);
  state.fitNext = true;
  renderWaypoints();
  updateButtons();

  if (state.waypoints.length >= 2) debounceFind();
  else refreshConditions();
}

function removeWaypoint(idx) {
  map.removeLayer(state.markers[idx]);
  state.waypoints.splice(idx, 1);
  state.markers.splice(idx, 1);

  // re-label remaining markers
  state.markers.forEach((m, i) => {
    m.unbindTooltip();
    m.bindTooltip(letter(i), { permanent: true, direction: "top", offset: [0, -12], className: "wp-tooltip" });
  });

  state.fitNext = true;
  renderWaypoints();
  updateButtons();

  if (state.waypoints.length >= 2) debounceFind();
  else clearRoutes();
}

function clearAll() {
  state.markers.forEach((m) => map.removeLayer(m));
  state.waypoints = [];
  state.markers = [];
  renderWaypoints();
  updateButtons();
  clearRoutes();
}

// ── SIDEBAR: WAYPOINTS LIST ───────────────────────────────────────
function renderWaypoints() {
  const ol = $("waypoints");
  ol.innerHTML = "";

  state.waypoints.forEach((wp, i) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="wp-label">${letter(i)}</span>
      <span class="wp-coords">${wp.lat.toFixed(4)}, ${wp.lng.toFixed(4)}</span>
      <button class="wp-remove" title="Remove" data-idx="${i}">✕</button>
    `;
    ol.appendChild(li);
  });

  ol.querySelectorAll(".wp-remove").forEach((btn) => {
    btn.addEventListener("click", () => removeWaypoint(+btn.dataset.idx));
  });

  const hint = $("waypointHint");
  if (state.waypoints.length === 0) {
    hint.innerHTML = "📍 Click the map to add a start point.";
    hint.style.display = "";
  } else if (state.waypoints.length === 1) {
    hint.innerHTML = "🏁 Click the map to add a destination.";
    hint.style.display = "";
  } else if (state.waypoints.length < MAX_POINTS) {
    hint.innerHTML = "➕ Click again to add a via point; drag markers to adjust.";
    hint.style.display = "";
  } else {
    hint.style.display = "none";
  }
}

function updateButtons() {
  $("findBtn").disabled = state.waypoints.length < 2;
  $("clearBtn").disabled = state.waypoints.length === 0;
}

// ── SCENARIOS & DEPART SLIDER ─────────────────────────────────────
const departSlider = $("depart");
const departOut = $("departOut");

const currentScenario = () => state.scenarios.find((s) => s.id === $("scenario").value);

async function loadScenarios() {
  try {
    const res = await fetch(`${API}/scenarios`);
    if (!res.ok) throw new Error(res.status);
    state.scenarios = await res.json();
  } catch {
    state.scenarios = [{ id: "live", label: "Live now" }];
    setStatus("⚠ Backend not reachable — start it with make demo (or make mock without data)", "error");
  }
  $("scenario").innerHTML = state.scenarios
    .map((s) => `<option value="${esc(s.id)}">${esc(s.label)}</option>`).join("");
  const heat = state.scenarios.find((s) => s.id.startsWith("heatwave"));
  if (heat) $("scenario").value = heat.id;   // the demo starts with the heatwave
  syncSliderToScenario();
}

function syncSliderToScenario() {
  // A scenario is one recorded day: start at its default hour; live starts now.
  const sc = currentScenario();
  let val;
  if (sc?.default_at) {
    val = 2 * parseInt(sc.default_at.slice(11, 13), 10) + (parseInt(sc.default_at.slice(14, 16), 10) >= 30 ? 1 : 0);
  } else {
    const d = new Date();
    val = 2 * d.getHours() + (d.getMinutes() >= 30 ? 1 : 0);
  }
  departSlider.value = val;
  departOut.textContent = sliderToTime(val);
}

function sliderToTime(val) {
  const h = Math.floor(val / 2);
  const m = val % 2 === 0 ? "00" : "30";
  return `${pad(h)}:${m}`;
}

function departIso() {
  // Scenario: its own date and UTC offset; live: today in the browser's time zone.
  const hhmm = `${sliderToTime(+departSlider.value)}:00`;
  const sc = currentScenario();
  if (sc?.default_at) return `${sc.default_at.slice(0, 10)}T${hhmm}${sc.default_at.slice(19)}`;
  const d = new Date();
  const off = -d.getTimezoneOffset();
  const tz = `${off >= 0 ? "+" : "-"}${pad(Math.floor(Math.abs(off) / 60))}:${pad(Math.abs(off) % 60)}`;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${hhmm}${tz}`;
}

function queryParams() {
  return new URLSearchParams({ scenario: $("scenario").value, at: departIso(), profile: $("profile").value });
}

// ── DEBOUNCED FIND ────────────────────────────────────────────────
function debounceFind() {
  clearTimeout(state.debounceTimer);
  state.debounceTimer = setTimeout(findRoutes, 300);
}

// ── REQUEST BODY ──────────────────────────────────────────────────
function requestBody() {
  return {
    points: state.waypoints.map((p) => ({ lat: +p.lat.toFixed(6), lon: +p.lng.toFixed(6) })),
    profile: $("profile").value,
    scenario: $("scenario").value,
    depart_at: departIso(),
    optimize_order: $("optimize").checked,
  };
}

// ── FIND ROUTES ───────────────────────────────────────────────────
async function findRoutes() {
  if (state.waypoints.length < 2) return;

  const currentReqId = ++state.reqId;
  setStatus('<span class="spinner"></span> Computing…', "loading");

  let res, data;
  try {
    res = await fetch(`${API}/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody()),
    });
    data = await res.json();
  } catch {
    if (currentReqId === state.reqId) setStatus("⚠ Network error — is the backend running?", "error");
    return;
  }
  if (currentReqId !== state.reqId) return;

  if (!res.ok) {
    setStatus("⚠ " + errorText(data), "error");
    return;
  }

  state.lastResult = data;
  drawRoutes(data.routes);
  renderComparison(data);
  renderCards(data);
  setStatus(conditionsLine(data.conditions, data.sun) + ` · computed in ${Math.round(data.timing_ms.total)} ms`);
}

function errorText(d) {
  if (d.error === "point_outside_area") {
    const i = d.detail?.index;
    return `Point ${i != null ? letter(i) + " " : ""}is too far from the Kraków bike network — move it closer to a street.`;
  }
  if (d.error === "validation" && Array.isArray(d.detail)) {
    const p = d.detail.find((e) => e.loc?.[0] === "points" && Number.isInteger(e.loc[1]));
    if (p) return `Point ${letter(p.loc[1])} is outside Kraków.`;
  }
  return {
    no_route: "No bike route between these points.",
    validation: "Invalid request.",
    internal: "Server error — see the backend log.",
  }[d.error] ?? "Server error.";
}

// ── DRAW ROUTES ───────────────────────────────────────────────────
function drawRoutes(routes) {
  Object.values(state.routeLayers).forEach((l) => map.removeLayer(l));
  state.routeLayers = {};

  // Fastest first, the active route last so it ends up on top
  const ordered = [...routes].sort((a, b) =>
    (a.id === state.activeRoute) - (b.id === state.activeRoute) || (ROUTE_STYLE[a.id]?.rank ?? 0) - (ROUTE_STYLE[b.id]?.rank ?? 0));

  for (const r of ordered) {
    const isActive = r.id === state.activeRoute;
    const style = ROUTE_STYLE[r.id] ?? { weight: 5, dashArray: null };
    const layerGroup = L.featureGroup();

    if (isActive && r.segments?.length) {
      // Segments coloured by discomfort explain where and why the ride is uncomfortable
      const coords = r.geometry.coordinates;
      L.geoJSON(r.geometry, { style: { color: "#fff", weight: style.weight + 4, opacity: 0.9 } }).addTo(layerGroup);
      for (const seg of r.segments) {
        const latLngs = coords.slice(seg.from, seg.to + 1).map((c) => [c[1], c[0]]);
        L.polyline(latLngs, { color: getColorForDiscomfort(seg.discomfort * 10), weight: style.weight + 1, opacity: 0.95 })
          .bindTooltip(`${esc(r.label)}: ${REASON_LABELS[seg.reason] ?? esc(seg.reason)} · discomfort ${(seg.discomfort * 10).toFixed(1)}/10`,
            { className: "segment-tooltip", sticky: true })
          .addTo(layerGroup);
      }
    } else {
      L.geoJSON(r.geometry, {
        style: { color: r.color, weight: style.weight, opacity: isActive ? 1.0 : 0.45, dashArray: style.dashArray },
      })
        .bindTooltip(`${esc(r.label)}: ${r.metrics.time_min} min · ${(r.metrics.distance_m / 1000).toFixed(1)} km`, { sticky: true })
        .addTo(layerGroup);
    }

    layerGroup.on("click", () => activateCard(r.id));
    layerGroup.addTo(map);
    state.routeLayers[r.id] = layerGroup;
  }

  if (state.fitNext) {
    const bounds = L.featureGroup(Object.values(state.routeLayers)).getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
    state.fitNext = false;
  }
}

function clearRoutes() {
  Object.values(state.routeLayers).forEach((l) => map.removeLayer(l));
  state.routeLayers = {};
  state.lastResult = null;
  $("cards").innerHTML = "";
  $("cardsSection").style.display = "none";
  $("comparisonSection").style.display = "none";
  refreshConditions();
}

// ── COMPARISON ────────────────────────────────────────────────────
function renderComparison(data) {
  const c = data.comparison;
  const el = $("comparison");
  const order = data.order ?? [];
  const reordered = order.some((v, i) => v !== i);
  const orderHtml = reordered
    ? `<p class="comparison-note">Visiting order: ${order.map(letter).join(" → ")}</p>`
    : "";

  if (c.same_route) {
    el.innerHTML = `<p class="comparison-same">✓ The fastest route is already the healthiest right now.</p>${orderHtml}`;
  } else {
    const row = (label, value, good) =>
      `<span class="card-metric-label">${label}</span><span class="card-metric-val ${good == null ? "" : good ? "good" : "bad"}">${value}</span>`;
    el.innerHTML = `
      <div class="card-metrics">
        ${row("Extra time", `+${c.time_delta_min.toFixed(1)} min (${formatPct(c.time_delta_pct)})`, null)}
        ${row("PM2.5 inhaled", formatPct(c.pm25_dose_delta_pct), c.pm25_dose_delta_pct <= 0)}
        ${row("Shade", `${c.shade_delta_pp >= 0 ? "+" : ""}${c.shade_delta_pp.toFixed(0)} pp`, c.shade_delta_pp >= 0)}
        ${row("Heat stress", `${c.heat_stress_delta_min >= 0 ? "+" : ""}${c.heat_stress_delta_min.toFixed(1)} min`, c.heat_stress_delta_min <= 0)}
      </div>${orderHtml}`;
  }
  $("comparisonSection").style.display = "";
}

// ── RENDER CARDS ──────────────────────────────────────────────────
function renderCards(data) {
  const container = $("cards");
  container.innerHTML = "";
  const c = data.comparison;
  const fastest = data.routes.find((r) => r.id === "fastest");

  for (const r of data.routes) {
    const m = r.metrics;
    const isFastest = r.id === "fastest";
    const card = document.createElement("div");
    card.className = "route-card" + (r.id === state.activeRoute ? " active" : "");
    card.dataset.id = r.id;
    card.style.color = r.color;

    const timeDiff = !isFastest && !c.same_route
      ? ` <span style="color:var(--color-muted)">(${formatPct(c.time_delta_pct)})</span>`
      : "";
    const dose = m.pm25_dose_ug == null ? "—" : `${m.pm25_dose_ug.toFixed(1)} µg`;
    const doseDiff = !isFastest && !c.same_route && fastest?.metrics.pm25_dose_ug
      ? ` (${formatPct(c.pm25_dose_delta_pct)})` : "";
    const avoidHtml = r.avoids?.length
      ? `<div class="card-avoids">⚠ Avoids: ${r.avoids.map(esc).join("; ")}</div>`
      : "";

    card.innerHTML = `
      <div class="card-header">
        <span class="card-dot" style="background:${r.color}"></span>
        <span class="card-title">${esc(r.label)}</span>
        <span class="card-subtitle">${(m.distance_m / 1000).toFixed(1)} km · ${m.time_min} min${timeDiff}</span>
      </div>
      <div class="card-metrics">
        <span class="card-metric-label">PM2.5 inhaled</span>
        <span class="card-metric-val ${!isFastest && c.pm25_dose_delta_pct < 0 ? "good" : ""}">${dose}${doseDiff}</span>
        <span class="card-metric-label">Shade</span>
        <span class="card-metric-val">${m.shade_pct.toFixed(0)}%</span>
        <span class="card-metric-label">Heat stress</span>
        <span class="card-metric-val">${m.heat_stress_min} min</span>
        <span class="card-metric-label">Discomfort</span>
        <span class="card-metric-val ${m.avg_discomfort > 6 ? "bad" : m.avg_discomfort < 4 ? "good" : ""}">${m.avg_discomfort.toFixed(1)}/10</span>
      </div>
      ${avoidHtml}
    `;

    card.addEventListener("click", () => activateCard(r.id));
    container.appendChild(card);
  }

  $("cardsSection").style.display = "";
}

function activateCard(id) {
  state.activeRoute = id;
  document.querySelectorAll(".route-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.id === id);
  });
  // Redraw map layers to show detailed segments for the active route
  if (state.lastResult) drawRoutes(state.lastResult.routes);
}

// ── DISCOMFORT MAP (GET /api/layers/shade) ────────────────────────
function debounceShade() {
  clearTimeout(state.shadeTimer);
  state.shadeTimer = setTimeout(loadShadeLayer, 300);
}

function removeShadeLayer() {
  if (state.shadeLayer) map.removeLayer(state.shadeLayer);
  state.shadeLayer = null;
}

async function loadShadeLayer() {
  const on = $("shadeLayer").checked;
  const tooFar = map.getZoom() < SHADE_MIN_ZOOM;
  $("legend").hidden = !on;
  $("legendScale").hidden = tooFar;
  $("legendHint").hidden = !tooFar;
  if (!on || tooFar) { removeShadeLayer(); return; }

  const reqId = ++state.shadeReqId;
  const b = map.getBounds();
  const params = queryParams();
  params.set("bbox", [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(5)).join(","));
  let gj;
  try {
    const res = await fetch(`${API}/layers/shade?${params}`);
    if (!res.ok) return;
    gj = await res.json();
  } catch {
    return;
  }
  if (reqId !== state.shadeReqId || !$("shadeLayer").checked) return;

  removeShadeLayer();
  state.shadeLayer = L.geoJSON(gj, {
    renderer: shadeRenderer,
    pane: "shadePane",
    style: (f) => ({ color: getColorForDiscomfort(f.properties.discomfort * 10), weight: 3, opacity: 0.75 }),
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindTooltip(`${esc(p.name ?? "Unnamed way")} · shade ${Math.round(p.shade * 100)}% · ` +
        `${REASON_LABELS[p.reason] ?? p.reason} · discomfort ${(p.discomfort * 10).toFixed(1)}/10`, { sticky: true });
    },
  }).addTo(map);
}

// ── CONDITIONS LINE ───────────────────────────────────────────────
function conditionsLine(c, sun) {
  if (!c) return "";
  const parts = [];
  if (c.temperature_c != null) parts.push(`${c.temperature_c.toFixed(1)}°C`);
  if (c.uv_index != null) parts.push(`UV ${c.uv_index.toFixed(1)}`);
  if (c.pm25 != null) parts.push(`PM2.5 ${Math.round(c.pm25)} µg/m³`);
  if (c.pm10 != null) parts.push(`PM10 ${Math.round(c.pm10)} µg/m³`);
  if (sun?.elevation_deg != null) parts.push(sun.elevation_deg > 0 ? `sun ${Math.round(sun.elevation_deg)}°` : "night");
  if (SOURCE_LABELS[c.source]) parts.push(SOURCE_LABELS[c.source]);
  if (c.source !== "scenario" && c.data_age_s > 3600) parts.push(`data age ${Math.round(c.data_age_s / 3600)} h`);
  return parts.join(" · ");
}

async function refreshConditions() {
  // Without a route the footer still shows the conditions for the chosen scenario and hour.
  if (state.waypoints.length >= 2) return;
  const reqId = ++state.reqId;
  try {
    const res = await fetch(`${API}/conditions?${queryParams()}`);
    if (!res.ok || reqId !== state.reqId) return;
    const c = await res.json();
    const hint = state.waypoints.length ? "🏁 Click the map to add a destination." : "📍 Click the map to add a start point.";
    setStatus(`${conditionsLine(c, c.sun)} · ${hint}`);
  } catch {
    /* the scenario loader already reported an unreachable backend */
  }
}

// ── STATUS ────────────────────────────────────────────────────────
function setStatus(html, cls = "") {
  const footer = $("status");
  // Wrap in span so the CSS #status > * ellipsis rule fires
  footer.innerHTML = `<span>${html}</span>`;
  footer.className = cls;
}

// ── DEMO ROUTE ────────────────────────────────────────────────────
// Kazimierz → Rondo Mogilskie → Nowa Huta in the heatwave: ECO trades a few minutes for a lot of shade.
const DEMO_WAYPOINTS = [
  { lat: 50.0510, lng: 19.9450 }, // Kazimierz, plac Nowy
  { lat: 50.0720, lng: 20.0370 }, // Nowa Huta, plac Centralny
];

function loadDemoRoute() {
  clearAll();
  const heat = state.scenarios.find((s) => s.id.startsWith("heatwave"));
  if (heat) $("scenario").value = heat.id;
  $("profile").value = "senior";
  syncSliderToScenario();
  DEMO_WAYPOINTS.forEach((latlng) => addWaypoint(latlng));
}

// ── INIT ──────────────────────────────────────────────────────────
function onConditionsChange() {
  if (state.waypoints.length >= 2) debounceFind();
  else refreshConditions();
  if ($("shadeLayer").checked) debounceShade();
}

departSlider.addEventListener("input", () => {
  departOut.textContent = sliderToTime(+departSlider.value);
  onConditionsChange();
});
$("scenario").addEventListener("change", () => {
  syncSliderToScenario();
  onConditionsChange();
});
$("profile").addEventListener("change", onConditionsChange);
$("optimize").addEventListener("change", () => state.waypoints.length >= 2 && debounceFind());
$("shadeLayer").addEventListener("change", loadShadeLayer);
map.on("moveend", () => $("shadeLayer").checked && debounceShade());

$("findBtn").addEventListener("click", findRoutes);
$("clearBtn").addEventListener("click", clearAll);
$("demoBtn").addEventListener("click", loadDemoRoute);

renderWaypoints();
updateButtons();
loadScenarios().then(refreshConditions);
