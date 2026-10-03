/* ================================================================
   AirRoute Kraków — app.js
   Mock-first: MOCK_RESPONSE mirrors the /api/routes schema exactly.
   Replace findRoutes() fetch body to switch to real backend.
   ================================================================ */

"use strict";

// ── CONSTANTS ────────────────────────────────────────────────────
const API = "/api";

const COLORS = {
  fastest:  "#6b7280",
  balanced: "#7c3aed",
  cleanest: "#16a34a",
};

const ROUTE_LABELS = {
  fastest:  "Fastest",
  balanced: "Balanced",
  cleanest: "Cleanest",
};

// ── MOCK DATA ────────────────────────────────────────────────────
// Realistic Kraków routes: Rynek Główny → AGH Kampus
// LineString coordinates: [lon, lat] (GeoJSON convention)

const MOCK_RESPONSE = {
  order: [0, 1],
  routes: [
    {
      id: "fastest",
      label: "Fastest",
      geometry: {
        type: "LineString",
        coordinates: [
          [19.9366, 50.0614], // Rynek Główny
          [19.9340, 50.0598],
          [19.9310, 50.0576],
          [19.9282, 50.0558],
          [19.9258, 50.0542], // Al. Mickiewicza
          [19.9238, 50.0525],
          [19.9218, 50.0510],
          [19.9196, 50.0492],
          [19.9174, 50.0472], // AGH Campus
        ],
      },
      metrics: {
        distance_m: 6100,
        time_min: 24,
        discomfort_avg: 7.2,
        pm25_dose_ug: 41.0,
        shade_pct: 18,
        heat_stress_min: 9,
      },
      vs_fastest: { time_pct: 0, pm25_dose_pct: 0 },
      avoids: [],
      segments: [],
    },
    {
      id: "balanced",
      label: "Balanced",
      geometry: {
        type: "LineString",
        coordinates: [
          [19.9366, 50.0614], // Rynek Główny
          [19.9380, 50.0600],
          [19.9370, 50.0578],
          [19.9352, 50.0558], // through Planty gardens
          [19.9330, 50.0540],
          [19.9300, 50.0522],
          [19.9270, 50.0506],
          [19.9240, 50.0490],
          [19.9210, 50.0474],
          [19.9185, 50.0468],
          [19.9174, 50.0472], // AGH Campus
        ],
      },
      metrics: {
        distance_m: 7100,
        time_min: 27,
        discomfort_avg: 4.5,
        pm25_dose_ug: 28.0,
        shade_pct: 47,
        heat_stress_min: 4,
      },
      vs_fastest: { time_pct: +12.5, pm25_dose_pct: -31.7 },
      avoids: ["Al. Mickiewicza (heat stress, no shade)"],
      segments: [
        { coords_from: 0, coords_to: 4, discomfort: 2.1, reason: "Shaded park path" },
        { coords_from: 4, coords_to: 7, discomfort: 6.8, reason: "Traffic exposure" },
        { coords_from: 7, coords_to: 10, discomfort: 3.5, reason: "Quiet street" },
      ],
    },
    {
      id: "cleanest",
      label: "Cleanest",
      geometry: {
        type: "LineString",
        coordinates: [
          [19.9366, 50.0614], // Rynek Główny
          [19.9395, 50.0610],
          [19.9400, 50.0585],
          [19.9388, 50.0558], // Planty / Park Jordana approach
          [19.9360, 50.0535],
          [19.9330, 50.0515],
          [19.9295, 50.0498],
          [19.9260, 50.0482],
          [19.9225, 50.0472],
          [19.9196, 50.0468],
          [19.9174, 50.0472], // AGH Campus
        ],
      },
      metrics: {
        distance_m: 7900,
        time_min: 31,
        discomfort_avg: 2.8,
        pm25_dose_ug: 24.0,
        shade_pct: 71,
        heat_stress_min: 2,
      },
      vs_fastest: { time_pct: +29.2, pm25_dose_pct: -41.5 },
      avoids: [
        "Al. Mickiewicza (heat stress, no shade)",
        "Al. Krasińskiego (high PM, no shade)",
      ],
      segments: [
        { coords_from: 0, coords_to: 5, discomfort: 1.5, reason: "Dense park shade" },
        { coords_from: 5, coords_to: 10, discomfort: 2.8, reason: "Low traffic, safe" },
      ],
    },
  ],
  front: [
    { time_min: 24, exposure: 7.2, source: "sweep", supported: true,  route_id: "fastest" },
    { time_min: 27, exposure: 4.5, source: "sweep", supported: true,  route_id: "balanced" },
    { time_min: 31, exposure: 2.8, source: "sweep", supported: true,  route_id: "cleanest" },
    { time_min: 26, exposure: 5.8, source: "sweep", supported: false },
    { time_min: 29, exposure: 3.6, source: "sweep", supported: false },
    { time_min: 33, exposure: 2.2, source: "sweep", supported: false },
  ],
  conditions: {
    temperature_c: 34.5,
    utci: 38,
    uv_index: 8,
    pm10_ugm3: 63,
    pm25_ugm3: 41,
    source: "mock",
    data_age_s: 0,
  },
  timing_ms: { snap: 0.5, costs: 12, search: 85, explain: 3, total: 100 },
};

