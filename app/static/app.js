/* ================================================================
   BiKing — app.js
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

// ── COLOUR-VISION MODES ───────────────────────────────────────────
// Discomfort scale (comfortable -> uncomfortable) and route colours per mode. The colour-blind scales
// avoid red vs green (or blue vs yellow) and keep the healthier route in the "comfortable" colour.
// `dark` overrides keep the lines visible on the dark map (dark greys and black would vanish there).
const PALETTES = {
  default:    { label: "Default colours", hint: "",
                scale: ["#00c832", "#ffc832", "#ff0032"], fastest: null, eco: null,
                dark: { fastest: "#9ca3af", eco: "#22c55e" } },
  redgreen:   { label: "Red–green safe", hint: "protanopia, deuteranopia",
                scale: ["#2166ac", "#b2abd2", "#e66101"], fastest: "#3f3f3f", eco: "#2166ac",
                dark: { scale: ["#4393c3", "#b2abd2", "#f4a259"], fastest: "#bdbdbd", eco: "#4393c3" } },
  blueyellow: { label: "Blue–yellow safe", hint: "tritanopia",
                scale: ["#018571", "#a6a6a6", "#d01c8b"], fastest: "#3f3f3f", eco: "#018571",
                dark: { scale: ["#5ab4ac", "#a6a6a6", "#e7298a"], fastest: "#bdbdbd", eco: "#5ab4ac" } },
  greyscale:  { label: "Greyscale", hint: "no colour vision, printing",
                scale: ["#d4d4d4", "#7a7a7a", "#000000"], fastest: "#8c8c8c", eco: "#000000",
                dark: { scale: ["#4d4d4d", "#a3a3a3", "#ffffff"], fastest: "#8c8c8c", eco: "#ffffff" } },
};
const CVD_KEY = "biking.colourVision";
const THEME_KEY = "biking.theme";
const TEXT_KEY = "biking.textSize";
const CONTRAST_KEY = "biking.contrast";
const MOTION_KEY = "biking.motion";

const highContrast = () => document.documentElement.dataset.contrast === "high";
const reducedMotion = () => document.documentElement.dataset.motion === "reduce";
const store = {   // per-browser preferences; storage may be blocked (private mode)
  get: (key) => { try { return localStorage.getItem(key); } catch { return null; } },
  set: (key, value) => { try { localStorage.setItem(key, value); } catch { /* not remembered */ } },
};

// Screen readers hear results and errors from a hidden live region (the footer changes too often)
function announce(text) {
  const live = $("srLive");
  live.textContent = "";
  setTimeout(() => { live.textContent = text; }, 50);
}

const isDark = () => document.documentElement.dataset.theme === "dark";
const palette = () => {
  const p = PALETTES[document.body.dataset.cvd] ?? PALETTES.default;
  return isDark() ? { ...p, ...p.dark } : p;
};
const routeColor = (r) => palette()[r.id] ?? r.color;
const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

function getColorForDiscomfort(val) {
  // 0 (comfortable) -> 5 -> 10 (uncomfortable), linear between the palette's three stops
  const [a, b, c] = palette().scale.map(hexToRgb);
  const t = Math.min(Math.max(val / 10, 0), 1);
  const [from, to, u] = t <= 0.5 ? [a, b, t * 2] : [b, c, t * 2 - 1];
  return `rgb(${from.map((x, i) => Math.round(x + (to[i] - x) * u)).join(", ")})`;
}

