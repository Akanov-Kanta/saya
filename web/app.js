// SAYA web map. The browser only draws: shadows, A*, Bayes and the MDP run in Python (server.py).

const $ = (id) => document.getElementById(id);
const state = { meta: null, start: null, end: null, shadeRequest: 0, routeRequest: 0, playing: false };
const markers = { start: null, end: null };

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  center: [71.4125, 51.09],
  zoom: 16.1,
  pitch: 55,
  bearing: -25,
  maxPitch: 75,
});
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
map.addControl(new maplibregl.ScaleControl(), "bottom-right");

// ---------------------------------------------------------------- helpers
const minutesToText = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const pct = (x) => `${Math.round(x * 100)}%`;
const fmt = (x, d = 1) => Number(x).toFixed(d);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(body.detail || response.statusText), { status: response.status });
  return body;
}

function circle(center, radiusM, steps = 96) {
  const [lat, lon] = center;
  const coords = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    coords.push([lon + (radiusM * Math.sin(a)) / (111320 * Math.cos((lat * Math.PI) / 180)),
                 lat + (radiusM * Math.cos(a)) / 111320]);
  }
  return { type: "Feature", geometry: { type: "LineString", coordinates: coords } };
}

const emptyLine = { type: "Feature", geometry: { type: "LineString", coordinates: [] } };

function timeParams() {
  return { date: $("date").value, time: minutesToText(Number($("time").value)) };
}

function showError(message) {
  $("error").hidden = !message;
  $("error").textContent = message || "";
}