// ── MOCK FLAG — set to false when backend is ready ──────────────
const USE_MOCK = true;

// ── MAP INIT ─────────────────────────────────────────────────────
const map = L.map("map", { preferCanvas: true }).setView([50.0614, 19.9366], 14);

L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
  maxZoom: 19,
  subdomains: "abcd",
}).addTo(map);

// ── STATE ─────────────────────────────────────────────────────────
const state = {
  waypoints: [],    // [{lat, lng}]
  markers: [],      // Leaflet markers
  routeLayers: {},  // {id: L.GeoJSON}
  lastRoutes: null,
  activeRoute: null,
  chart: null,
  debounceTimer: null,
  reqId: 0,         // Prevent async race conditions
};

// ── MAP CLICK ─────────────────────────────────────────────────────
map.on("click", (e) => addWaypoint(e.latlng));

function addWaypoint(latlng) {
  if (state.waypoints.length >= 7) {
    setStatus("⚠ Max 7 waypoints allowed", "error");
    return;
  }

  const idx = state.waypoints.length;
  const label = String.fromCharCode(65 + idx); // A, B, C…

  console.log(`[Demo] Marker ${label} added at ${latlng.lat.toFixed(4)}, ${latlng.lng.toFixed(4)}`);

  const m = L.marker(latlng, { draggable: true })
    .addTo(map)
    .bindTooltip(label, { permanent: true, direction: "top", offset: [0, -12], className: "wp-tooltip" });

  m.on("dragend", () => {
    state.waypoints[state.markers.indexOf(m)] = m.getLatLng();
    renderWaypoints();
    debounceFind();
  });

  state.waypoints.push(latlng);
  state.markers.push(m);
  renderWaypoints();
  updateButtons();

  if (state.waypoints.length >= 2) debounceFind();
}

function removeWaypoint(idx) {
  map.removeLayer(state.markers[idx]);
  state.waypoints.splice(idx, 1);
  state.markers.splice(idx, 1);

  // re-label remaining markers
  state.markers.forEach((m, i) => {
    const label = String.fromCharCode(65 + i);
    m.unbindTooltip();
    m.bindTooltip(label, { permanent: true, direction: "top", offset: [0, -12], className: "wp-tooltip" });
  });

  renderWaypoints();
  updateButtons();

  if (state.waypoints.length >= 2) debounceFind();
  else clearRoutes();
}

