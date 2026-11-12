// SAYA web app. The browser only draws: shadows, A*, Bayes and the MDP run in Python.
import { Buildings3D } from './buildings3d.js';
import { astanaDate, compass, sunPosition } from './sun.js';
import { BARRIER_ICON, BARRIER_KIND, LABEL, esc, renderEmpty, renderLoading, renderNeedsWeather, renderResult } from './panel.js';

const $ = (id) => document.getElementById(id);
const PROFILES = [
  { key: 'disabled', label: 'With disabilities', icon: 'accessible' },
  { key: 'standard', label: 'Without disabilities', icon: 'directions_walk' },
];
const CHOICES = [
  { key: 'Shortest', icon: 'bolt' },
  { key: 'Shaded', icon: 'umbrella' },
];
const QUICK = ['qairu', 'megasilkway', 'nu', 'nuralem', 'botanical', 'aitu'];
const COLOURS = { Shortest: '#e4572e', Shaded: '#1f5fbf' };
const ACCESS = '#0e8a6a';   // the barrier-free route of a person with disabilities

const state = {
  meta: null, start: null, end: null, profile: 'disabled', date: '2026-07-15', minutes: 960,
  feelsLike: null, trip: null, choice: null, playing: false, activeField: null, sun: null,
};
// Person with disabilities: SAYA's decision. Otherwise: the person's choice, or SAYA's suggestion until they choose.
const shownAction = (trip) => (trip.profile === 'disabled' ? trip.decision : state.choice || trip.decision);
const barrierMarkers = {};
const fmt = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.detail || response.statusText);
    error.status = response.status;
    throw error;
  }
  return body;
}

// ------------------------------------------------------------------ map

const STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
const map = new maplibregl.Map({
  container: 'map',
  style: STYLE_URL,
  center: [71.4125, 51.0925], zoom: 15.4, pitch: 58, bearing: -28, maxPitch: 75,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
// Our layers only need the style JSON, not every tile or the icon sprite (which can be slow).
let styleLoaded = false, styleRetries = 0;
const styleReady = new Promise((resolve) => map.once('style.load', () => { styleLoaded = true; resolve(); }));
map.on('error', () => {
  // The free tile server sometimes drops a request: retry the style a few times.
  if (styleLoaded || styleRetries >= 4) return;
  styleRetries += 1;
  setTimeout(() => { if (!styleLoaded) map.setStyle(STYLE_URL); }, 1200 * styleRetries);
});
let buildings3d = null;
const markers = { start: null, end: null };
window.saya = { map, state };   // handy in the browser console

function circle([lat, lon], radius, steps = 160) {
  const ring = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    ring.push([lon + (radius * Math.sin(a)) / (111320 * Math.cos((lat * Math.PI) / 180)), lat + (radius * Math.cos(a)) / 110540]);
  }
  return ring;
}

const empty = { type: 'FeatureCollection', features: [] };
const lineFeature = (coords) => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } });

