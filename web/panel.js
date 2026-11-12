// HTML for the result part of the panel: the route, why, and the three AI steps (A*, Bayes, MDP).
//
// Person with disabilities: SAYA picks the way (barrier-free, and shaded when the MDP says the heat is
// worth avoiding), so there is one route and no choice to make.
// Person without disabilities: they choose Fastest or Most shade; SAYA's MDP only suggests.

export const LABEL = { Shortest: 'Fastest', Shaded: 'Most shade' };
export const BARRIER_ICON = {
  steps: 'stairs', high_kerb: 'vertical_align_top', broken_ramp: 'block', narrow: 'compress',
  steep: 'trending_up', construction: 'construction',
};

const pct = (x) => `${Math.round(x * 100)}%`;
const km = (m) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`);
const min1 = (x) => `${x.toFixed(1)} min`;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function renderEmpty() {
  return `
    <div class="empty">
      <div class="empty-art" aria-hidden="true"><span class="ms">route</span></div>
      <h3>Plan a walk anyone can make</h3>
      <p>Set a start and a destination: search above or click the map. For a person with disabilities SAYA finds a barrier-free way and checks if the shade is worth it right now.</p>
      <button type="button" class="btn-primary" id="demo-trip"><span class="ms">near_me</span>Try QAIRU → Mega Silk Way</button>
    </div>`;
}

export function renderLoading() {
  return `<div class="skeleton"><i></i><i></i><i class="short"></i></div>`;
}

export function riskOf(trip) {
  const risk = {};
  for (const row of trip.mdp.rows) if (row.state === 'Comfortable') risk[row.action] = row.p_stressed;
  return risk;
}

function heatSentence(trip) {
  const s = trip.routes.Shortest.stats, h = trip.routes.Shaded.stats;
  const risk = riskOf(trip);
  const heat = trip.bayes.posterior;
  if (trip.same_route) return 'There is no shadier way right now, so the fastest way is also the shadiest.';
  const extra = Math.max(h.walk_min - s.walk_min, 0), lessSun = s.sun_min - h.sun_min;
  if (trip.decision === 'Shaded') {
    return `The shadier way takes ${min1(extra)} longer but cuts ${min1(lessSun)} of sun. With a ${pct(heat)} chance of dangerous heat, the heat-stress risk drops from ${pct(risk.Shortest)} to ${pct(risk.Shaded)}.`;
  }
  const reason = heat < 0.3 ? `The heat risk is low right now (${pct(heat)}), so` : `Even with a ${pct(heat)} chance of dangerous heat,`;
  return `${reason} saving ${min1(lessSun)} of sun is not worth ${min1(extra)} more: risk ${pct(risk.Shortest)} vs ${pct(risk.Shaded)}.`;
}

function hero(kind, icon, kicker, title, st) {
  return `
    <div class="hero ${kind}">
      <span class="ms hero-icon">${icon}</span>
      <div>
        <div class="hero-kicker">${kicker}</div>
        <div class="hero-title">${title}</div>
        <div class="hero-sub">${min1(st.walk_min)} · ${km(st.length_m)} · ${pct(st.sun_share)} in the sun</div>
      </div>
    </div>`;
}

function arrival(trip, names) {
  const line = (p, name, verb) => (p.entrance
    ? `${verb} <b>${esc(p.entrance.includes(',') ? p.entrance : `${name}, ${p.entrance}`)}</b>` : null);
  const parts = [line(trip.start_point, names.start, 'Starts at'), line(trip.end_point, names.end, 'Arrives at')].filter(Boolean);
  return parts.length ? `<p class="arrive"><span class="ms">door_front</span><span>${parts.join('. ')}.</span></p>` : '';
}

function disabledResult(trip, names) {
  const action = trip.decision;
  const st = trip.routes[action].stats;
  const direct = trip.direct;
  let avoid = '';
  if (direct && direct.barriers.length) {
    const items = direct.barriers.map((b) => `<li><span class="ms">${BARRIER_ICON[b.type] || 'warning'}</span>${esc(b.name)}</li>`).join('');
    avoid = `
      <div class="avoided">
        <b>The direct way (${km(direct.stats.length_m)}) has ${direct.barriers.length === 1 ? 'a barrier' : `${direct.barriers.length} barriers`} a wheelchair cannot pass:</b>
        <ul>${items}</ul>
        <small>Shown on the map as a grey dashed line. This route goes around ${direct.barriers.length === 1 ? 'it' : 'them'}.</small>
      </div>`;
  } else if (direct && direct.stats.length_m < st.length_m - 20) {
    avoid = `<p class="why">The direct way is ${km(st.length_m - direct.stats.length_m)} shorter, but it runs along busy roads without a sidewalk or over crossings without a traffic light, so this route stays on safer paths.</p>`;
  } else {
    avoid = `<p class="why">The direct way is already barrier-free.</p>`;
  }
  return `
    ${hero('access', 'accessible', 'Person with disabilities · SAYA picks the way', `Barrier-free route${action === 'Shaded' && !trip.same_route ? ', in the shade' : ''}`, st)}
    ${avoid}
    ${arrival(trip, names)}
    <p class="why"><span class="ms inline">auto_awesome</span>${heatSentence(trip)}</p>`;
}

function standardResult(trip, choice, names) {
  const st = trip.routes[choice].stats;
  const risk = riskOf(trip);
  const rows = ['Shortest', 'Shaded'].map((a) => {
    const s = trip.routes[a].stats;
    return `<tr class="${a === choice ? 'chosen' : ''}"><td><i class="sw sw-${a.toLowerCase()}"></i>${LABEL[a]}</td><td>${min1(s.walk_min)}</td><td>${km(s.length_m)}</td><td>${pct(s.sun_share)}</td><td>${pct(risk[a])}</td></tr>`;
  }).join('');
  const suggestion = trip.same_route
    ? 'Fastest and Most shade are the same route right now: there is no shadier way.'
    : `SAYA suggests <b>${LABEL[trip.decision]}</b>. ${heatSentence(trip)}`;
  return `
    ${hero(choice.toLowerCase(), choice === 'Shaded' ? 'umbrella' : 'bolt', 'Person without disabilities · your choice', `${LABEL[choice]} route`, st)}
    <p class="why"><span class="ms inline">auto_awesome</span>${suggestion}</p>
    <table class="compare"><thead><tr><th>option</th><th>time</th><th>length</th><th>in sun</th><th>heat risk</th></tr></thead><tbody>${rows}</tbody></table>
    ${arrival(trip, names)}`;
}

function stepAStar(trip) {
  const rows = ['Shortest', 'Shaded'].map((a) => {
    const st = trip.routes[a].stats;
    return `<tr><td>${LABEL[a]}</td><td>${st.sun_weight}</td><td>${Math.round(st.length_m)} m</td><td>${pct(st.sun_share)}</td><td>${st.expanded}</td><td>${st.dijkstra_expanded}</td></tr>`;
  });
  if (trip.direct) {
    rows.push(`<tr class="muted-row"><td>Direct, no disabilities</td><td>0</td><td>${Math.round(trip.direct.stats.length_m)} m</td><td>${pct(trip.direct.stats.sun_share)}</td><td colspan="2">${trip.direct.barriers.length} barrier${trip.direct.barriers.length === 1 ? '' : 's'}</td></tr>`);
  }
  return `
    <details class="step">
      <summary><span class="step-n">1</span><span><b>A* search</b><small>${trip.profile === 'disabled' ? 'barrier-free routes' : 'the fastest and the shadiest route'}</small></span></summary>
      <div class="step-body">
        <p>Edge cost = <code>length × access × (1 + w × sun)</code> + crossing penalty. For a person with disabilities steps, kerbs without a ramp, broken ramps, narrow or steep paths are impassable. <code>w = 0</code> gives the fastest route, <code>w = 3</code> the shadiest. The heuristic is the straight-line distance, which never overestimates.</p>
        <table><thead><tr><th>route</th><th>w</th><th>length</th><th>sun</th><th>A* nodes</th><th>Dijkstra</th></tr></thead><tbody>${rows.join('')}</tbody></table>
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
    return `<tr class="${chosen ? 'chosen' : ''}"><td>${r.state}, ${LABEL[r.action]}</td><td>${r.p_comfortable.toFixed(3)}</td><td>${r.p_stressed.toFixed(3)}</td><td>${r.reward.toFixed(1)}</td><td>${r.q.toFixed(2)}</td></tr>`;
  }).join('');
  const role = trip.profile === 'disabled' ? 'picks the route' : 'suggests';
  return `
    <details class="step">
      <summary><span class="step-n">3</span><span><b>MDP</b><small>one Bellman update ${role}: ${LABEL[trip.decision]}</small></span></summary>
      <div class="step-body">
        <p>Each minute in the sun can cause heat stress (×${trip.mdp.vulnerability} for this person). Reward = −minutes, ending heat-stressed = ${trip.mdp.values.HeatStressed}. <code>Q = R + ${trip.mdp.gamma} × Σ P(s′) V₀(s′)</code>. Fastest and Most shade are <code>Shortest</code> and <code>Shaded</code> in the code.</p>
        <table><thead><tr><th>s, a</th><th>→ OK</th><th>→ stress</th><th>R</th><th>Q</th></tr></thead><tbody>${rows}</tbody></table>
      </div>
    </details>`;
}

export function renderResult(trip, { choice, feelsLikeEdited, names }) {
  const reading = trip.bayes.reading;
  const main = trip.profile === 'disabled' ? disabledResult(trip, names) : standardResult(trip, choice, names);
  return `
    ${main}
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
