// HTML for the result part of the panel: the decision, the two routes, and the
// three AI steps (A*, Bayes, MDP) with their numbers.

const PROFILE_WHO = {
  wheelchair: 'a wheelchair user',
  elderly: 'an elderly pedestrian',
  standard: 'a pedestrian',
};

const pct = (x) => `${Math.round(x * 100)}%`;
const km = (m) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`);
const min1 = (x) => `${x.toFixed(1)} min`;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function renderEmpty() {
  return `
    <div class="empty">
      <div class="empty-art" aria-hidden="true"><span class="ms">route</span></div>
      <h3>Plan a cooler walk</h3>
      <p>Set a start and a destination: search above or click the map. SAYA finds routes this person can actually pass, measures the sun on each, and checks if the shade is worth it right now.</p>
      <button type="button" class="btn-primary" id="demo-trip"><span class="ms">near_me</span>Try AITU → Mega Silk Way</button>
    </div>`;
}

export function renderLoading() {
  return `<div class="skeleton"><i></i><i></i><i class="short"></i></div>`;
}

function why(trip) {
  const s = trip.routes.Shortest.stats, h = trip.routes.Shaded.stats;
  const risk = riskOf(trip);
  const extra = h.walk_min - s.walk_min;
  const lessSun = s.sun_min - h.sun_min;
  const heat = trip.bayes.posterior;
  if (trip.decision === 'Shaded') {
    return `The shaded route takes ${min1(Math.max(extra, 0))} longer but cuts ${min1(lessSun)} of sun. With a ${pct(heat)} chance of dangerous heat, the heat-stress risk drops from ${pct(risk.Shortest)} to ${pct(risk.Shaded)}.`;
  }
  if (lessSun < 0.5) return `Both routes get about the same sun, so the shorter one wins.`;
  const reason = heat < 0.3 ? `The heat risk is low right now (${pct(heat)}), so` : `Even with a ${pct(heat)} chance of dangerous heat,`;
  return `${reason} saving ${min1(lessSun)} of sun is not worth ${min1(Math.max(extra, 0))} more walking: risk ${pct(risk.Shortest)} vs ${pct(risk.Shaded)}.`;
}

export function riskOf(trip) {
  const risk = {};
  for (const row of trip.mdp.rows) if (row.state === 'Comfortable') risk[row.action] = row.p_stressed;
  return risk;
}

function routeCard(trip, action, focus) {
  const st = trip.routes[action].stats;
  const risk = riskOf(trip)[action];
  const best = trip.decision === action;
  const classes = ['route-card', action.toLowerCase(), best ? 'best' : '', focus === action ? 'focused' : ''].join(' ');
  return `
    <button type="button" class="${classes}" data-route="${action}" aria-pressed="${focus === action}">
      <div class="rc-head"><i class="rc-swatch"></i><b>${action}</b>${best ? '<span class="badge">Recommended</span>' : ''}</div>
      <div class="rc-main"><span>${min1(st.walk_min)}</span><span>${km(st.length_m)}</span></div>
      <div class="sunbar" title="${pct(st.sun_share)} of the route in direct sun"><i style="width:${(st.sun_share * 100).toFixed(1)}%"></i></div>
      <div class="rc-meta"><span><span class="ms">wb_sunny</span>${min1(st.sun_min)} in sun</span><span><span class="ms">thermometer</span>risk ${pct(risk)}</span></div>
    </button>`;
}

function stepAStar(trip) {
  const rows = ['Shortest', 'Shaded'].map((a) => {
    const st = trip.routes[a].stats;
    return `<tr><td>${a}</td><td>${st.sun_weight}</td><td>${Math.round(st.length_m)} m</td><td>${pct(st.sun_share)}</td><td>${st.expanded}</td><td>${st.dijkstra_expanded}</td></tr>`;
  }).join('');
  return `
    <details class="step">
      <summary><span class="step-n">1</span><span><b>A* search</b><small>two routes this person can pass</small></span></summary>
      <div class="step-body">
        <p>Edge cost = <code>length × access × (1 + w × sun)</code> + crossing penalty. Steps and broken ramps are impassable for a wheelchair. <code>w = 0</code> gives the shortest accessible route, <code>w = 3</code> the shaded one. The heuristic is the straight-line distance, which never overestimates.</p>
        <table><thead><tr><th>route</th><th>w</th><th>length</th><th>sun</th><th>A* nodes</th><th>Dijkstra</th></tr></thead><tbody>${rows}</tbody></table>
      </div>
    </details>`;
}

function stepBayes(trip) {
  const b = trip.bayes;
  return `
    <details class="step">
      <summary><span class="step-n">2</span><span><b>Bayes</b><small>P(dangerous heat) = ${pct(b.posterior)}</small></span></summary>
      <div class="step-body">
        <p>Sensor: ${esc(trip.weather.source)}. Reading <b>${b.reading}</b> (cool &lt; 24 °C ≤ warm &lt; 30 °C ≤ hot).</p>
        <div class="belief"><span>prior ${pct(b.prior)}</span><div class="belief-bar"><i class="prior" style="width:${b.prior * 100}%"></i><i class="post" style="width:${b.posterior * 100}%"></i></div><span>posterior ${pct(b.posterior)}</span></div>
        <div class="calc">P(${b.reading}) = ${b.prior.toFixed(2)} × ${b.p_reading_given_dangerous.toFixed(2)} + ${(1 - b.prior).toFixed(2)} × ${b.p_reading_given_safe.toFixed(2)} = ${b.evidence.toFixed(3)}