function formatPct(val) {
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(0)} %`;
}

// ── LOADING ANIMATION ─────────────────────────────────────────────
// Shown over the map only when a request takes longer than LOADER_DELAY_MS (cached answers come back in
// ~50 ms), then kept for at least LOADER_MIN_MS so it never just flickers.
const LOADER_DELAY_MS = 150;
const LOADER_MIN_MS = 400;
const loader = { pending: 0, timer: null, shownAt: 0 };
map.getContainer().appendChild($("loader"));

function startLoading(text) {
  $("loaderText").textContent = text;
  if (loader.pending++ > 0) return;
  loader.timer = setTimeout(() => {
    $("loader").hidden = false;
    loader.shownAt = performance.now();
  }, LOADER_DELAY_MS);
}

function stopLoading() {
  loader.pending = Math.max(0, loader.pending - 1);
  if (loader.pending) return;
  clearTimeout(loader.timer);
  const left = loader.shownAt ? LOADER_MIN_MS - (performance.now() - loader.shownAt) : 0;
  setTimeout(() => {
    if (loader.pending) return;
    $("loader").hidden = true;
    loader.shownAt = 0;
  }, Math.max(0, left));
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
      <button class="wp-remove" title="Remove" aria-label="Remove point ${letter(i)}" data-idx="${i}">✕</button>
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
  startLoading("Starting BiKing…");
  try {
    const res = await fetch(`${API}/scenarios`);
    if (!res.ok) throw new Error(res.status);
    state.scenarios = await res.json();
  } catch {
    state.scenarios = [{ id: "live", label: "Live now" }];
    setStatus("⚠ Backend not reachable — start it with make demo (or make mock without data)", "error");
  } finally {
    stopLoading();
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

// ── ADVANCED OPTIONS: which factors the healthier route avoids ───
const FACTOR_LABELS = { heat: "heat", air: "air", uv: "UV" };
const factorBoxes = () => [...document.querySelectorAll('input[name="factor"]')];
const selectedFactors = () => factorBoxes().filter((b) => b.checked).map((b) => b.value);

function onFactorChange(e) {
  if (!selectedFactors().length) {        // the healthier route needs at least one thing to avoid
    e.target.checked = true;
    setStatus("At least one factor must stay on — otherwise the healthier route is just the fastest one.");
    return;
  }
  const chosen = selectedFactors();
  const badge = $("factorsBadge");
  badge.hidden = chosen.length === factorBoxes().length;
  badge.textContent = chosen.map((f) => FACTOR_LABELS[f]).join(" + ") + " only";
  if (state.waypoints.length >= 2) debounceFind();
}

// ── REQUEST BODY ──────────────────────────────────────────────────
function requestBody() {
  return {
    points: state.waypoints.map((p) => ({ lat: +p.lat.toFixed(6), lon: +p.lng.toFixed(6) })),
    profile: $("profile").value,
    scenario: $("scenario").value,
    depart_at: departIso(),
    optimize_order: $("optimize").checked,
    factors: selectedFactors(),
  };
}

// ── FIND ROUTES ───────────────────────────────────────────────────
async function findRoutes() {
  if (state.waypoints.length < 2) return;
  startLoading("Finding healthier routes…");
  try {
    await computeRoutes();
  } finally {
    stopLoading();
  }
}

async function computeRoutes() {
  const currentReqId = ++state.reqId;
  setStatus('<span class="spinner"></span> Computing…', "loading");

  const body = requestBody();
  let res, data;
  try {
    res = await fetch(`${API}/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    data = await res.json();
  } catch {
    if (currentReqId === state.reqId) setStatus("⚠ Network error — is the backend running?", "error");
    return;
  }
  if (currentReqId !== state.reqId) return;

  if (!res.ok) {
    setStatus("⚠ " + errorText(data), "error");
    announce(errorText(data));
    return;
  }

  state.lastResult = data;
  state.lastRequest = body;
  if (window.speechSynthesis?.speaking) speechSynthesis.cancel();   // never read out an old route
  drawRoutes(data.routes);
  renderComparison(data);
  renderHealthTips(data);
  renderCards(data);
  announce(`Routes ready. ${summarySentences(data).slice(0, 3).join(" ")}`);
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
    const base = ROUTE_STYLE[r.id] ?? { weight: 5, dashArray: null };
    const style = { ...base, weight: base.weight + (highContrast() ? 3 : 0) };
    const layerGroup = L.featureGroup();

    if (isActive && r.segments?.length) {
      // Segments coloured by discomfort explain where and why the ride is uncomfortable
      const coords = r.geometry.coordinates;
      const casing = isDark() ? "#0f172a" : "#fff";   // separates the coloured segments from the map
      L.geoJSON(r.geometry, { style: { color: casing, weight: style.weight + 4, opacity: 0.9 } }).addTo(layerGroup);
      for (const seg of r.segments) {
        const latLngs = coords.slice(seg.from, seg.to + 1).map((c) => [c[1], c[0]]);
        L.polyline(latLngs, { color: getColorForDiscomfort(seg.discomfort * 10), weight: style.weight + 1, opacity: 0.95 })
          .bindTooltip(`${esc(r.label)}: ${REASON_LABELS[seg.reason] ?? esc(seg.reason)} · discomfort ${(seg.discomfort * 10).toFixed(1)}/10`,
            { className: "segment-tooltip", sticky: true })
          .addTo(layerGroup);
      }
    } else {
      L.geoJSON(r.geometry, {
        style: { color: routeColor(r), weight: style.weight, opacity: isActive ? 1.0 : 0.45, dashArray: style.dashArray },
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
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16, animate: !reducedMotion() });
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

// ── METRIC LABELS (same wording and hover help in cards and comparison) ──
const METRIC_INFO = {
  dose:    ["PM2.5 inhaled", "Fine dust breathed in on this ride: concentration × breathing rate × time"],
  poorAir: ["Poor air", "Minutes with air quality 'poor' or worse (EEA index from PM2.5, PM10 and NO₂)"],
  feels:   ["Feels like", "Average felt temperature on the ride (UTCI: air temperature, sun, wind, humidity)"],
  heat:    ["Heat stress", "Minutes with felt temperature above 32 °C (strong heat stress)"],
  shade:   ["Shade", "Share of the ride in the shade of buildings and trees"],
  uv:      ["High UV", "Minutes in strong sun: UV index 6+ after shade (WHO 'high')"],
  disc:    ["Discomfort", "Heat, air and UV combined for the selected profile (fuzzy model), 0–10"],
};
const metricLabel = (key) => `<span class="card-metric-label" title="${METRIC_INFO[key][1]}">${METRIC_INFO[key][0]}</span>`;
const signed = (v, digits) => `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;
const better = (delta, lowerIsBetter = true) => (delta === 0 ? null : (delta < 0) === lowerIsBetter);

// ── HEALTH TIPS, READ ALOUD, GLOSSARY (plain language) ────────────
// Air categories: the EEA European Air Quality Index (2024 hourly bands, as in the backend). Advice
// paraphrases the EEA health messages, the WHO UV-index guidance and the UTCI heat-stress scale.
const EAQI_LIMITS = { pm25: [5, 15, 50, 90, 140], pm10: [15, 45, 120, 195, 270], no2: [10, 25, 60, 100, 150] };
const AIR_NAMES = ["good", "fair", "moderate", "poor", "very poor", "extremely poor"];
const AIR_ADVICE = {
  general:   ["", "", "fine for most riders; ease off if you notice symptoms.",
              "consider a lighter pace and keep away from busy roads.",
              "consider a shorter ride or public transport.", "avoid riding hard outdoors."],
  sensitive: ["", "", "consider a lighter effort if you notice symptoms.",
              "reduce your effort and avoid busy roads.", "consider postponing the ride.",
              "avoid physical activity outdoors today."],
};
const SENSITIVE_PROFILES = new Set(["asthma", "senior"]);

function airCategory(c) {
  return Math.max(...Object.entries(EAQI_LIMITS).map(([k, limits]) => {
    if (c[k] == null) return 0;
    const i = limits.findIndex((limit) => c[k] <= limit);
    return i === -1 ? limits.length : i;
  }));
}

function healthTips(data, profile) {
  const c = data.conditions;
  const eco = data.routes.find((r) => r.id === "eco")?.metrics ?? {};
  const sensitive = SENSITIVE_PROFILES.has(profile);
  const tips = [];
  const air = airCategory(c);
  if (air >= 2) {
    let tip = `Air is ${AIR_NAMES[air]}: ${AIR_ADVICE[sensitive ? "sensitive" : "general"][air]}`;
    if (profile === "asthma" && air >= 3) tip += " Keep your reliever inhaler with you.";
    tips.push(tip);
  }
  const feels = eco.utci_avg_c ?? c.temperature_c;
  if (feels >= 38) tips.push("Very strong heat stress: drink often, rest in the shade and avoid the midday hours.");
  else if (feels >= 32) tips.push("Strong heat stress: take water and prefer the shaded route.");
  else if (feels >= 26) tips.push("Warm: take water with you.");
  else if (feels < 0) tips.push("Cold: wear layers and cover your hands and ears.");
  if (sensitive && feels >= 32) tips.push("Heat is harder on older riders, children and people with asthma: consider riding early or late.");
  if (c.uv_index >= 8) tips.push("Very high UV: sunscreen, sunglasses and covered arms; shade on the route helps.");
  else if (c.uv_index >= 6) tips.push("High UV: wear sunscreen and sunglasses.");
  else if (c.uv_index >= 3) tips.push("Moderate UV: sunscreen on longer rides.");
  return tips.length ? tips : ["Good conditions for a ride."];
}

function renderHealthTips(data) {
  const tips = healthTips(data, state.lastRequest?.profile ?? $("profile").value);
  $("healthTips").innerHTML = `<strong>Health tips for this ride</strong>
    <ul>${tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
    <small>General guidance based on EEA air-quality and WHO UV advice, not medical advice.</small>`;
}

function summarySentences(data) {
  const c = data.comparison;
  if (c.same_route) return ["The fastest route is already the healthiest right now."];
  const n = (v, digits = 1) => Math.abs(v).toFixed(digits);
  const out = [`The healthier route takes ${n(c.time_delta_min)} minutes longer.`];
  if (c.pm25_dose_delta_pct) out.push(`You breathe in ${n(c.pm25_dose_delta_pct, 0)} percent ${c.pm25_dose_delta_pct < 0 ? "less" : "more"} fine dust.`);
  if (c.air_poor_delta_min) out.push(`${n(c.air_poor_delta_min)} minutes ${c.air_poor_delta_min < 0 ? "less" : "more"} in poor air.`);
  if (c.shade_delta_pp) out.push(`The shaded part of the ride is ${n(c.shade_delta_pp, 0)} percentage points ${c.shade_delta_pp > 0 ? "larger" : "smaller"}.`);
  if (c.utci_delta_c) out.push(`It feels ${n(c.utci_delta_c)} degrees ${c.utci_delta_c < 0 ? "cooler" : "warmer"}.`);
  if (c.uv_high_delta_min) out.push(`${n(c.uv_high_delta_min)} minutes ${c.uv_high_delta_min < 0 ? "less" : "more"} in strong sun.`);
  const avoids = data.routes.find((r) => r.id === "eco")?.avoids ?? [];
  if (avoids.length) out.push(`It avoids ${avoids.map((a) => a.replace(/ \(.*\)$/, "")).join(", ")}.`);
  return out;
}

function toggleSpeech() {
  const btn = $("speakBtn");
  if (speechSynthesis.speaking) { speechSynthesis.cancel(); return; }
  if (!state.lastResult) return;
  const profile = state.lastRequest?.profile ?? $("profile").value;
  const text = [...summarySentences(state.lastResult), ...healthTips(state.lastResult, profile)].join(" ");
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-GB";
  utterance.onend = utterance.onerror = () => btn.setAttribute("aria-pressed", "false");
  btn.setAttribute("aria-pressed", "true");
  speechSynthesis.speak(utterance);
}

function renderGlossary() {
  $("glossary").innerHTML = Object.values(METRIC_INFO)
    .map(([name, text]) => `<dt>${esc(name)}</dt><dd>${esc(text)}</dd>`).join("");
}

// ── COMPARISON ────────────────────────────────────────────────────
function renderComparison(data) {
  const c = data.comparison;
  const el = $("comparison");
  const order = data.order ?? [];
  const reordered = order.some((v, i) => v !== i);
  const orderHtml = (reordered
    ? `<p class="comparison-note">Visiting order: ${order.map(letter).join(" → ")}</p>`
    : "") + (data.factors && data.factors.length < Object.keys(FACTOR_LABELS).length
    ? `<p class="comparison-note">Healthier route avoids ${data.factors.map((f) => FACTOR_LABELS[f]).join(" + ")} only (advanced options).</p>`
    : "");

  if (c.same_route) {
    el.innerHTML = `<p class="comparison-same">✓ The fastest route is already the healthiest right now.</p>${orderHtml}`;
  } else {
    const row = (label, value, good) =>
      `${label}<span class="card-metric-val ${good == null ? "" : good ? "good" : "bad"}">${value}</span>`;
    el.innerHTML = `
      <div class="card-metrics">
        ${row('<span class="card-metric-label">Extra time</span>', `+${c.time_delta_min.toFixed(1)} min (${formatPct(c.time_delta_pct)})`, null)}
        ${row(metricLabel("dose"), formatPct(c.pm25_dose_delta_pct), better(c.pm25_dose_delta_pct))}
        ${row(metricLabel("poorAir"), `${signed(c.air_poor_delta_min, 1)} min`, better(c.air_poor_delta_min))}
        ${row(metricLabel("feels"), `${signed(c.utci_delta_c, 1)} °C`, better(c.utci_delta_c))}
        ${row(metricLabel("heat"), `${signed(c.heat_stress_delta_min, 1)} min`, better(c.heat_stress_delta_min))}
        ${row(metricLabel("shade"), `${signed(c.shade_delta_pp, 0)} pp`, better(c.shade_delta_pp, false))}
        ${row(metricLabel("uv"), `${signed(c.uv_high_delta_min, 1)} min`, better(c.uv_high_delta_min))}
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
    card.style.color = routeColor(r);

    const timeDiff = !isFastest && !c.same_route
      ? ` <span style="color:var(--color-muted)">(${formatPct(c.time_delta_pct)})</span>`
      : "";
    const dose = m.pm25_dose_ug == null ? "—" : `${m.pm25_dose_ug.toFixed(1)} µg`;
    const doseDiff = !isFastest && !c.same_route && fastest?.metrics.pm25_dose_ug
      ? ` (${formatPct(c.pm25_dose_delta_pct)})` : "";
    // A longer detour can mean a higher dose: mark it as worse, not in the route's green
    const doseClass = !doseDiff ? "" : c.pm25_dose_delta_pct < 0 ? "good" : c.pm25_dose_delta_pct > 0 ? "bad" : "";
    const feels = m.utci_avg_c == null ? "—" : `${m.utci_avg_c.toFixed(1)} °C`;
    const avoidHtml = r.avoids?.length
      ? `<div class="card-avoids">⚠ Avoids: ${r.avoids.map(esc).join("; ")}</div>`
      : "";

    card.innerHTML = `
      <div class="card-header">
        <span class="card-dot" style="background:${routeColor(r)}"></span>
        <button type="button" class="card-title" aria-pressed="${r.id === state.activeRoute}"
                aria-label="Show the ${esc(r.label)} route on the map">${esc(r.label)}</button>
        <span class="card-subtitle">${(m.distance_m / 1000).toFixed(1)} km · ${m.time_min} min${timeDiff}</span>
        <button class="card-export" type="button" data-id="${r.id}"
                title="Download this route as GPX for Komoot, Garmin Connect, Strava and other apps">⬇ GPX</button>
      </div>
      <div class="card-metrics">
        ${metricLabel("dose")}<span class="card-metric-val ${doseClass}">${dose}${doseDiff}</span>
        ${metricLabel("poorAir")}<span class="card-metric-val">${m.air_poor_min} min</span>
        ${metricLabel("feels")}<span class="card-metric-val">${feels}</span>
        ${metricLabel("heat")}<span class="card-metric-val">${m.heat_stress_min} min</span>
        ${metricLabel("shade")}<span class="card-metric-val">${m.shade_pct.toFixed(0)}%</span>
        ${metricLabel("uv")}<span class="card-metric-val">${m.uv_high_min} min</span>
        ${metricLabel("disc")}<span class="card-metric-val ${m.avg_discomfort > 6 ? "bad" : m.avg_discomfort < 4 ? "good" : ""}">${m.avg_discomfort.toFixed(1)}/10</span>
      </div>
      ${avoidHtml}
    `;

    card.addEventListener("click", () => activateCard(r.id));
    card.querySelector(".card-export").addEventListener("click", (e) => {
      e.stopPropagation();                 // exporting must not switch the active route
      exportGpx(r.id);
    });
    container.appendChild(card);
  }

  $("cardsSection").style.display = "";
}