// ── SIDEBAR: WAYPOINTS LIST ───────────────────────────────────────
function renderWaypoints() {
  const ol = document.getElementById("waypoints");
  if (!ol) return;
  ol.innerHTML = "";

  state.waypoints.forEach((wp, i) => {
    const label = String.fromCharCode(65 + i);
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="wp-label">${label}</span>
      <span class="wp-coords">${wp.lat.toFixed(4)}, ${wp.lng.toFixed(4)}</span>
      <button class="wp-remove" title="Remove" data-idx="${i}">✕</button>
    `;
    ol.appendChild(li);
  });

  ol.querySelectorAll(".wp-remove").forEach((btn) => {
    btn.addEventListener("click", () => removeWaypoint(+btn.dataset.idx));
  });

  const hint = document.getElementById("waypointHint");
  if (hint) {
    if (state.waypoints.length === 0) {
      hint.innerHTML = "📍 Click the map to add a start point.";
      hint.style.display = "";
    } else if (state.waypoints.length === 1) {
      hint.innerHTML = "🏁 Click the map to add a destination.";
      hint.style.display = "";
    } else {
      hint.style.display = "none";
    }
  }
}

function updateButtons() {
  const ready = state.waypoints.length >= 2;
  const fBtn = document.getElementById("findBtn");
  if (fBtn) fBtn.disabled = !ready;
  const dBtn = document.getElementById("deepBtn");
  if (dBtn) dBtn.disabled = !ready;
}

// ── DEPART SLIDER ─────────────────────────────────────────────────
const departSlider = document.getElementById("depart");
const departOut = document.getElementById("departOut");

function sliderToTime(val) {
  const h = Math.floor(val / 2);
  const m = val % 2 === 0 ? "00" : "30";
  return `${String(h).padStart(2, "0")}:${m}`;
}

function departIso() {
  const val = +departSlider.value;
  const h = Math.floor(val / 2);
  const m = val % 2 === 0 ? 0 : 30;
  const base = new Date();
  base.setHours(h, m, 0, 0);
  return base.toISOString();
}

// ── DEBOUNCED FIND ────────────────────────────────────────────────
function debounceFind() {
  clearTimeout(state.debounceTimer);
  state.debounceTimer = setTimeout(findRoutes, 300);
}

// ── REQUEST BODY ──────────────────────────────────────────────────
function requestBody(mode = "fast") {
  return {
    waypoints: state.waypoints.map((p) => ({ lat: p.lat, lon: p.lng })),
    profile: document.getElementById("profile").value,
    scenario: document.getElementById("scenario").value,
    depart_at: departIso(),
    optimize_order: document.getElementById("optimize").checked,
    mode,
  };
}

// ── FIND ROUTES (mock or real) ────────────────────────────────────
async function findRoutes() {
  if (state.waypoints.length < 2) return;

  const currentReqId = ++state.reqId;
  console.log(`[Demo] findRoutes() triggered. USE_MOCK is set to ${USE_MOCK}.`);
  setStatus('<span class="spinner"></span> Computing…', "loading");

  let data;
  if (USE_MOCK) {
    // Simulate network latency
    await new Promise((r) => setTimeout(r, 120));
    if (currentReqId !== state.reqId) return;

    // Deep copy mock to avoid permanent mutations across renders
    data = JSON.parse(JSON.stringify(MOCK_RESPONSE));
    
    // Random jitter to prove UI reactivity on slider/dropdown changes
    const timeOffset = Math.floor(Math.random() * 5) - 2; // -2 to +2 min
    data.routes.forEach(r => {
      r.metrics.time_min = Math.max(1, r.metrics.time_min + timeOffset);
    });
    data.front.forEach(p => {
      p.time_min = Math.max(1, p.time_min + (Math.random() * 2 - 1));
      p.exposure = Math.max(0, p.exposure + (Math.random() * 0.5 - 0.25));
    });
  } else {
    try {
      const res = await fetch(`${API}/routes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody("fast")),
      });
      if (currentReqId !== state.reqId) return;

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (currentReqId === state.reqId) setStatus("⚠ " + (err.detail ?? `Error ${res.status}`), "error");
        return;
      }
      data = await res.json();
    } catch (e) {
      if (currentReqId === state.reqId) setStatus("⚠ Network error — is the backend running?", "error");
      return;
    }
  }

  if (currentReqId !== state.reqId) return;

  drawRoutes(data.routes);
  renderCards(data.routes);
  renderPareto(data.front);
  setStatus(conditionsLine(data.conditions) + ` · computed in ${Math.round(data.timing_ms.total)} ms`);
}

