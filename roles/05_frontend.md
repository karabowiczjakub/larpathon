# Rola 5 — Frontend (Leaflet, mapa, wybór A/B, wyświetlanie i porównanie tras)

> **Twoja misja:** jeden ekran, który w 10 sekund tłumaczy jurorowi pomysł: dwie trasy na mapie (szara = najszybsza, zielona = zdrowsza) i jedno zdanie porównania — „+2 min, −27% wdychanego PM2.5, +36 pp cienia". **Design to 20% oceny** — a w fazie 1 jury zobaczy tylko Twoje zrzuty ekranu i wideo.
>
> Stack: **czysty HTML + CSS + vanilla JS**, Leaflet. Bez npm, bez buildu. Pliki w `app/static/`, serwuje je Flask. Kontrakt API: `04_backend_integration.md`, sekcja 4.4.

---

## 1. Definition of Done

- [ ] Klik na mapie: A, potem B (markery przeciągalne) → automatycznie liczą się trasy.
- [ ] Dwie trasy na mapie + karty z metrykami + zdanie porównania + „Avoids: …".
- [ ] Wybór scenariusza (Live / Heatwave / Smog), profilu, **suwak godziny wyjazdu** (zmiana → przeliczenie).
- [ ] Kolorowanie zdrowszej trasy wg dyskomfortu (przełącznik).
- [ ] Stopka: warunki (temp, UV, PM10, źródło danych, słońce) + **„computed in X ms"**.
- [ ] Stany: pusty („Click the map to set start"), ładowanie, błąd (punkt poza Krakowem, brak trasy), „Fastest is already the healthiest".
- [ ] Działa na laptopie 1920×1080 i na telefonie (układ pionowy).
- [ ] Zrzuty ekranu do PDF + **nagranie demo 1:30–2:00** (to jest „demo link" w zgłoszeniu — mentorzy w fazie 1 nie uruchomią aplikacji).

---

## 2. Strategia „100%": niezależność od backendu od pierwszej godziny

1. **H0–H1:** pliki z sekcji 5 + `mock/route.json` → otwierasz `http://localhost:8000/?mock=1` (albo nawet `python -m http.server` w `app/static`) i rysujesz trasy z pliku. **Nie czekasz na nikogo.**
2. **H2:** Backend wystawia API na mockach → przełączasz na prawdziwe `fetch("/api/route")` (bez `?mock=1`).
3. **H4+:** te same ekrany, ale prawdziwe ulice Krakowa — Twoja praca się nie zmienia.
4. **Leaflet lokalnie:** w H0 pobierz `leaflet.js` i `leaflet.css` do `app/static/vendor/` (CDN na sali może nie działać). Kod niżej najpierw próbuje CDN, ale wersja lokalna to plan B jedną zmianą linii.

---

## 3. Plan godzinowy

| H | Zadanie | Sprawdzian |
|---|---|---|
| 0–1 | Kontrakt API z Backendem; `vendor/` Leaflet; szkielet `index.html` | mapa Krakowa się wyświetla |
| 1–2 | Wybór A/B, markery, rysowanie tras z `mock/route.json`, karty | `?mock=1` pokazuje 2 trasy i porównanie |
| 2–4 | Prawdziwe API (mocki backendu); scenariusze, profil, suwak; stany błędów | zmiana suwaka → nowe zapytanie |
| 4–8 | Prawdziwy graf: dopieszczenie dopasowania mapy, kolorowanie segmentów, „Avoids", stopka warunków | trasy po ulicach Krakowa |
| **8–10** | **M1** z zespołem | demo end-to-end |
| 10–14 | Design pass (sekcja 6), responsywność, presety tras demo, ekran „About" (1 akapit + źródła danych) | test na telefonie |
| 14–17 | Sen zmianowy | |
| 17–20 | Zrzuty ekranu 1920×1080 (Heatwave 14:00 vs 18:30, Smog + Asthma), szkic slajdów | |
| **20** | Feature freeze | |
| 20–22 | **Nagranie wideo** (OBS Studio), montaż minimalny, upload (YouTube niepubliczny / Drive) | link działa w oknie incognito |
| 22–23 | Slajdy (max 10, PDF) z zespołem; wysyłka zgłoszenia ≥ 30 min przed terminem | |

---

## 4. Ekran (wireframe)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ AirRoute Kraków · healthier bike routes                         [About]       │
├────────────────────────┬──────────────────────────────────────────────────────┤
│ TRIP                   │                                                      │
│ A  ● Rynek Główny      │                                                      │
│ B  ● AGH               │                 M A P  (Leaflet)                     │
│ [Reset]  Presets: ▾    │      - - - Fastest (grey, dashed)                    │
│                        │      ━━━━ Healthier (green, on top)                  │
│ CONDITIONS             │      Ⓐ Ⓑ draggable                                  │
│ Scenario [Heatwave ▾]  │                                                      │
│ Profile  [Senior   ▾]  │                                                      │
│ Depart   ──●───  14:00 │                                                      │
│                        │                                                      │
│ RESULT                 │                                                      │
│ Healthier route:       │                                                      │
│ +2 min · −27% PM2.5 ·  │                                                      │
│ +36 pp shade           │                                                      │
│ ┌ Fastest ─────────┐   │                                                      │
│ │ 2.3 km · 9 min   │   │                                                      │
│ │ shade 22% · …    │   │                                                      │
│ └──────────────────┘   │                                                      │
│ ┌ Healthier ───────┐   │                                                      │
│ │ 2.8 km · 11 min  │   │                                                      │
│ │ Avoids: Al. M…   │   │  ☐ Colour healthier route by discomfort              │
│ └──────────────────┘   │                                                      │
├────────────────────────┴──────────────────────────────────────────────────────┤
│ 34.5°C · UV 8.1 · PM10 21 µg/m³ · scenario data · sun 59° · computed in 342 ms │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Kod (kompletny — kopiujesz w H0–H1)

### 5.1 `app/static/index.html`

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AirRoute Kraków</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <!-- plan B bez internetu: <link rel="stylesheet" href="vendor/leaflet.css" /> -->
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header class="topbar">
    <h1>AirRoute Kraków <span>healthier bike routes</span></h1>
    <button id="aboutBtn" class="ghost">About</button>
  </header>

  <main class="layout">
    <aside class="sidebar">
      <section>
        <h2>Trip</h2>
        <p id="hint" class="hint">Click the map to set the start (A).</p>
        <div class="row">
          <button id="resetBtn" class="ghost">Reset</button>
          <select id="preset" aria-label="Demo routes">
            <option value="">Demo routes…</option>
            <option value="50.0617,19.9373|50.0665,19.9195">Main Square → AGH</option>
            <option value="50.0670,19.9450|50.0540,19.9355">Main Station → Wawel</option>
            <option value="50.0515,19.9447|50.0717,20.0377">Kazimierz → Nowa Huta</option>
          </select>
        </div>
      </section>

      <section>
        <h2>Conditions</h2>
        <label>Scenario <select id="scenario"></select></label>
        <label>Profile
          <select id="profile">
            <option value="standard">Standard cyclist</option>
            <option value="asthma">Asthma / allergy</option>
            <option value="senior">Senior / child</option>
            <option value="athlete">Athlete</option>
          </select>
        </label>
        <label>Depart at <output id="departOut">14:00</output>
          <input id="depart" type="range" min="5" max="22" step="0.5" value="14" />
        </label>
      </section>

      <section id="result" hidden>
        <h2>Result</h2>
        <p id="summary" class="summary"></p>
        <div id="cards"></div>
        <label class="check"><input type="checkbox" id="colorize" /> Colour healthier route by discomfort</label>
      </section>

      <p id="error" class="error" hidden></p>
    </aside>
    <div id="map" aria-label="Map of Kraków"></div>
  </main>

  <footer id="status">Loading…</footer>

  <dialog id="about">
    <h2>About</h2>
    <p>AirRoute finds a bike route that trades a few minutes for less smog, less heat and more shade.
       It combines OpenStreetMap streets, GUGiK 3D buildings, Kraków city greenery (MSIP),
       Open-Meteo / CAMS forecasts and GIOŚ air-quality stations. Shade is computed from the sun position
       and building and tree heights.</p>
    <p class="small">Data: © OpenStreetMap contributors (ODbL) · GUGiK · MSIP Kraków · Open-Meteo (CC BY 4.0) / CAMS · GIOŚ · © CARTO</p>
    <form method="dialog"><button>Close</button></form>
  </dialog>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <!-- plan B: <script src="vendor/leaflet.js"></script> -->
  <script src="app.js"></script>
</body>
</html>
```

### 5.2 `app/static/style.css`

```css
:root {
  --bg: #f8fafc; --panel: #ffffff; --ink: #0f172a; --muted: #64748b; --line: #e2e8f0;
  --fast: #6b7280; --eco: #16a34a; --bad: #dc2626; --good: #16a34a; --accent: #0f766e;
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink); background: var(--bg);
       display: grid; grid-template-rows: auto 1fr auto; }
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px;
          background: var(--panel); border-bottom: 1px solid var(--line); }