P(Dangerous | ${b.reading}) = ${b.joint_dangerous.toFixed(3)} / ${b.evidence.toFixed(3)} = <b>${b.posterior.toFixed(3)}</b></div>
      </div>
    </details>`;
}

function stepMdp(trip) {
  const rows = trip.mdp.rows.map((r) => {
    const chosen = r.state === 'Comfortable' && r.action === trip.decision;
    return `<tr class="${chosen ? 'chosen' : ''}"><td>${r.state}, ${r.action}</td><td>${r.p_comfortable.toFixed(3)}</td><td>${r.p_stressed.toFixed(3)}</td><td>${r.reward.toFixed(1)}</td><td>${r.q.toFixed(2)}</td></tr>`;
  }).join('');
  return `
    <details class="step">
      <summary><span class="step-n">3</span><span><b>MDP</b><small>one Bellman update → ${trip.decision}</small></span></summary>
      <div class="step-body">
        <p>Each minute in the sun can cause heat stress (×${trip.mdp.vulnerability} for this person). Reward = −minutes, ending heat-stressed = ${trip.mdp.values.HeatStressed}. <code>Q = R + ${trip.mdp.gamma} × Σ P(s′) V₀(s′)</code></p>
        <table><thead><tr><th>s, a</th><th>→ OK</th><th>→ stress</th><th>R</th><th>Q</th></tr></thead><tbody>${rows}</tbody></table>
      </div>
    </details>`;
}

export function renderResult(trip, { profile, focus, feelsLikeEdited }) {
  const best = trip.routes[trip.decision].stats;
  const shaded = trip.decision === 'Shaded';
  const reading = trip.bayes.reading;
  return `
    <div class="hero ${trip.decision.toLowerCase()}">
      <span class="ms hero-icon">${shaded ? 'umbrella' : 'bolt'}</span>
      <div>
        <div class="hero-kicker">Best for ${PROFILE_WHO[profile] || 'this walker'}</div>
        <div class="hero-title">Take the ${shaded ? 'shaded' : 'shortest'} route</div>
        <div class="hero-sub">${min1(best.walk_min)} · ${km(best.length_m)} · ${pct(best.sun_share)} in the sun</div>
      </div>
    </div>
    <p class="why">${why(trip)}</p>
    <div class="routes">${routeCard(trip, 'Shaded', focus)}${routeCard(trip, 'Shortest', focus)}</div>
    <div class="heat ${reading}">
      <span class="ms">device_thermostat</span>
      <span>Feels like <b>${trip.weather.feels_like.toFixed(1)} °C</b> · ${reading}${feelsLikeEdited ? ' · set by you' : ''}</span>
      <button type="button" class="link" id="edit-feels">${feelsLikeEdited ? 'Use forecast' : 'Change'}</button>
    </div>
    <div class="feels-edit" id="feels-edit" hidden>
      <input type="number" id="feels-input" step="0.5" min="-40" max="55" value="${trip.weather.feels_like}" aria-label="Feels-like temperature in °C">
      <button type="button" class="btn-small" id="feels-apply">Apply</button>
    </div>
    <h2 class="steps-title">How SAYA decided</h2>
    ${stepAStar(trip)}${stepBayes(trip)}${stepMdp(trip)}`;
}

export function renderNeedsWeather(message) {
  return `
    <div class="notice">
      <span class="ms">cloud_off</span>
      <div><b>No weather forecast for this date</b><p>${esc(message)}</p>
        <div class="feels-edit"><input type="number" id="feels-input" step="0.5" min="-40" max="55" placeholder="°C" aria-label="Feels-like temperature in °C">
        <button type="button" class="btn-small" id="feels-apply">Use this temperature</button></div></div>
    </div>`;
}