// ── DEEP SEARCH (streaming NDJSON) ───────────────────────────────
async function deepSearch() {
  if (state.waypoints.length < 2) return;

  if (USE_MOCK) {
    // In mock mode, just show a fake animation then the mock result
    setStatus('<span class="spinner"></span> Evolving… generation 0', "loading");
    let gen = 0;
    const mockFront = [...MOCK_RESPONSE.front];
    const interval = setInterval(() => {
      gen++;
      // add a fake evo point each generation
      mockFront.push({
        time_min: 24 + Math.random() * 12,
        exposure: 2 + Math.random() * 5,
        source: "evo",
        supported: Math.random() > 0.6,
      });
      renderPareto(mockFront);
      setStatus(`<span class="spinner"></span> Evolving… generation ${gen}`, "loading");
      if (gen >= 8) {
        clearInterval(interval);
        drawRoutes(MOCK_RESPONSE.routes);
        renderCards(MOCK_RESPONSE.routes);
        renderPareto(mockFront);
        setStatus(conditionsLine(MOCK_RESPONSE.conditions) + " · deep search done");
      }
    }, 200);
    return;
  }

  setStatus('<span class="spinner"></span> Evolving…', "loading");

  try {
    const res = await fetch(`${API}/routes/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody("deep")),
    });

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line) continue;
        const ev = JSON.parse(line);
        if (ev.type === "gen") {
          renderPareto(ev.front);
          setStatus(`<span class="spinner"></span> Evolving… generation ${ev.gen}`, "loading");
        }
        if (ev.type === "result") {
          drawRoutes(ev.routes);
          renderCards(ev.routes);
          renderPareto(ev.front);
          setStatus(conditionsLine(ev.conditions ?? {}) + " · deep search done");
        }
      }
    }
  } catch (e) {
    setStatus("⚠ Stream error", "error");
  }
}

// ── HELPERS ───────────────────────────────────────────────────────
function getColorForDiscomfort(val) {
  // 0 (green) -> 5 (yellow) -> 10 (red)
  if (val <= 5) {
    const r = Math.round(255 * (val / 5));
    return `rgb(${r}, 200, 50)`;
  } else {
    const g = Math.round(200 * (1 - ((val - 5) / 5)));
    return `rgb(255, ${g}, 50)`;
  }
}

// ── DRAW ROUTES ───────────────────────────────────────────────────
function drawRoutes(routes) {
  console.log(`[Demo] Rendering ${routes.length} mock routes (GeoJSON) on the map.`);
  state.lastRoutes = routes; // Save for redraws in activateCard
  
  Object.values(state.routeLayers).forEach((l) => map.removeLayer(l));
  state.routeLayers = {};

  // Draw fastest first so cleanest ends up on top
  const ordered = [...routes].sort((a, b) => {
    const rank = { fastest: 0, balanced: 1, cleanest: 2 };
    return rank[a.id] - rank[b.id];
  });

  for (const r of ordered) {
    const isActive = r.id === state.activeRoute;
    const baseColor = COLORS[r.id] ?? "#334155";
    
    // Feature group to hold the entire route (base line + optional segments)
    const layerGroup = L.featureGroup();
    
    if (isActive && r.segments && r.segments.length > 0) {
      // Draw segmented route for explainability
      for (const seg of r.segments) {
        const segCoords = r.geometry.coordinates.slice(seg.coords_from, seg.coords_to + 1);
        // GeoJSON uses [lon, lat], Leaflet polyline needs [lat, lon]
        const latLngs = segCoords.map(c => [c[1], c[0]]);
        
        L.polyline(latLngs, {
          color: getColorForDiscomfort(seg.discomfort),
          weight: 8,
          opacity: 0.9,
        })
        .bindTooltip(`${seg.reason} (Discomfort: ${seg.discomfort.toFixed(1)})`, {
          className: "segment-tooltip", sticky: true
        })
        .addTo(layerGroup);
      }
    } else {
      // Draw single solid line
      // Differentiate thickness for accessibility (color-blind friendliness)
      const weightMap = { fastest: 4, balanced: 6, cleanest: 8 };
      
      L.geoJSON(r.geometry, {
        style: {
          color: baseColor,
          weight: isActive ? (weightMap[r.id] + 2) : weightMap[r.id],
          opacity: isActive ? 1.0 : 0.25,
          dashArray: r.id === "fastest" ? "8, 8" : null, // Add dashed line for fastest
        },
      })
      .bindTooltip(`${ROUTE_LABELS[r.id]}: ${r.metrics.time_min} min · ${(r.metrics.distance_m / 1000).toFixed(1)} km`, {
        sticky: true,
      })
      .addTo(layerGroup);
    }

    layerGroup.on("click", () => activateCard(r.id));
    layerGroup.addTo(map);
    state.routeLayers[r.id] = layerGroup;
  }

  const allLayers = Object.values(state.routeLayers);
  if (allLayers.length && !state.activeRoute) { // Fit bounds only on initial draw, not card click
    const group = L.featureGroup(allLayers);
    const bounds = group.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  }
}

function clearRoutes() {
  Object.values(state.routeLayers).forEach((l) => map.removeLayer(l));
  state.routeLayers = {};
  state.lastRoutes = null;
  state.activeRoute = null;
  const cardsDiv = document.getElementById("cards");
  if (cardsDiv) cardsDiv.innerHTML = "";
  const cardsSec = document.getElementById("cardsSection");
  if (cardsSec) cardsSec.style.display = "none";
  const paretoSec = document.getElementById("paretoSection");
  if (paretoSec) paretoSec.style.display = "none";
  setStatus("📍 Click the map to add a start point.");
}

// ── RENDER CARDS ──────────────────────────────────────────────────
function renderCards(routes) {
  console.log(`[Demo] Route cards updated in the UI.`);
  const container = document.getElementById("cards");
  if (!container) return;
  container.innerHTML = "";

  for (const r of routes) {
    const card = document.createElement("div");
    card.className = "route-card";
    card.dataset.id = r.id;
    card.style.color = COLORS[r.id];

    const timeDiff = r.vs_fastest.time_pct !== 0
      ? ` <span style="color:var(--color-muted)">(${formatPct(r.vs_fastest.time_pct)})</span>`
      : "";

    // For fastest route show absolute dose; for others show relative delta
    const pm25Diff = r.vs_fastest.pm25_dose_pct !== 0
      ? formatPct(r.vs_fastest.pm25_dose_pct)
      : `${r.metrics.pm25_dose_ug.toFixed(0)} µg (baseline)`;

    const avoidHtml = r.avoids.length
      ? `<div class="card-avoids">⚠ Avoids: ${r.avoids.join("; ")}</div>`
      : "";

    card.innerHTML = `
      <div class="card-header">
        <span class="card-dot" style="background:${COLORS[r.id]}"></span>
        <span class="card-title">${ROUTE_LABELS[r.id]}</span>
        <span class="card-subtitle">${(r.metrics.distance_m / 1000).toFixed(1)} km · ${r.metrics.time_min} min${timeDiff}</span>
      </div>
      <div class="card-metrics">
        <span class="card-metric-label">PM2.5 dose</span>
        <span class="card-metric-val ${r.vs_fastest.pm25_dose_pct < 0 ? "good" : ""}">${pm25Diff}</span>
        <span class="card-metric-label">Shade</span>
        <span class="card-metric-val">${r.metrics.shade_pct}%</span>
        <span class="card-metric-label">Heat stress</span>
        <span class="card-metric-val">${r.metrics.heat_stress_min} min</span>
        <span class="card-metric-label">Discomfort</span>
        <span class="card-metric-val ${r.metrics.discomfort_avg > 6 ? "bad" : r.metrics.discomfort_avg < 4 ? "good" : ""}">${r.metrics.discomfort_avg.toFixed(1)}/10</span>
      </div>
      ${avoidHtml}
    `;

    card.addEventListener("click", () => activateCard(r.id));
    container.appendChild(card);
  }

  document.getElementById("cardsSection").style.display = "";
}

function activateCard(id) {
  state.activeRoute = id;

  document.querySelectorAll(".route-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.id === id);
  });

  // Redraw map layers to show detailed segments for active route
  if (state.lastRoutes) {
    drawRoutes(state.lastRoutes);
  }
}

function formatPct(val) {
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(0)} %`;
}

// ── RENDER PARETO CHART ───────────────────────────────────────────
function renderPareto(front) {
  console.log(`[Demo] Pareto chart updated with ${front.length} data points.`);
  const section = document.getElementById("paretoSection");
  if (section) section.style.display = "";
  
  const canvas = document.getElementById("pareto");
  if (!canvas) return;

  const sweepDataRaw = front.filter((p) => p.source === "sweep" && p.supported);
  const sweepData = sweepDataRaw.map((p) => ({ x: p.time_min, y: p.exposure }));
  const sweepColors = sweepDataRaw.map((p) => COLORS[p.route_id] || "#6b7280");

  const unsupportedData = front
    .filter((p) => !p.supported && p.source !== "evo")
    .map((p) => ({ x: p.time_min, y: p.exposure }));

  const evoData = front
    .filter((p) => p.source === "evo")
    .map((p) => ({ x: p.time_min, y: p.exposure }));

  const datasets = [
    {
      label: "Sweep",
      data: sweepData,
      backgroundColor: sweepColors,
      pointRadius: 6,
      pointHoverRadius: 8,
    },
    {
      label: "★ Non-convex",
      data: unsupportedData,
      backgroundColor: "#94a3b8",
      pointRadius: 5,
      pointStyle: "triangle",
    },
    {
      label: "EA (NSGA-II)",
      data: evoData,
      backgroundColor: "#f97316",
      pointRadius: 6,
      pointHoverRadius: 8,
    },
  ].filter((d) => d.data.length > 0);

  if (state.chart) {
    state.chart.destroy();
  }

  state.chart = new Chart(canvas, {
    type: "scatter",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { font: { size: 10 }, boxWidth: 10 } },
        tooltip: {
          callbacks: {
            label: (ctx) =>
              `${ctx.dataset.label}: ${ctx.parsed.x.toFixed(1)} min, discomfort ${ctx.parsed.y.toFixed(1)}`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Time (min)", font: { size: 10 } },
          ticks: { font: { size: 10 } },
        },
        y: {
          title: { display: true, text: "Exposure", font: { size: 10 } },
          ticks: { font: { size: 10 } },
        },
      },
    },
  });
}