function addLayers() {
  for (const layer of map.getStyle().layers) {
    if (layer.id.includes('building') || layer.id.startsWith('poi')) map.setLayoutProperty(layer.id, 'visibility', 'none');
  }
  const { center, radius_m: radius } = state.meta;
  const area = circle(center, radius);
  const world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
  map.addSource('night', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [world] } } });
  map.addLayer({ id: 'night', type: 'fill', source: 'night', paint: { 'fill-color': '#0d1733', 'fill-opacity': 0 } });
  map.addSource('shade', { type: 'geojson', data: empty });
  map.addLayer({ id: 'shade', type: 'fill', source: 'shade', paint: { 'fill-color': '#1c2a4f', 'fill-opacity': 0.3 } });
  map.addSource('mask', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [world, area.slice().reverse()] } } });
  map.addLayer({ id: 'mask', type: 'fill', source: 'mask', paint: { 'fill-color': '#f3f1ec', 'fill-opacity': 0.62 } });
  map.addSource('area', { type: 'geojson', data: lineFeature(area) });
  map.addLayer({ id: 'area', type: 'line', source: 'area', paint: { 'line-color': '#7b8494', 'line-width': 1.5, 'line-dasharray': [3, 3] } });
  map.addSource('direct', { type: 'geojson', data: empty });
  map.addLayer({ id: 'direct', type: 'line', source: 'direct', layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#6b7280', 'line-width': 4, 'line-opacity': 0.75, 'line-dasharray': [1.2, 1.2] } });
  for (const action of ['Shortest', 'Shaded']) {
    map.addSource(`route-${action}`, { type: 'geojson', data: empty });
    map.addLayer({ id: `casing-${action}`, type: 'line', source: `route-${action}`, layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': 10, 'line-opacity': 0.95 } });
    map.addLayer({ id: `route-${action}`, type: 'line', source: `route-${action}`, layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': COLOURS[action], 'line-width': 6 } });
  }
}

// A click on a barrier or a map fix opens a card about it; it never moves A or B.
const info = new maplibregl.Popup({ closeOnClick: false, offset: 20, maxWidth: '300px', className: 'info-popup', focusAfterOpen: false });
let infoKey = null;
info.on('close', () => { infoKey = null; });
const ON_MARKER = '.maplibregl-marker, .maplibregl-popup';

function openInfo(key, lngLat, html) {
  if (infoKey === key && info.isOpen()) { info.remove(); return; }
  hideTooltip();
  info.setLngLat(lngLat).setHTML(html);  // an open card moves to the new marker in place
  if (!info.isOpen()) info.addTo(map);
  infoKey = key;
}

function infoCard(icon, kind, title, rows, source, extra = '') {
  const items = rows.map(([ms, text]) => `<li><span class="ms">${ms}</span><span>${text}</span></li>`).join('');
  return `<div class="info ${kind}">
    <div class="info-head"><span class="info-icon"><span class="ms">${icon}</span></span><div>${title}</div></div>
    <ul class="info-rows">${items}</ul>${extra}<small class="info-src">${source}</small></div>`;
}

function barrierInfo(barrier, el) {
  const kind = BARRIER_KIND[barrier.type] || 'Barrier';
  const closedForAll = barrier.type === 'construction';
  const rows = [
    ['accessible', '<b>Person with disabilities:</b> impassable, SAYA routes around it'],
    ['directions_walk', closedForAll ? '<b>Person without disabilities:</b> also closed' : '<b>Person without disabilities:</b> can pass'],
  ];
  const extra = el.classList.contains('avoided') ? '<p class="info-flag">The direct way passes here. The route on the map goes around it.</p>' : '';
  const source = barrier.source === 'OpenStreetMap'
    ? `From OpenStreetMap${barrier.note ? `: ${esc(barrier.note.replace(/^Mapped in OpenStreetMap as /, ''))}` : ''}`
    : 'Simulated resident report for the demo, not a verified barrier';
  return infoCard(BARRIER_ICON[barrier.type] || 'warning', 'barrier', `<small>Barrier · ${kind}</small><b>${esc(barrier.name)}</b>`, rows, source, extra);
}

function fixInfo(fix) {
  const rows = [['info', esc(fix.note)], ['route', 'Routes for both profiles can now cross here']];
  return infoCard('build', 'fix', `<small>Map fix</small><b>A ${fix.length_m} m link added to the walk network</b>`, rows, 'Added by hand in data/map_fixes.json');
}

function clickable(el, label, open) {
  el.setAttribute('role', 'button');
  el.setAttribute('aria-label', label);
  el.tabIndex = 0;
  el.addEventListener('click', open);
  el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
}

function addBarriers() {
  for (const barrier of state.meta.barriers) {
    const el = document.createElement('div');
    el.className = 'barrier-marker';
    el.innerHTML = `<span class="dot"><span class="ms">${BARRIER_ICON[barrier.type] || 'warning'}</span></span>`;
    const lngLat = [barrier.lon, barrier.lat];
    new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map);
    clickable(el, `Barrier: ${barrier.name}`, () => openInfo(`barrier-${barrier.id}`, lngLat, barrierInfo(barrier, el)));
    barrierMarkers[barrier.id] = el;
  }
  for (const [i, fix] of (state.meta.map_fixes || []).entries()) {
    const el = document.createElement('div');
    el.className = 'fix-marker';
    el.innerHTML = '<span class="ms">build</span>';
    const lngLat = [fix.lon, fix.lat];
    new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map);
    clickable(el, `Map fix: ${fix.length_m} m link added`, () => openInfo(`fix-${i}`, lngLat, fixInfo(fix)));
  }
}

function markAvoided(barriers) {
  const ids = new Set(barriers.map((b) => b.id));
  for (const [id, el] of Object.entries(barrierMarkers)) el.classList.toggle('avoided', ids.has(Number(id)) || ids.has(id));
}

// ------------------------------------------------------------------ trip points

function placeLabel(lat, lon) {
  let best = null, bestDistance = 70;
  for (const place of state.meta.search) {
    const d = Math.hypot((place.lat - lat) * 110540, (place.lon - lon) * 111320 * Math.cos((lat * Math.PI) / 180));
    if (d < bestDistance) { best = place; bestDistance = d; }
  }
  return best ? best.name : `Point ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}

function setPoint(which, lat, lon, label) {
  state[which] = { lat, lon, label: label || placeLabel(lat, lon) };
  if (!markers[which]) {
    const el = document.createElement('div');
    el.className = `pin-marker pin-${which === 'start' ? 'a' : 'b'}`;
    el.innerHTML = `<span><b>${which === 'start' ? 'A' : 'B'}</b></span>`;
    markers[which] = new maplibregl.Marker({ element: el, draggable: true, anchor: 'bottom' }).setLngLat([lon, lat]).addTo(map);
    markers[which].on('dragend', () => {
      const p = markers[which].getLngLat();
      setPoint(which, p.lat, p.lng);
      refreshRoute();
    });
  } else {
    markers[which].setLngLat([lon, lat]);
  }
  $(which === 'start' ? 'from' : 'to').value = state[which].label;
  updateFields();
}

function removePoint(which) {
  state[which] = null;
  markers[which]?.remove();
  markers[which] = null;
  $(which === 'start' ? 'from' : 'to').value = '';
}

function clearPoint(which) {
  removePoint(which);
  clearRoute();
  updateFields();
}

function updateFields() {
  for (const which of ['start', 'end']) {
    document.querySelector(`.field[data-field="${which}"]`).classList.toggle('filled', Boolean(state[which]));
  }
  if (!state.start || !state.end) {
    $('result').innerHTML = renderEmpty();
    wireEmpty();
  }
}

function clearRoute() {
  state.trip = null;
  renderSummary();
  for (const action of ['Shortest', 'Shaded']) map.getSource(`route-${action}`)?.setData(empty);
  map.getSource('direct')?.setData(empty);
  markAvoided([]);
}

function fitTrip() {
  if (!state.start || !state.end) return;
  const bounds = new maplibregl.LngLatBounds();
  bounds.extend([state.start.lon, state.start.lat]).extend([state.end.lon, state.end.lat]);
  const wide = innerWidth > 760;
  map.fitBounds(bounds, {
    padding: wide ? { left: 470, right: 130, top: 120, bottom: 120 } : { left: 50, right: 50, top: 80, bottom: innerHeight * 0.68 },
    maxZoom: 16.6, pitch: map.getPitch(), bearing: map.getBearing(), duration: 900,
  });
}

// ------------------------------------------------------------------ search

function setupSearch() {
  const list = $('suggest');
  let options = [], active = -1, target = null;
  const close = () => { list.hidden = true; active = -1; };
  const choose = (place) => {
    setPoint(target, place.lat, place.lon, place.name);
    close();
    if (target === 'start' && !state.end) $('to').focus(); else $(target === 'start' ? 'from' : 'to').blur();
    if (state.start && state.end) { fitTrip(); refreshRoute(); }
  };
  const show = (input) => {
    const query = input.value.trim().toLowerCase();
    const showAll = !query || (state[target] && input.value === state[target].label);
    options = state.meta.search.filter((p) => showAll || p.name.toLowerCase().includes(query)).slice(0, 8);
    list.innerHTML = options.map((p, i) => `<li role="option" data-i="${i}" class="${i === active ? 'active' : ''}"><span class="ms">${p.type === 'park' || p.type === 'garden' ? 'park' : p.type === 'landmark' ? 'star' : 'location_on'}</span><span>${p.name}</span></li>`).join('')
      || '<li class="none">No place with that name. Click the map instead.</li>';
    list.dataset.for = target;
    list.hidden = false;
  };
  for (const [id, which] of [['from', 'start'], ['to', 'end']]) {
    const input = $(id);
    input.addEventListener('focus', () => { target = which; state.activeField = which; active = -1; input.select(); show(input); });
    input.addEventListener('input', () => { active = -1; show(input); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        active = Math.max(0, Math.min(options.length - 1, active + (e.key === 'ArrowDown' ? 1 : -1)));
        show(input);
      } else if (e.key === 'Enter' && options.length) {
        choose(options[Math.max(active, 0)]);
      } else if (e.key === 'Escape') { close(); input.blur(); }
    });
    input.addEventListener('blur', () => setTimeout(() => {
      if (document.activeElement === input) return;
      close();
      if (state.activeField === which) state.activeField = null;
      input.value = state[which] ? state[which].label : '';
    }, 180));
  }
  list.addEventListener('mousedown', (e) => {
    const li = e.target.closest('li[data-i]');
    if (li) { e.preventDefault(); choose(options[Number(li.dataset.i)]); }
  });
  document.querySelectorAll('.field-clear').forEach((b) => b.addEventListener('click', (e) => { e.preventDefault(); clearPoint(b.dataset.clear); }));
  $('swap').addEventListener('click', () => {
    const { start, end } = state;
    if (!start && !end) return;
    removePoint('start');
    removePoint('end');
    if (end) setPoint('start', end.lat, end.lon, end.label);
    if (start) setPoint('end', start.lat, start.lon, start.label);
    updateFields();
    refreshRoute();
  });
  $('chips').innerHTML = QUICK.filter((k) => state.meta.places[k]).map((k) => `<button type="button" class="chip" data-place="${k}">${state.meta.places[k].name.split(',')[0]}</button>`).join('');
  $('chips').addEventListener('mousedown', (e) => { if (e.target.closest('[data-place]')) e.preventDefault(); });
  $('chips').addEventListener('click', (e) => {
    const chip = e.target.closest('[data-place]');
    if (!chip) return;
    const place = state.meta.places[chip.dataset.place];
    const which = state.activeField || (!state.start ? 'start' : 'end');
    setPoint(which, place.lat, place.lon, place.name);
    document.activeElement?.blur?.();
    if (state.start && state.end) { fitTrip(); refreshRoute(); }
  });
}

// ------------------------------------------------------------------ profile and time

function updateChoice() {
  const disabled = state.profile === 'disabled';
  $('auto-note').hidden = !disabled;
  $('choice-box').hidden = disabled;
  const suggested = state.trip && state.trip.profile === 'standard' ? state.trip.decision : null;
  const shown = state.choice || suggested;
  $('choice').innerHTML = CHOICES.map((c) => `
    <button type="button" role="radio" data-choice="${c.key}" aria-checked="${c.key === shown}" class="${c.key === shown ? 'on' : ''}">
      <span class="ms">${c.icon}</span><span>${LABEL[c.key]}</span>${c.key === suggested ? '<em>SAYA suggests</em>' : ''}</button>`).join('');
}

function setupControls() {
  $('profiles').innerHTML = PROFILES.map((p) => `
    <button type="button" role="radio" data-profile="${p.key}" aria-checked="${p.key === state.profile}" class="${p.key === state.profile ? 'on' : ''}">
      <span class="ms">${p.icon}</span><span>${p.label}</span></button>`).join('');
  $('profiles').addEventListener('click', (e) => {
    const button = e.target.closest('[data-profile]');
    if (!button || button.dataset.profile === state.profile) return;
    state.profile = button.dataset.profile;
    $('profiles').querySelectorAll('button').forEach((b) => {
      const on = b.dataset.profile === state.profile;
      b.classList.toggle('on', on);
      b.setAttribute('aria-checked', on);
    });
    updateChoice();
    refreshRoute();
  });
  $('choice').addEventListener('click', (e) => {
    const button = e.target.closest('[data-choice]');
    if (!button) return;
    state.choice = button.dataset.choice;
    updateChoice();
    if (state.trip) { drawRoutes(); renderPanel(); }
  });
  updateChoice();

  $('date').value = state.date;
  $('date').addEventListener('change', () => {
    if (!$('date').value) return;
    state.date = $('date').value;
    state.feelsLike = null;
    drawSunCurve();
    onTimeChange();
  });
  const slider = $('time');
  slider.value = state.minutes;
  let timer = null;
  slider.addEventListener('input', () => {
    state.minutes = Number(slider.value);
    updateClock();
    clearTimeout(timer);
    timer = setTimeout(onTimeChange, 140);
  });
  $('play').addEventListener('click', togglePlay);
  $('ticks').innerHTML = [300, 540, 780, 1020, 1320].map((m) => `<span style="left:${((m - 300) / 1020) * 100}%">${fmt(m)}</span>`).join('');

  for (const [id, action] of [['tool-3d', toggle3d], ['tool-shade', toggleShade], ['tool-buildings', toggleBuildings], ['tool-fit', fitArea]]) {
    $(id).addEventListener('click', action);
  }
  $('sheet-handle').addEventListener('click', () => $('panel').classList.toggle('collapsed'));
  $('summary').addEventListener('click', () => {
    $('panel').classList.remove('collapsed');
    $('result').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function setTool(id, on) {
  $(id).classList.toggle('on', on);
  $(id).setAttribute('aria-pressed', on);
}
function toggle3d() {
  const flat = map.getPitch() > 5;
  map.easeTo({ pitch: flat ? 0 : 58, bearing: flat ? 0 : -28, duration: 700 });
  setTool('tool-3d', !flat);
}
function toggleShade() {
  const on = map.getLayoutProperty('shade', 'visibility') === 'none';
  map.setLayoutProperty('shade', 'visibility', on ? 'visible' : 'none');
  setTool('tool-shade', on);
}
function toggleBuildings() {
  const on = !buildings3d.visible;
  buildings3d.setVisible(on);
  setTool('tool-buildings', on);
}
function fitArea() {
  const [lat, lon] = state.meta.center, r = state.meta.radius_m;
  const dLat = r / 110540, dLon = r / (111320 * Math.cos((lat * Math.PI) / 180));
  map.fitBounds([[lon - dLon, lat - dLat], [lon + dLon, lat + dLat]],
    { padding: innerWidth > 760 ? { left: 440, right: 60, top: 60, bottom: 60 } : 30, pitch: 45, duration: 900 });
}

const curveY = (alt) => 56 - ((Math.max(alt, -6) + 6) / 76) * 52;

function updateClock() {
  $('time-text').textContent = fmt(state.minutes);
  const [lat, lon] = state.meta.center;
  const sun = sunPosition(astanaDate(state.date, state.minutes), lat, lon);
  state.sun = sun;
  const up = sun.altitude > 0;
  const shadow = up ? Math.min(10 / Math.tan((sun.altitude * Math.PI) / 180), 250) : null;
  $('sun-line').innerHTML = up
    ? `<span class="ms">wb_sunny</span><span>${sun.altitude.toFixed(0)}° from ${compass(sun.azimuth)} · shadows point ${compass(sun.azimuth + 180)} · a 10 m wall casts ${shadow.toFixed(0)} m</span>`
    : `<span class="ms">dark_mode</span><span>Sun is down: no shadows, every path is in the shade</span>`;
  $('compass').classList.toggle('night', !up);
  $('compass-sun').style.transform = `rotate(${sun.azimuth}deg)`;
  $('compass-shadow').style.transform = `rotate(${sun.azimuth}deg)`;
  const marker = $('sun-now');
  if (marker) {
    marker.setAttribute('cx', state.minutes - 300);
    marker.setAttribute('cy', curveY(sun.altitude));
  }
  buildings3d?.setSun(sun.altitude, sun.azimuth);
  const night = Math.min(Math.max((2 - sun.altitude) / 8, 0), 1);
  if (map.getLayer('night')) map.setPaintProperty('night', 'fill-opacity', 0.42 * night);
}

function drawSunCurve() {
  const [lat, lon] = state.meta.center;
  let path = '';
  for (let m = 300; m <= 1320; m += 10) {
    const { altitude } = sunPosition(astanaDate(state.date, m), lat, lon);
    path += `${m === 300 ? 'M' : 'L'}${m - 300},${curveY(altitude).toFixed(1)} `;
  }
  const horizon = curveY(0);
  $('sun-curve').innerHTML = `
    <defs><linearGradient id="day" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f7b955" stop-opacity="0.6"/><stop offset="1" stop-color="#f7b955" stop-opacity="0.08"/></linearGradient>
    <clipPath id="above"><rect x="0" y="0" width="1020" height="${horizon}"/></clipPath></defs>
    <rect x="0" y="${horizon}" width="1020" height="${60 - horizon}" fill="#e7eaf2"/>
    <path d="${path} L1020,60 L0,60 Z" fill="url(#day)" clip-path="url(#above)"/>
    <path d="${path}" fill="none" stroke="#e39b2d" stroke-width="2" vector-effect="non-scaling-stroke"/>
    <line x1="0" x2="1020" y1="${horizon}" y2="${horizon}" stroke="#c3c8d3" stroke-width="1" vector-effect="non-scaling-stroke"/>
    <ellipse id="sun-now" rx="9" ry="7" fill="#f2a51a" stroke="#fff" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`;
  updateClock();
}

let playTimer = null;
function togglePlay() {
  state.playing = !state.playing;
  $('play').classList.toggle('playing', state.playing);
  $('play').innerHTML = `<span class="ms">${state.playing ? 'pause' : 'play_arrow'}</span>`;
  $('play').setAttribute('aria-label', state.playing ? 'Pause' : 'Play the whole day');
  clearInterval(playTimer);
  if (!state.playing) { refreshRoute(); return; }
  playTimer = setInterval(() => {
    state.minutes = state.minutes >= 1320 ? 300 : state.minutes + 15;
    $('time').value = state.minutes;
    updateClock();
    onTimeChange();
  }, 700);
}

// ------------------------------------------------------------------ server calls

let shadeRequest = 0, routeRequest = 0, busy = 0, routeInFlight = false;
function setBusy(delta) {
  busy += delta;
  $('progress').classList.toggle('on', busy > 0);
}

function onTimeChange() {
  refreshShade();
  if (!state.playing || !routeInFlight) refreshRoute();
}

async function refreshShade() {
  const id = ++shadeRequest;
  setBusy(1);
  try {
    const data = await api(`/api/shade?date=${state.date}&time=${fmt(state.minutes)}`);
    if (id !== shadeRequest) return;
    map.getSource('shade').setData(data.shade);
  } catch (error) {
    if (id === shadeRequest) toast(error.message);
  } finally { setBusy(-1); }
}

async function refreshRoute() {
  if (!state.start || !state.end) return;
  const id = ++routeRequest;
  routeInFlight = true;
  setBusy(1);
  if (!state.trip) $('result').innerHTML = renderLoading();
  $('result').classList.add('stale');
  try {
    const trip = await api('/api/route', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start: [state.start.lat, state.start.lon], end: [state.end.lat, state.end.lon],
        date: state.date, time: fmt(state.minutes), profile: state.profile, feels_like: state.feelsLike,
      }),
    });
    if (id !== routeRequest) return;
    state.trip = trip;
    drawRoutes();
    renderPanel();
  } catch (error) {
    if (id !== routeRequest) return;
    clearRoute();
    if (error.status === 424) {
      $('result').innerHTML = renderNeedsWeather(error.message);
      wireFeelsLike();
    } else {
      $('result').innerHTML = renderEmpty();
      wireEmpty();
      toast(error.message);
    }
  } finally {
    if (id === routeRequest) { routeInFlight = false; $('result').classList.remove('stale'); }
    setBusy(-1);
  }
}

function drawRoutes() {
  const trip = state.trip;
  const shown = shownAction(trip);
  // One route on the map: the one SAYA picked, or the one the person chose.
  const colour = trip.profile === 'disabled' ? ACCESS : COLOURS[shown];
  for (const action of ['Shortest', 'Shaded']) {
    map.getSource(`route-${action}`).setData(action === shown ? lineFeature(trip.routes[action].coords) : empty);
  }
  map.setPaintProperty(`route-${shown}`, 'line-color', colour);
  map.setPaintProperty(`ghost-${shown}`, 'line-color', colour);
  map.moveLayer(`casing-${shown}`, 'buildings-3d');
  map.moveLayer(`route-${shown}`, 'buildings-3d');
  // For a person with disabilities, the direct way in grey shows what the route goes around.
  const avoided = trip.profile === 'disabled' && trip.direct ? trip.direct.barriers : [];
  map.getSource('direct').setData(avoided.length ? lineFeature(trip.direct.coords) : empty);
  markAvoided(avoided);
  // The pins move to the entrance the route really starts and ends at.
  for (const [which, point] of [['start', trip.start_point], ['end', trip.end_point]]) {
    markers[which]?.setLngLat(point.entrance ? [point.lon, point.lat] : [state[which].lon, state[which].lat]);
    const input = $(which === 'start' ? 'from' : 'to');
    if (document.activeElement !== input) {
      input.value = entranceLabel(which, point);
      input.scrollLeft = 0;   // show the start of a long name, not its end
    }
  }
}

function entranceLabel(which, point) {
  const label = state[which].label;
  if (!point.entrance) return label;
  return point.entrance.includes(',') ? point.entrance : `${label} · ${point.entrance}`;
}

function renderSummary() {
  const trip = state.trip;
  const el = $('summary');
  if (!trip) { el.hidden = true; return; }
  const shown = shownAction(trip);
  const best = trip.routes[shown].stats;
  const title = trip.profile === 'disabled' ? 'Barrier-free route' : `${LABEL[shown]} route`;
  el.className = `summary ${trip.profile === 'disabled' ? 'access' : shown.toLowerCase()}`;
  el.innerHTML = `<span class="ms">${trip.profile === 'disabled' ? 'accessible' : shown === 'Shaded' ? 'umbrella' : 'bolt'}</span><b>${title}</b><span>${best.walk_min.toFixed(0)} min · ${Math.round(best.sun_share * 100)}% sun · ${fmt(state.minutes)}</span><span class="ms">expand_more</span>`;
  el.hidden = false;
}

function renderPanel() {
  renderSummary();
  updateChoice();
  $('result').innerHTML = renderResult(state.trip, {
    choice: shownAction(state.trip), feelsLikeEdited: state.feelsLike !== null,
    names: { start: state.start.label, end: state.end.label },
  });
  $('edit-feels')?.addEventListener('click', () => {
    if (state.feelsLike !== null) { state.feelsLike = null; refreshRoute(); return; }
    $('feels-edit').hidden = false;
    $('feels-input').focus();
  });
  wireFeelsLike();
}

function wireFeelsLike() {
  const apply = () => {
    const value = Number($('feels-input').value);
    if ($('feels-input').value === '' || Number.isNaN(value)) return;
    state.feelsLike = value;
    refreshRoute();
  };
  $('feels-apply')?.addEventListener('click', apply);
  $('feels-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') apply(); });
}

function wireEmpty() {
  $('demo-trip')?.addEventListener('click', () => {
    const { qairu, megasilkway } = state.meta.places;
    setPoint('start', qairu.lat, qairu.lon, qairu.name);
    setPoint('end', megasilkway.lat, megasilkway.lon, megasilkway.name);
    fitTrip();
    refreshRoute();
  });
}

// ------------------------------------------------------------------ tooltip, toast

const tooltip = $('tooltip');
function showTooltip(anchor, html, point) {
  tooltip.innerHTML = html;
  tooltip.hidden = false;
  const rect = anchor ? anchor.getBoundingClientRect() : null;
  const x = point ? point.x : rect.left + rect.width / 2, y = point ? point.y : rect.top;
  tooltip.style.left = `${Math.max(8, Math.min(x + 14, innerWidth - tooltip.offsetWidth - 8))}px`;
  tooltip.style.top = `${Math.max(y - tooltip.offsetHeight - 12, 8)}px`;
}
function hideTooltip() { tooltip.hidden = true; }

let toastTimer = null;
function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 5000);
}

function buildingTooltip(p) {
  const kind = p.kind === 'yes' ? 'Building' : p.kind.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
  const title = p.name || kind;
  const raised = p.min_height > 0.3 ? ` · from ${p.min_height.toFixed(0)} m up` : '';
  const shape = p.shape === 'sphere' ? ' · sphere' : p.shape !== 'flat' ? ` · ${p.shape} roof` : '';
  return `<b>${title}</b><span>${p.height.toFixed(0)} m tall${raised}${shape}</span><small>${p.height_source}</small>`;
}

let lastPick = 0;
function onMouseMove(e) {
  const now = performance.now();
  if (now - lastPick < 60 || !buildings3d) return;
  lastPick = now;
  if (e.originalEvent.target.closest?.(ON_MARKER)) { hideTooltip(); map.getCanvas().style.cursor = ''; return; }
  const p = buildings3d.pick(e.point.x, e.point.y);
  if (p) {
    showTooltip(null, buildingTooltip(p), { x: e.originalEvent.clientX, y: e.originalEvent.clientY });
    map.getCanvas().style.cursor = 'crosshair';
  } else {
    hideTooltip();
    map.getCanvas().style.cursor = '';
  }
}

// ------------------------------------------------------------------ start

async function start() {
  const [meta, buildings, trees] = await Promise.all([api('/api/meta'), api('/api/buildings'), api('/api/trees')]);
  state.meta = meta;
  state.date = meta.defaults.date;
  state.profile = meta.defaults.profile;
  const [hh, mm] = meta.defaults.time.split(':').map(Number);
  state.minutes = hh * 60 + mm;
  setupControls();
  setupSearch();
  drawSunCurve();
  await styleReady;
  addLayers();
  const [lat, lon] = meta.center;
  buildings3d = new Buildings3D(maplibregl, buildings, [lon, lat], trees);
  map.addLayer(buildings3d);
  // Faint copies on top of the buildings, so a route behind a building stays visible.
  for (const action of ['Shortest', 'Shaded']) {
    map.addLayer({ id: `ghost-${action}`, type: 'line', source: `route-${action}`, layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': COLOURS[action], 'line-width': 4, 'line-opacity': 0.4, 'line-dasharray': [1, 1.6] } });
  }
  addBarriers();
  updateClock();
  map.on('mousemove', onMouseMove);
  map.on('mouseout', hideTooltip);
  map.on('click', (e) => {
    if (e.originalEvent.target.closest?.(ON_MARKER)) return;  // a marker handles its own click
    if (info.isOpen()) { info.remove(); return; }  // the first click elsewhere only closes the card
    const which = state.activeField || (!state.start ? 'start' : 'end');
    setPoint(which, e.lngLat.lat, e.lngLat.lng);
    document.activeElement?.blur?.();
    if (state.start && state.end) refreshRoute();
  });
  const { start: s, end: t } = meta.defaults;
  setPoint('start', meta.places[s].lat, meta.places[s].lon, meta.places[s].name);
  setPoint('end', meta.places[t].lat, meta.places[t].lon, meta.places[t].name);
  fitTrip();
  refreshShade();
  refreshRoute();
}

start().catch((error) => toast(`Could not start: ${error.message}`));