function activateCard(id) {
  state.activeRoute = id;
  document.querySelectorAll(".route-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.id === id);
    c.querySelector(".card-title").setAttribute("aria-pressed", String(c.dataset.id === id));
  });
  // Redraw map layers to show detailed segments for the active route
  if (state.lastResult) drawRoutes(state.lastResult.routes);
}

// ── GPX EXPORT ────────────────────────────────────────────────────
// GPX 1.1 track without timestamps or elevation: fitness apps import it as a route to ride (not as a
// recorded activity) and add elevation from their own maps.
function routeToGpx(route, request) {
  const m = route.metrics;
  const scenario = state.scenarios.find((s) => s.id === request.scenario)?.label ?? request.scenario;
  const name = `BiKing – ${route.label} route (${scenario}, ${request.depart_at.slice(11, 16)})`;
  const desc = [
    `${(m.distance_m / 1000).toFixed(1)} km`, `${m.time_min} min`, `profile ${request.profile}`,
    m.pm25_dose_ug != null && `PM2.5 inhaled ${m.pm25_dose_ug.toFixed(1)} µg`, `poor air ${m.air_poor_min} min`,
    m.utci_avg_c != null && `feels like ${m.utci_avg_c.toFixed(1)} °C`, `shade ${m.shade_pct.toFixed(0)}%`,
    `high UV ${m.uv_high_min} min`, route.avoids?.length && `avoids: ${route.avoids.join("; ")}`,
  ].filter(Boolean).join(" · ");
  const wpts = request.points
    .map((p, i) => `  <wpt lat="${p.lat}" lon="${p.lon}"><name>${letter(i)}</name></wpt>`).join("\n");
  const trkpts = route.geometry.coordinates
    .map(([lon, lat]) => `      <trkpt lat="${lat}" lon="${lon}"/>`).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="BiKing" xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>${esc(name)}</name>
    <desc>${esc(desc)}</desc>
  </metadata>
${wpts}
  <trk>
    <name>${esc(name)}</name>
    <desc>${esc(desc)}</desc>
    <type>cycling</type>
    <trkseg>
${trkpts}
    </trkseg>
  </trk>
</gpx>
`;
}

async function exportGpx(routeId) {
  const result = state.lastResult;
  const route = result?.routes.find((r) => r.id === routeId);
  if (!route || !state.lastRequest) return;
  const gpx = routeToGpx(route, state.lastRequest);
  const { scenario, depart_at: departAt } = state.lastRequest;
  const km = (route.metrics.distance_m / 1000).toFixed(1);
  const fileName = `biking-${route.label.toLowerCase()}-${km}km-${scenario}-${departAt.slice(11, 16).replace(":", "")}.gpx`;
  const file = new File([gpx], fileName, { type: "application/gpx+xml" });

  // Phones: the system share sheet sends the file straight to Komoot, Garmin Connect, Strava...
  if (window.matchMedia("(pointer: coarse)").matches && navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: fileName });
      return;
    } catch (err) {
      if (err.name === "AbortError") return;   // the user closed the share sheet
    }
  }
  const url = URL.createObjectURL(file);
  const a = Object.assign(document.createElement("a"), { href: url, download: fileName });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  setStatus(`⬇ ${esc(fileName)} saved — import it in Komoot, Garmin Connect, Strava or another app.`);
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
  startLoading("Loading the discomfort map…");
  try {
    const res = await fetch(`${API}/layers/shade?${params}`);
    if (!res.ok) return;
    gj = await res.json();
  } catch {
    return;
  } finally {
    stopLoading();
  }
  if (reqId !== state.shadeReqId || !$("shadeLayer").checked) return;

  removeShadeLayer();
  state.shadeLayer = L.geoJSON(gj, {
    renderer: shadeRenderer,
    pane: "shadePane",
    style: (f) => ({ color: getColorForDiscomfort(f.properties.discomfort * 10), weight: highContrast() ? 5 : 3,
                     opacity: highContrast() ? 0.95 : 0.75 }),
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

// ── ACCESSIBILITY PANEL (colours, text size, contrast, motion) ───
function setColourVision(mode) {
  if (!PALETTES[mode]) mode = "default";
  document.body.dataset.cvd = mode;
  store.set(CVD_KEY, mode);
  document.querySelectorAll('#cvdOptions input').forEach((i) => { i.checked = i.value === mode; });
  markPanelButton();
  refreshColours();
}

function markPanelButton() {
  const custom = document.body.dataset.cvd !== "default" || highContrast()
    || document.documentElement.style.getPropertyValue("--text-scale") > 1;
  $("a11yBtn").classList.toggle("on", custom);
}

function setTextSize(scale, remember = true) {
  if (!["1", "1.2", "1.4"].includes(String(scale))) scale = "1";
  document.documentElement.style.setProperty("--text-scale", scale);
  document.querySelectorAll('input[name="textSize"]').forEach((i) => { i.checked = i.value === String(scale); });
  if (remember) store.set(TEXT_KEY, scale);
  markPanelButton();
  map.invalidateSize();                    // the sidebar width follows the text size
}

function setContrast(high, remember = true) {
  document.documentElement.dataset.contrast = high ? "high" : "normal";
  $("contrastToggle").checked = high;
  if (remember) store.set(CONTRAST_KEY, high ? "high" : "normal");
  markPanelButton();
  refreshColours();                        // thicker route and map lines
}

function setMotion(reduce, remember = true) {
  document.documentElement.dataset.motion = reduce ? "reduce" : "full";
  $("motionToggle").checked = reduce;
  if (remember) store.set(MOTION_KEY, reduce ? "reduce" : "full");
}

function refreshColours() {
  // Everything coloured from palette(): legend, routes, cards and the discomfort map
  document.querySelector(".legend-bar").style.background = `linear-gradient(to right, ${palette().scale.join(", ")})`;
  if (state.lastResult) {
    drawRoutes(state.lastResult.routes);
    renderCards(state.lastResult);
  }
  if (state.shadeLayer) state.shadeLayer.resetStyle();
}

// ── THEME (light / dark) ──────────────────────────────────────────
function setTheme(theme, remember = true) {
  document.documentElement.dataset.theme = theme;
  if (remember) {
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode: the choice just isn't remembered */ }
  }
  const dark = theme === "dark";
  $("themeBtn").textContent = dark ? "☀️" : "🌙";
  $("themeBtn").title = dark ? "Switch to light mode" : "Switch to dark mode";
  $("themeBtn").setAttribute("aria-pressed", String(dark));
  refreshColours();
}

function initTheme() {
  const saved = () => { try { return localStorage.getItem(THEME_KEY); } catch { return null; } };
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  setTheme(saved() ?? (system.matches ? "dark" : "light"), false);
  // Follow the system setting until the user picks a theme with the button
  system.addEventListener("change", (e) => { if (!saved()) setTheme(e.matches ? "dark" : "light", false); });
  $("themeBtn").addEventListener("click", () => setTheme(isDark() ? "light" : "dark"));
}

function initAccessibility() {
  $("cvdOptions").innerHTML = Object.entries(PALETTES).map(([id, p]) => `
    <label class="cvd-option">
      <input type="radio" name="cvd" value="${id}" />
      <span class="cvd-text"><b>${p.label}</b>${p.hint ? `<small>${p.hint}</small>` : ""}</span>
      <span class="cvd-preview" style="background: linear-gradient(to right, ${p.scale.join(", ")})"></span>
    </label>`).join("");
  $("cvdOptions").addEventListener("change", (e) => setColourVision(e.target.value));

  const toggle = (open) => {
    $("a11yPanel").hidden = !open;
    $("a11yBtn").setAttribute("aria-expanded", String(open));
  };
  $("a11yBtn").addEventListener("click", (e) => { e.stopPropagation(); toggle($("a11yPanel").hidden); });
  document.addEventListener("click", (e) => { if (!$("a11yPanel").contains(e.target)) toggle(false); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("a11yPanel").hidden) { toggle(false); $("a11yBtn").focus(); }
  });

  document.querySelectorAll('input[name="textSize"]').forEach((i) => i.addEventListener("change", () => setTextSize(i.value)));
  $("contrastToggle").addEventListener("change", (e) => setContrast(e.target.checked));
  $("motionToggle").addEventListener("change", (e) => setMotion(e.target.checked));

  setColourVision(store.get(CVD_KEY) ?? "default");
  setTextSize(store.get(TEXT_KEY) ?? "1", false);
  setContrast(store.get(CONTRAST_KEY) === "high", false);
  const motion = store.get(MOTION_KEY);   // default: the system "reduce motion" setting
  setMotion(motion ? motion === "reduce" : window.matchMedia("(prefers-reduced-motion: reduce)").matches, false);
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
factorBoxes().forEach((b) => b.addEventListener("change", onFactorChange));
map.on("moveend", () => $("shadeLayer").checked && debounceShade());

$("findBtn").addEventListener("click", findRoutes);
$("clearBtn").addEventListener("click", clearAll);
$("demoBtn").addEventListener("click", loadDemoRoute);

initTheme();
initAccessibility();
renderGlossary();
if ("speechSynthesis" in window) {
  $("speakBtn").hidden = false;
  $("speakBtn").addEventListener("click", toggleSpeech);
}
renderWaypoints();
updateButtons();
loadScenarios().then(refreshConditions);