// ── CONDITIONS LINE ───────────────────────────────────────────────
function conditionsLine(c) {
  if (!c || !Object.keys(c).length) return "";
  const parts = [];
  if (c.temperature_c != null) parts.push(`${c.temperature_c.toFixed(1)}°C`);
  if (c.utci        != null) parts.push(`UTCI ${c.utci}`);
  if (c.uv_index    != null) parts.push(`UV ${c.uv_index}`);
  if (c.pm10_ugm3   != null) parts.push(`PM10 ${c.pm10_ugm3} µg/m³`);
  if (c.data_age_s  != null && c.data_age_s > 3600)
    parts.push(`data age: ${Math.round(c.data_age_s / 3600)} h`);
  return parts.join(" · ");
}

// ── STATUS ────────────────────────────────────────────────────────
function setStatus(html, cls = "") {
  const footer = document.getElementById("status");
  // Wrap in span so the CSS #status > * ellipsis rule fires
  footer.innerHTML = `<span>${html}</span>`;
  footer.className = cls;
}

// ── DEMO ROUTE ────────────────────────────────────────────────────
// Pre-baked waypoints for hackathon demo (Rynek Główny → AGH Campus)
const DEMO_WAYPOINTS = [
  { lat: 50.0614, lng: 19.9366 }, // Rynek Główny
  { lat: 50.0472, lng: 19.9174 }, // AGH Kampus
];