.topbar h1 { font-size: 18px; margin: 0; }
.topbar h1 span { font-weight: 400; color: var(--muted); font-size: 14px; margin-left: 6px; }
.layout { display: grid; grid-template-columns: 360px 1fr; min-height: 0; }
.sidebar { overflow-y: auto; padding: 12px 16px; background: var(--panel); border-right: 1px solid var(--line); }
.sidebar section { padding: 10px 0; border-bottom: 1px solid var(--line); }
h2 { font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 0 0 8px; }
label { display: block; margin: 8px 0; font-size: 14px; }
select, input[type=range] { width: 100%; margin-top: 4px; }
select { padding: 6px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
button { padding: 7px 12px; border-radius: 8px; border: 1px solid var(--accent); background: var(--accent); color: #fff; cursor: pointer; }
button.ghost { background: transparent; color: var(--accent); }
.row { display: flex; gap: 8px; align-items: center; }
.row select { margin: 0; }
.hint { color: var(--muted); margin: 0 0 8px; }
.summary { font-size: 16px; font-weight: 600; margin: 4px 0 10px; }
.card { border: 1px solid var(--line); border-left: 6px solid var(--fast); border-radius: 10px; padding: 10px 12px; margin: 8px 0; cursor: pointer; }
.card.eco { border-left-color: var(--eco); }
.card.active { box-shadow: 0 0 0 2px var(--ink) inset; }
.card h3 { margin: 0 0 4px; font-size: 15px; }
.metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 10px; font-size: 13px; color: var(--muted); }
.metrics b { color: var(--ink); font-weight: 600; }
.avoids { font-size: 13px; margin-top: 6px; }
.badge { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 12px; font-weight: 600; margin-right: 4px; }
.badge.good { background: #dcfce7; color: #166534; } .badge.bad { background: #fee2e2; color: #991b1b; }
.check { display: flex; gap: 8px; align-items: center; font-size: 13px; }
.error { color: var(--bad); font-weight: 600; }
#map { min-height: 0; }
footer { padding: 6px 16px; font-size: 13px; color: var(--muted); background: var(--panel); border-top: 1px solid var(--line); }
footer .warn { color: #b45309; font-weight: 600; }
.pin { width: 28px; height: 28px; border-radius: 50%; color: #fff; font-weight: 700; display: grid; place-items: center;
       border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.4); }
.pin-A { background: #0f172a; } .pin-B { background: #0f766e; }
body.busy #map { cursor: progress; opacity: .85; }
dialog { max-width: 520px; border: 1px solid var(--line); border-radius: 12px; }
.small { font-size: 12px; color: var(--muted); }
@media (max-width: 800px) {
  .layout { grid-template-columns: 1fr; grid-template-rows: 55vh auto; }
  #map { order: -1; }
  .sidebar { border-right: none; border-top: 1px solid var(--line); }
}
```

### 5.3 `app/static/app.js`

```javascript
const API = "/api";
const MOCK = new URLSearchParams(location.search).has("mock");
const $ = (s) => document.querySelector(s);
const SEG_COLORS = ["#16a34a", "#84cc16", "#eab308", "#f97316", "#dc2626"];
const REASON = { heat: "heat stress", air: "air pollution", uv: "strong UV", ok: "comfortable" };

const state = { A: null, B: null, markers: {}, layers: [], scenarios: [], last: null, active: "eco" };

// ---------- mapa ----------
const map = L.map("map").setView([50.0614, 19.9366], 13);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
  subdomains: "abcd", maxZoom: 19,
}).addTo(map);
fetch("krakow_boundary.geojson").then((r) => (r.ok ? r.json() : null))
  .then((g) => g && L.geoJSON(g, { style: { color: "#334155", weight: 1, fill: false, dashArray: "4 4" }, interactive: false }).addTo(map))
  .catch(() => {});

map.on("click", (e) => setPoint(!state.A ? "A" : "B", e.latlng));

function pinIcon(label) {
  return L.divIcon({ className: "", html: `<div class="pin pin-${label}">${label}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] });
}

function setPoint(which, latlng, silent = false) {
  state[which] = L.latLng(latlng);
  if (state.markers[which]) state.markers[which].setLatLng(state[which]);
  else {
    const m = L.marker(state[which], { draggable: true, icon: pinIcon(which), keyboard: true, title: which }).addTo(map);
    m.on("dragend", () => { state[which] = m.getLatLng(); findRoutes(); });
    state.markers[which] = m;
  }
  $("#hint").textContent = state.B ? "Drag A or B to change the trip." : "Now click the destination (B).";
  if (!silent && state.A && state.B) findRoutes();
}

function reset() {
  Object.values(state.markers).forEach((m) => map.removeLayer(m));
  clearRoutes(); Object.assign(state, { A: null, B: null, markers: {}, last: null });
  $("#result").hidden = true; $("#error").hidden = true;
  $("#hint").textContent = "Click the map to set the start (A).";
}

// ---------- kontrolki ----------
async function loadScenarios() {
  try {
    state.scenarios = MOCK
      ? [{ id: "heatwave_2025-07-03", label: "Heatwave · 3 Jul 2025", default_at: "2025-07-03T14:00:00+02:00" }]
      : await (await fetch(`${API}/scenarios`)).json();
  } catch { state.scenarios = [{ id: "live", label: "Live now" }]; }
  $("#scenario").innerHTML = state.scenarios.map((s) => `<option value="${s.id}">${esc(s.label)}</option>`).join("");
  const heat = state.scenarios.find((s) => s.id.startsWith("heatwave"));
  if (heat) $("#scenario").value = heat.id;               // demo zaczyna od upału
  syncSliderToScenario();
}

function syncSliderToScenario() {
  const sc = currentScenario();
  let h = 14;
  if (sc?.default_at) h = parseInt(sc.default_at.slice(11, 13), 10);
  else { const d = new Date(); h = Math.min(22, Math.max(5, d.getHours() + (d.getMinutes() >= 30 ? 0.5 : 0))); }
  $("#depart").value = h; showDepart();
}
const currentScenario = () => state.scenarios.find((s) => s.id === $("#scenario").value);
function showDepart() {
  const v = parseFloat($("#depart").value);
  $("#departOut").textContent = `${String(Math.floor(v)).padStart(2, "0")}:${v % 1 ? "30" : "00"}`;
}

function departIso() {
  const v = parseFloat($("#depart").value);
  const hhmm = `${String(Math.floor(v)).padStart(2, "0")}:${v % 1 ? "30" : "00"}:00`;
  const sc = currentScenario();
  if (sc?.default_at) return `${sc.default_at.slice(0, 10)}T${hhmm}${sc.default_at.slice(19)}`;
  const d = new Date(), off = -d.getTimezoneOffset(), p = (n) => String(n).padStart(2, "0");
  const tz = `${off >= 0 ? "+" : "-"}${p(Math.floor(Math.abs(off) / 60))}:${p(Math.abs(off) % 60)}`;
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${hhmm}${tz}`;
}

let debounce;
$("#depart").addEventListener("input", () => { showDepart(); clearTimeout(debounce); debounce = setTimeout(findRoutes, 300); });
$("#scenario").addEventListener("change", () => { syncSliderToScenario(); findRoutes(); });
$("#profile").addEventListener("change", findRoutes);
$("#colorize").addEventListener("change", () => state.last && drawRoutes(state.last.routes));
$("#resetBtn").addEventListener("click", reset);
$("#preset").addEventListener("change", (e) => {
  if (!e.target.value) return;
  const [a, b] = e.target.value.split("|").map((s) => s.split(",").map(Number));
  setPoint("A", a, true); setPoint("B", b); e.target.value = "";
});
$("#aboutBtn").addEventListener("click", () => $("#about").showModal());

// ---------- zapytanie ----------
async function findRoutes() {
  if (!state.A || !state.B) return;
  document.body.classList.add("busy"); $("#error").hidden = true;
  const body = {
    points: [state.A, state.B].map((p) => ({ lat: +p.lat.toFixed(6), lon: +p.lng.toFixed(6) })),
    scenario: $("#scenario").value, profile: $("#profile").value, depart_at: departIso(),
  };
  try {
    const res = MOCK ? await fetch("mock/route.json")
      : await fetch(`${API}/route`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) throw new Error(errorText(data));
    state.last = data; render(data);
  } catch (err) {
    $("#error").textContent = err.message || "Something went wrong."; $("#error").hidden = false;
  } finally {
    document.body.classList.remove("busy");
  }
}

function errorText(d) {
  return { point_outside_area: "That point is outside the Kraków bike network — move it closer to a street.",
           no_route: "No bike route between these points.", validation: "Invalid request." }[d.error] || "Server error.";
}

// ---------- rysowanie ----------
function clearRoutes() { state.layers.forEach((l) => map.removeLayer(l)); state.layers = []; }

function drawRoutes(routes) {
  clearRoutes();
  const fast = routes.find((r) => r.id === "fastest"), eco = routes.find((r) => r.id === "eco");
  const ll = (c) => c.map(([lon, lat]) => [lat, lon]);
  const dim = (id) => (state.active === id ? 1 : 0.45);
  if (fast) state.layers.push(L.polyline(ll(fast.geometry.coordinates),
    { color: "#6b7280", weight: 6, opacity: dim("fastest"), dashArray: "8 8" }).bindTooltip("Fastest").addTo(map));
  if (eco) {
    if ($("#colorize").checked && eco.segments?.length) {
      const c = eco.geometry.coordinates;
      eco.segments.forEach((s) => {
        const col = SEG_COLORS[Math.min(4, Math.floor(s.discomfort * 5))];
        state.layers.push(L.polyline(ll(c.slice(s.from, s.to + 1)), { color: col, weight: 7, opacity: dim("eco") })
          .bindTooltip(`${REASON[s.reason] || s.reason} · discomfort ${(s.discomfort * 10).toFixed(1)}/10`).addTo(map));
      });
    } else {
      state.layers.push(L.polyline(ll(eco.geometry.coordinates), { color: "#16a34a", weight: 7, opacity: dim("eco") })
        .bindTooltip("Healthier").addTo(map));
    }
  }
  const all = L.featureGroup(state.layers);
  if (state.layers.length) map.fitBounds(all.getBounds(), { padding: [40, 40], maxZoom: 16 });
}

function render(d) {
  drawRoutes(d.routes);
  $("#result").hidden = false;
  const c = d.comparison;
  $("#summary").innerHTML = c.same_route
    ? "The fastest route is already the healthiest right now."
    : `Healthier route: ${badge(`+${c.time_delta_min} min`, false)}
       ${badge(`${c.pm25_dose_delta_pct}% PM2.5`, c.pm25_dose_delta_pct <= 0)}
       ${badge(`${c.shade_delta_pp >= 0 ? "+" : ""}${c.shade_delta_pp} pp shade`, c.shade_delta_pp >= 0)}
       ${c.heat_stress_delta_min ? badge(`${c.heat_stress_delta_min} min heat stress`, c.heat_stress_delta_min <= 0) : ""}`;
  $("#cards").innerHTML = d.routes.map(card).join("");
  document.querySelectorAll(".card").forEach((el) => el.addEventListener("click", () => {
    state.active = el.dataset.id; drawRoutes(d.routes); $("#cards").innerHTML = d.routes.map(card).join("");
  }));
  footer(d);
}

function card(r) {
  const m = r.metrics;
  return `<div class="card ${r.id === "eco" ? "eco" : ""} ${state.active === r.id ? "active" : ""}" data-id="${r.id}">
    <h3>${esc(r.label)}</h3>
    <div class="metrics">
      <span><b>${(m.distance_m / 1000).toFixed(1)} km</b> · <b>${m.time_min} min</b></span>
      <span>shade <b>${m.shade_pct}%</b></span>
      <span>PM2.5 inhaled <b>${m.pm25_dose_ug} µg</b></span>
      <span>heat stress <b>${m.heat_stress_min} min</b></span>
      <span>discomfort <b>${m.avg_discomfort}/10</b></span>
    </div>
    ${r.avoids?.length ? `<div class="avoids">Avoids: ${r.avoids.map(esc).join(", ")}</div>` : ""}
  </div>`;
}

function footer(d) {
  const k = d.conditions || {}, s = d.sun || {};
  const src = { live: "live data", scenario: "scenario data", fallback: '<span class="warn">offline fallback</span>', mock: "mock data" }[k.source] || "";
  $("#status").innerHTML = [
    k.temperature_c != null && `${k.temperature_c}°C`, k.uv_index != null && `UV ${k.uv_index}`,
    k.pm10 != null && `PM10 ${Math.round(k.pm10)} µg/m³`, src,
    s.elevation_deg != null && (s.elevation_deg > 0 ? `sun ${Math.round(s.elevation_deg)}°` : "night"),
    d.timing_ms && `computed in ${Math.round(d.timing_ms.total)} ms`,
  ].filter(Boolean).join(" · ");
}

const badge = (t, good) => `<span class="badge ${good ? "good" : "bad"}">${t}</span>`;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

loadScenarios().then(() => { $("#status").textContent = "Click the map to plan a trip."; });
```

### 5.4 `app/static/mock/route.json` (do pracy bez backendu)

```json
{
  "routes": [
    {"id": "fastest", "label": "Fastest", "color": "#6b7280",
     "geometry": {"type": "LineString", "coordinates": [[19.9373,50.0617],[19.9330,50.0630],[19.9280,50.0645],[19.9235,50.0657],[19.9195,50.0665]]},
     "metrics": {"distance_m": 1450, "time_min": 5.8, "avg_discomfort": 6.4, "shade_pct": 18.0, "pm25_dose_ug": 2.6, "heat_stress_min": 4.1},
     "segments": [{"from": 0, "to": 4, "discomfort": 0.68, "reason": "heat"}], "avoids": []},
    {"id": "eco", "label": "Healthier", "color": "#16a34a",
     "geometry": {"type": "LineString", "coordinates": [[19.9373,50.0617],[19.9360,50.0640],[19.9320,50.0660],[19.9270,50.0668],[19.9230,50.0672],[19.9195,50.0665]]},
     "metrics": {"distance_m": 1720, "time_min": 6.9, "avg_discomfort": 3.1, "shade_pct": 61.0, "pm25_dose_ug": 1.9, "heat_stress_min": 0.8},
     "segments": [{"from": 0, "to": 2, "discomfort": 0.22, "reason": "ok"}, {"from": 2, "to": 5, "discomfort": 0.41, "reason": "heat"}],
     "avoids": ["Al. Mickiewicza (heat)"]}
  ],
  "comparison": {"same_route": false, "time_delta_min": 1.1, "time_delta_pct": 19.0, "pm25_dose_delta_pct": -26.9, "shade_delta_pp": 43.0, "heat_stress_delta_min": -3.3},
  "conditions": {"source": "mock", "temperature_c": 34.5, "uv_index": 8.1, "pm10": 21.0},
  "sun": {"azimuth_deg": 215.0, "elevation_deg": 59.0},
  "timing_ms": {"total": 342.0}
}
```

---

## 6. Design — zasady (20% oceny)

- **Jedna myśl na ekranie:** szara przerywana = najszybsza, zielona ciągła = zdrowsza i rysowana na wierzchu. Nic więcej domyślnie.
- **Porównanie zamiast surowych liczb:** zdanie „+1 min · −27% PM2.5 · +43 pp shade" jest ważniejsze niż karty.
- **Dostępność:** trasa najszybsza odróżnia się też wzorem (przerywana), nie tylko kolorem; badge mają tekst, nie tylko kolor; kontrast tekstu ≥ 4.5:1.
- **Mapa:** jasny podkład CARTO Positron (kolorowe trasy dobrze kontrastują), granica Krakowa przerywaną linią (zasięg usługi).
- **Puste/błędne stany** zawsze z instrukcją, co zrobić („move it closer to a street").
- **Bez emoji, bez gradientów, bez animacji poza zmianą tras.** Font systemowy.
- **Zrzuty do PDF:** 1920×1080, zoom przeglądarki 100%, scenariusz Heatwave, profil Senior, preset „Main Square → AGH" — potem ta sama trasa o 18:30 (zmiana przez cień) i Smog + Asthma.

---

## 7. Scenariusz nagrania (1:30–2:00, OBS Studio)

1. (0:00) Mapa Krakowa, pusty stan. Głos: problem w jednym zdaniu (smog zimą, upał latem, rowerzysta oddycha 2–3× intensywniej).
2. (0:15) Heatwave 3 Jul 14:00, profil Senior, preset Main Square → AGH → dwie trasy, zdanie porównania.
3. (0:35) Klik w kartę „Healthier" → „Avoids: …"; włączenie kolorowania dyskomfortu.
4. (0:50) **Suwak 14:00 → 18:30** — trasa się zmienia (cienie budynków). To jest kulminacja.
5. (1:10) Smog 20 Jan 17:00 + Asthma → trasa omija arterie, spada dawka PM2.5.
6. (1:30) Stopka: „computed in X ms", źródła danych (About). Koniec.

Nagrywaj **na scenariuszach** (nie na live) — wynik powtarzalny. Zrób 2 ujęcia, wybierz lepsze.

---

## 8. Testy ręczne (checklista przed H20)

- [ ] `?mock=1` działa bez backendu.
- [ ] Klik poza Krakowem (np. Wieliczka) → czytelny błąd, aplikacja dalej działa.
- [ ] Szybkie przeciąganie markera / suwaka nie zostawia „starych" tras (debounce + czyszczenie warstw).
- [ ] Reset czyści wszystko.
- [ ] Telefon (DevTools 390×844): mapa u góry, panel pod spodem, wszystko klikalne.
- [ ] Bez internetu: Leaflet z `vendor/` (plan B), kafle znikają — ale trasy i karty działają.
- [ ] Polskie nazwy ulic w „Avoids" wyświetlają się poprawnie (UTF-8, escapowanie).

---

## 9. Ryzyka i plan B

| Ryzyko | Plan B |
|---|---|
| Backend nie gotowy | `?mock=1` — cały UI i nagranie na mocku |
| CDN Leaflet niedostępny | `vendor/leaflet.js|css` (pobrane w H0), zmiana 2 linii |
| Kafle CARTO nie działają | OSM `https://tile.openstreetmap.org/{z}/{x}/{y}.png` z atrybucją |
| Wolne odpowiedzi | stan „busy", debounce 300 ms, stopka z czasem |
| Brak czasu na kolorowanie segmentów | zostaje jednolita zielona linia — wygląda dobrze |

## 10. Czego NIE robić

- Nie dodawaj Reacta, bundlera, TypeScriptu, frameworka CSS — 3 pliki wystarczą.
- Nie rób wyszukiwarki adresów (Nominatim ma limit 1 zapytanie/s i polityki użycia) — presety + klik wystarczą.
- Nie pokazuj więcej niż 2 tras domyślnie (trzecia tylko, jeśli Backend doda BALANCED).
- Nie nagrywaj demo na danych live (zmienne, w październiku trasy mogą być identyczne).