// ---------------------------------------------------------------- map layers
map.on("load", async () => {
  state.meta = await api("/api/meta");
  const meta = state.meta;

  // Our own 3D buildings replace the flat basemap ones
  for (const layer of map.getStyle().layers) {
    if (layer["source-layer"] === "building") map.setLayoutProperty(layer.id, "visibility", "none");
  }

  map.addSource("area", { type: "geojson", data: circle(meta.center, meta.radius_m) });
  map.addLayer({ id: "area", type: "line", source: "area",
    paint: { "line-color": "#1f6fb2", "line-width": 1.5, "line-dasharray": [3, 3], "line-opacity": 0.6 } });

  map.addSource("shade", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({ id: "shade", type: "fill", source: "shade",
    paint: { "fill-color": "#2b3150", "fill-opacity": 0.38 } });

  map.addSource("buildings", { type: "geojson", data: "/api/buildings" });
  map.addLayer({ id: "buildings-3d", type: "fill-extrusion", source: "buildings",
    paint: {
      "fill-extrusion-height": ["get", "height"],
      "fill-extrusion-color": ["interpolate", ["linear"], ["get", "height"], 3, "#e8e4dc", 20, "#d8d2c6", 60, "#c4bcae"],
      "fill-extrusion-opacity": 0.92,
      "fill-extrusion-vertical-gradient": true,
    } });

  for (const action of ["Shortest", "Shaded"]) {
    map.addSource(`route-${action}`, { type: "geojson", data: emptyLine });
    map.addLayer({ id: `route-${action}-casing`, type: "line", source: `route-${action}`,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "white", "line-width": 9, "line-opacity": 0.9 } });
    map.addLayer({ id: `route-${action}`, type: "line", source: `route-${action}`,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": action === "Shortest" ? "#d1495b" : "#1f6fb2", "line-width": 5 } });
  }

  for (const report of meta.barriers) {
    const el = document.createElement("div");
    el.className = "barrier-marker";
    el.textContent = "!";
    el.title = `${report.name} (${report.type}, simulated report)`;
    new maplibregl.Marker({ element: el }).setLngLat([report.lon, report.lat]).addTo(map);
  }

  // Controls
  for (const [key, label] of Object.entries(meta.profiles)) $("profile").add(new Option(label, key));
  $("profile").value = meta.defaults.profile;
  $("date").value = meta.defaults.date;
  const [h, m] = meta.defaults.time.split(":").map(Number);
  $("time").value = h * 60 + m;
  $("time-text").textContent = meta.defaults.time;

  usePreset();
  await refresh();
  fitToTrip();
});

function fitToTrip() {
  if (!state.start || !state.end) return;
  const wide = window.innerWidth > 720;
  // Build the box from min/max: a box given west > east would wrap around the globe
  const bounds = new maplibregl.LngLatBounds();
  for (const [lat, lon] of [state.start, state.end]) bounds.extend([lon, lat]);
  map.fitBounds(bounds, {
    padding: wide ? { left: 420, right: 80, top: 80, bottom: 80 } : { left: 40, right: 40, top: 40, bottom: window.innerHeight * 0.55 },
    bearing: -20, maxZoom: 17, duration: 800,
  });
}

map.on("click", (event) => {
  const point = [event.lngLat.lat, event.lngLat.lng];
  if (!state.start) setPoint("start", point);
  else if (!state.end) { setPoint("end", point); refreshRoute(); }
  else { clearRoute(); setPoint("start", point); }
  updateHint();
});

// ---------------------------------------------------------------- start / end
function setPoint(which, latlon) {
  state[which] = latlon;
  if (!markers[which]) {
    markers[which] = new maplibregl.Marker({ color: which === "start" ? "#2a9d8f" : "#264653", draggable: true })
      .setLngLat([latlon[1], latlon[0]])
      .addTo(map);
    markers[which].on("dragend", () => {
      const p = markers[which].getLngLat();
      state[which] = [p.lat, p.lng];
      if (state.start && state.end) refreshRoute();
    });
  }
  markers[which].setLngLat([latlon[1], latlon[0]]);
}

function clearRoute() {
  for (const which of ["start", "end"]) {
    if (markers[which]) markers[which].remove();
    markers[which] = null;
    state[which] = null;
  }
  for (const action of ["Shortest", "Shaded"]) map.getSource(`route-${action}`)?.setData(emptyLine);
  $("result").hidden = true;
  showError("");
}

function usePreset() {
  const { places, defaults } = state.meta;
  clearRoute();
  setPoint("start", [places[defaults.start].lat, places[defaults.start].lon]);
  setPoint("end", [places[defaults.end].lat, places[defaults.end].lon]);
  updateHint();
}

function updateHint() {
  $("hint").textContent = !state.start ? "Click the map to choose a start point."
    : !state.end ? "Now click where you want to go."
    : "Drag the markers to adjust, or click the map to start a new trip.";
}

$("preset").onclick = () => { usePreset(); refreshRoute(); fitToTrip(); };
$("swap").onclick = () => {
  if (!state.start || !state.end) return;
  const [a, b] = [state.start, state.end];
  setPoint("start", b); setPoint("end", a); refreshRoute();
};
$("clear").onclick = () => { clearRoute(); updateHint(); };

// ---------------------------------------------------------------- time, shade, sun
let debounce = null;
function scheduleRefresh() {
  $("time-text").textContent = minutesToText(Number($("time").value));
  clearTimeout(debounce);
  debounce = setTimeout(refresh, 120);
}
$("time").addEventListener("input", scheduleRefresh);
$("date").addEventListener("change", refresh);
$("profile").addEventListener("change", refreshRoute);
$("feels").addEventListener("change", refreshRoute);

$("play").onclick = async () => {
  state.playing = !state.playing;
  $("play").classList.toggle("playing", state.playing);
  $("play").innerHTML = state.playing ? "&#10073;&#10073;" : "&#9654;";
  while (state.playing) {
    let next = Number($("time").value) + 15;
    if (next > Number($("time").max)) next = Number($("time").min);
    $("time").value = next;
    $("time-text").textContent = minutesToText(next);
    await refresh();
    await sleep(250);
  }
};

async function refresh() {
  await Promise.all([refreshShade(), state.start && state.end ? refreshRoute() : null]);
}

async function refreshShade() {
  const id = ++state.shadeRequest;
  document.body.classList.add("loading");
  try {
    const data = await api(`/api/shade?${new URLSearchParams(timeParams())}`);
    if (id !== state.shadeRequest) return;   // a newer request already won
    map.getSource("shade").setData(data.shade);
    drawSun(data.sun, data.shaded_share);
  } catch (error) {
    showError(error.message);
  } finally {
    if (id === state.shadeRequest) document.body.classList.remove("loading");
  }
}

function drawSun(sun, shadedShare) {
  if (sun.is_night) {
    $("sun-text").innerHTML = `Sun is below the horizon (${fmt(sun.altitude)}&deg;). No sun, no shade difference.`;
    map.setLight({ anchor: "map", position: [1.5, 0, 80], intensity: 0.15, color: "#9db0ff" });
    $("sun-arrow").style.opacity = 0.3;
    return;
  }
  $("sun-arrow").style.opacity = 1;
  $("sun-arrow").style.transform = `rotate(${sun.azimuth + 180}deg)`;   // arrow = where shadows point
  $("sun-text").innerHTML =
    `Sun ${fmt(sun.altitude)}&deg; high, from the <b>${sun.compass}</b> &rarr; shadows fall <b>${sun.shadow_compass}</b><br>` +
    `A 10 m building casts a ${fmt(sun.shadow_of_10m)} m shadow · shade covers ${pct(shadedShare)} of paths`;
  // Light the 3D buildings from the real sun direction
  map.setLight({ anchor: "map", position: [1.5, sun.azimuth, Math.max(0, 90 - sun.altitude)],
                 intensity: 0.5, color: "#fff7e8" });
}

// ---------------------------------------------------------------- route
async function refreshRoute() {
  if (!state.start || !state.end) return;
  const id = ++state.routeRequest;
  const feels = $("feels").value;
  const body = { start: state.start, end: state.end, profile: $("profile").value, ...timeParams(),
                 feels_like: feels === "" ? null : Number(feels) };
  try {
    const trip = await api("/api/route", { method: "POST", headers: { "Content-Type": "application/json" },
                                           body: JSON.stringify(body) });
    if (id !== state.routeRequest) return;
    $("feels").parentElement.classList.remove("need");
    showError("");
    drawRoutes(trip);
    renderResult(trip);
  } catch (error) {
    if (id !== state.routeRequest) return;
    if (error.status === 424) $("feels").parentElement.classList.add("need");
    showError(error.message);
    $("result").hidden = true;
    for (const action of ["Shortest", "Shaded"]) map.getSource(`route-${action}`).setData(emptyLine);
  }
}

function drawRoutes(trip) {
  for (const [action, route] of Object.entries(trip.routes)) {
    map.getSource(`route-${action}`).setData({ type: "Feature", geometry: { type: "LineString", coordinates: route.coords } });
    const chosen = action === trip.decision;
    map.setPaintProperty(`route-${action}`, "line-width", chosen ? 7 : 4);
    map.setPaintProperty(`route-${action}`, "line-dasharray", chosen ? [1, 0] : [1.5, 1.5]);
    map.setPaintProperty(`route-${action}-casing`, "line-width", chosen ? 11 : 7);
  }
  // Recommended route drawn last (on top)
  map.moveLayer(`route-${trip.decision}-casing`);
  map.moveLayer(`route-${trip.decision}`);
}

function renderResult(trip) {
  const { routes, bayes: b, mdp, decision } = trip;
  const chosen = routes[decision].stats;
  const short = routes.Shortest.stats, shaded = routes.Shaded.stats;
  const stress = mdp.rows.find((r) => r.state === "Comfortable" && r.action === decision).p_stressed;
  const q = (s, a) => mdp.rows.find((r) => r.state === s && r.action === a).q;
  const other = decision === "Shortest" ? "Shaded" : "Shortest";

  const routeRow = (name, s) => `<tr><td>${name}</td><td>${fmt(s.length_m, 0)} m</td><td>${fmt(s.walk_min)}</td>
    <td>${pct(s.sun_share)}</td><td>${fmt(s.sun_min)}</td><td>${s.expanded} / ${s.dijkstra_expanded}</td></tr>`;
  const mdpRows = mdp.rows.map((r) => `<tr><td>${r.state}, ${r.action}</td><td>${fmt(r.p_comfortable, 3)}</td>
    <td>${fmt(r.p_stressed, 3)}</td><td>${fmt(r.reward)}</td><td><b>${fmt(r.q, 2)}</b></td></tr>`).join("");
  const barrierNote = chosen.barriers.length ? `<p>&#9888; Passes reported barriers: ${chosen.barriers.join("; ")}</p>` : "";

  $("result").innerHTML = `
    <div class="decision ${decision}">
      <b>Recommended: ${decision} route</b>
      <div>${fmt(chosen.length_m, 0)} m · ${fmt(chosen.walk_min, 0)} min · ${pct(chosen.sun_share)} in the sun · ${pct(stress)} heat-stress risk</div>
    </div>
    ${barrierNote}
    <table>
      <tr><th>route</th><th>length</th><th>min</th><th>sun</th><th>sun min</th><th>A* / Dijkstra</th></tr>
      ${routeRow("Shortest", short)}${routeRow("Shaded", shaded)}
    </table>
    <details>
      <summary>1. A* search</summary>
      <p>Two searches on ${trip.start_node} &rarr; ${trip.goal_node}. Edge cost:</p>
      <div class="calc">length × access penalty × (1 + w × sun_fraction) + crossing penalty
Shortest: w = ${short.sun_weight} · Shaded: w = ${shaded.sun_weight}
h(n) = straight-line distance to the goal</div>
      <p>The shaded route is ${fmt(shaded.length_m - short.length_m, 0)} m longer and avoids
         ${fmt(short.sun_m - shaded.sun_m, 0)} m of sun. A* expanded ${short.expanded} nodes where Dijkstra needed ${short.dijkstra_expanded}.</p>
    </details>
    <details>
      <summary>2. Bayes: is it dangerously hot?</summary>
      <p>Sensor: ${trip.weather.source}, feels like ${fmt(trip.weather.feels_like)} &deg;C &rarr; reading <code>${b.reading}</code></p>
      <div class="calc">prior P(Dangerous) = ${fmt(b.prior, 2)}
P(${b.reading}|D) = ${fmt(b.p_reading_given_dangerous, 2)}   P(${b.reading}|Safe) = ${fmt(b.p_reading_given_safe, 2)}
P(${b.reading}) = ${fmt(b.prior, 2)}×${fmt(b.p_reading_given_dangerous, 2)} + ${fmt(1 - b.prior, 2)}×${fmt(b.p_reading_given_safe, 2)} = ${fmt(b.evidence, 3)}
P(D|${b.reading}) = ${fmt(b.joint_dangerous, 3)} / ${fmt(b.evidence, 3)} = <b>${fmt(b.posterior, 3)}</b></div>
    </details>
    <details>
      <summary>3. MDP: Shortest or Shaded?</summary>
      <p>States Comfortable / HeatStressed, γ = ${mdp.gamma}, V0(HeatStressed) = ${mdp.values.HeatStressed},
         heat vulnerability ×${mdp.vulnerability}.</p>
      <table><tr><th>s, a</th><th>&rarr;Comf.</th><th>&rarr;Stress</th><th>R</th><th>Q</th></tr>${mdpRows}</table>
      <div class="calc">Q(s,a) = R + γ·Σ P(s'|s,a)·V0(s')
choose ${decision}: Q = ${fmt(q("Comfortable", decision), 2)} vs ${fmt(q("Comfortable", other), 2)}</div>
    </details>`;
  $("result").hidden = false;
}