function loadDemoRoute() {
  // Clear any existing waypoints
  [...state.markers].forEach((m) => map.removeLayer(m));
  state.waypoints = [];
  state.markers = [];
  clearRoutes();

  // Place demo markers
  DEMO_WAYPOINTS.forEach((latlng) => addWaypoint(latlng));

  // Set scenario to heatwave for the most visual demo
  const scen = document.getElementById("scenario");
  if (scen) scen.value = "heatwave_2025-07-03T14";
  const prof = document.getElementById("profile");
  if (prof) prof.value = "senior";
  const dep = document.getElementById("depart");
  if (dep) dep.value = 28; // 14:00
  if (departOut) departOut.textContent = sliderToTime(28);
}

// ── INIT ──────────────────────────────────────────────────────────
if (departSlider && departOut) {
  departSlider.addEventListener("input", () => {
    departOut.textContent = sliderToTime(+departSlider.value);
    if (state.waypoints.length >= 2) debounceFind();
  });
  departOut.textContent = sliderToTime(+departSlider.value);
}

const scenSelect = document.getElementById("scenario");
if (scenSelect) scenSelect.addEventListener("change", () => {
  if (state.waypoints.length >= 2) debounceFind();
});

const profSelect = document.getElementById("profile");
if (profSelect) profSelect.addEventListener("change", () => {
  if (state.waypoints.length >= 2) debounceFind();
});

const fBtn = document.getElementById("findBtn");
if (fBtn) fBtn.addEventListener("click", findRoutes);
const dBtn = document.getElementById("deepBtn");
if (dBtn) dBtn.addEventListener("click", deepSearch);
const dmBtn = document.getElementById("demoBtn");
if (dmBtn) dmBtn.addEventListener("click", loadDemoRoute);

renderWaypoints();
updateButtons();
