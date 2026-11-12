/**
 * Plaza: a 9 × 9 plaza of paving stones on a plinth, with three buildings on
 * it and the long shadows a low sun throws from them, down to the right. A
 * stone in shade sits a hair lower, keeps the medium stroke and carries one
 * medium dot; a stone in the sun takes the silhouette's stroke. The start has
 * tactile paving. The pointer picks a destination stone and a real A*
 * runs from the start corner: 4-neighbour moves, the Manhattan heuristic, a
 * step costing 1 in the shade and 1 + w in the sun. The route's stones rise a
 * step and take the bright stroke, staggered outward from the start along the
 * route. The slider is w, the sun weight.
 *
 * The pattern: discrete items (Riffle) picked through the ground plane
 * (Terrain). The buildings never move, so their screen hulls are a static
 * hit test: a pointer on one picks the visible free stone nearest it.
 */
const {
  Cam, clamp, facing, fit, hull, open, prism, proj, ringAt, rings, run, unproj,
  tdone, tset, tval, tween, reducedMotion, disposer, flatDot, mk, place, pointer, put, register, solid,
} = HL;

const N = 9, CELL = 14, FOOT = 12, EXT = N * CELL, PB = 5, ZS = 4, ZD = 0.8, LIFT = 5, STEP = 30, FLOOR = 12;
const START = 8 * N + 0, REST = 0 * N + 8; // cell j·N + i: the left corner, and the far corner opposite it
const SUN = [1, 0], TAN = 0.9; // the sun is low behind the left; shadows run down to the right
const BLD = [[2, 3, 4, 5, 50], [3, 5, 2, 2, 36], [2, 3, 7, 7, 24]]; // i0, i1, j0, j1, height

/** Whether a cell's centre lies in a building's shadow: its footprint swept away from the sun by height / tan(elevation). */
function shaded(i, j) {
  return BLD.some(([a, b, c, d, H]) => {
    let s0 = 0, s1 = H / (CELL * TAN);
    for (const [p, u, m0, m1] of [[i + 0.5, SUN[0], a, b + 1], [j + 0.5, SUN[1], c, d + 1]]) {
      const t0 = (p - m1) / u, t1 = (p - m0) / u;
      s0 = Math.max(s0, Math.min(t0, t1)); s1 = Math.min(s1, Math.max(t0, t1));
    }
    return s0 <= s1;
  });
}

/**
 * A* from START to goal: 4-neighbour moves on free cells, h = Manhattan distance (admissible: no step costs under 1).
 * Ties go to the smaller h, then to the cell nearer the straight line from start to goal, then to the lower index.
 */
function astar(free, shade, goal, w) {
  const gi = goal % N, gj = (goal / N) | 0, si = START % N, sj = (START / N) | 0;
  const h = (k) => Math.abs((k % N) - gi) + Math.abs(((k / N) | 0) - gj);
  const off = (k) => Math.abs(((k % N) - si) * (gj - sj) - (((k / N) | 0) - sj) * (gi - si));
  const g = new Array(N * N).fill(Infinity), par = new Array(N * N).fill(-1), shut = new Array(N * N).fill(false);
  const f = (k) => g[k] + h(k), frontier = [START];
  const before = (a, b) => (Math.abs(f(a) - f(b)) > 1e-9 ? f(a) < f(b) : h(a) !== h(b) ? h(a) < h(b) : off(a) !== off(b) ? off(a) < off(b) : a < b);
  g[START] = 0;
  while (frontier.length) {
    let bi = 0;
    for (let n = 1; n < frontier.length; n++) if (before(frontier[n], frontier[bi])) bi = n;
    const k = frontier.splice(bi, 1)[0];
    if (shut[k]) continue;
    shut[k] = true;
    if (k === goal) { const path = [k]; while (par[path[0]] >= 0) path.unshift(par[path[0]]); return path; }
    const i = k % N, j = (k / N) | 0;
    for (const [di, dj] of [[1, 0], [0, -1], [0, 1], [-1, 0]]) {
      const ni = i + di, nj = j + dj, n = nj * N + ni;
      if (ni < 0 || nj < 0 || ni >= N || nj >= N || !free[n] || shut[n]) continue;
      const c = g[k] + 1 + (shade[n] ? 0 : w);
      if (c < g[n] - 1e-9) { g[n] = c; par[n] = k; frontier.push(n); }
    }
  }
  return [START];
}

/** Whether a screen point lies inside a convex polygon of screen points: never on both sides of its edges. */
function inside(poly, [x, y]) {
  const side = poly.map((a, n) => { const b = poly[(n + 1) % poly.length]; return Math.sign((b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])); });
  return !(side.includes(1) && side.includes(-1));
}

function mount({ stage, svg, read }, value) {
  const bag = disposer();
  let w = value, goal = REST, over = false, route = [];

  // Fitted to the plinth and the tallest roof, so nothing leaves the frame.
  const C = Cam(45, 0.5, 1.55);
  fit(C, [[-6, -6, -PB], [EXT + 6, EXT + 6, -PB], [EXT + 6, -6, -PB], [-6, EXT + 6, -PB], ...BLD.map((b) => [b[0] * CELL, b[2] * CELL, b[4]])], 200, 166);
  const P = proj(C), front = facing(C);

  const free = [], shade = [];
  for (let k = 0; k < N * N; k++) {
    const i = k % N, j = (k / N) | 0;
    free.push(!BLD.some(([a, b, c, d]) => i >= a && i <= b && j >= c && j <= d));
    shade.push(free[k] && shaded(i, j));
  }

  const g = mk("g", {}, svg), [pr, pi] = rings(-6, -6, EXT + 6, EXT + 6, 9, 2.2);
  put(solid(g), prism(P, front, pr, pi, -PB, 0));

  // Paint order: stones by diagonal, left to right; a building after every stone behind it and before every one in front.
  const items = [];
  for (let k = 0; k < N * N; k++) if (free[k]) items.push({ k, at: [(k % N) + ((k / N) | 0), k % N] });
  BLD.forEach((b, n) => items.push({ b: n, at: [Math.max(b[0] - 1 + b[3], b[1] + b[2] - 1), b[1] + 0.5] }));
  items.sort((p, q) => p.at[0] - q.at[0] || p.at[1] - q.at[1]);

  const stones = new Map(), hulls = [];
  for (const it of items) {
    if (it.b !== undefined) {
      const [a, b, c, d, H] = BLD[it.b], el = solid(g), top = it.b ? H : H + 5;
      const [ring, inner] = rings(a * CELL + 1, c * CELL + 1, (b + 1) * CELL - 1, (d + 1) * CELL - 1, 4.5, 1.8);
      put(el, prism(P, front, ring, inner, 0, H));
      // a floor line every storey, round the faces that look at the camera; a plant room on the tallest roof
      for (let z = FLOOR; z < H - 4; z += FLOOR) mk("path", { d: open(ringAt(P, run(ring, front), z)), class: "nf lo" }, el.g);
      const [rr, ri] = rings(a * CELL + 6, c * CELL + 6, a * CELL + 17, c * CELL + 15, 2, 0.8);
      if (!it.b) put(solid(el.g), prism(P, front, rr, ri, H, top));
      hulls.push(hull(ringAt(P, ring, 0).concat(ringAt(P, ring, top))));
      continue;
    }
    const i = it.k % N, j = (it.k / N) | 0, x0 = i * CELL + (CELL - FOOT) / 2, y0 = j * CELL + (CELL - FOOT) / 2;
    const [ring, inner] = rings(x0, y0, x0 + FOOT, y0 + FOOT, 2.4, 0.9);
    const el = solid(g), dot = shade[it.k] ? flatDot(el.g, C, 1.5, "dot m") : null;
    if (dot) el.sil.classList.remove("sil");
    stones.set(it.k, { k: it.k, i, j, ring, inner, el, dot, base: shade[it.k] ? ZD : ZS, z: tween(0), drawn: NaN, on: false, hi: false, at: 0 });
  }

  // Tactile paving: a 3 × 3 of dots on the start stone, and on the stone the route ends on.
  const dots = (cls) => { const m = mk("g", {}, g), d = []; for (let n = 0; n < 9; n++) d.push(flatDot(m, C, 0.6, cls)); return { m, d, on: null, h: NaN }; };
  const startMark = dots("dot m"), goalMark = dots("dot");
  function ride(mark, st) {
    if (mark.on !== st) { mark.on = st; st.el.g.after(mark.m); mark.h = NaN; }
    const h = st.drawn;
    if (h === mark.h) return;
    mark.h = h;
    const cx = (st.i + 0.5) * CELL, cy = (st.j + 0.5) * CELL;
    mark.d.forEach((el, n) => place(el, P(cx + ((n % 3) - 1) * 2.8, cy + (Math.floor(n / 3) - 1) * 2.8, h)));
  }

  // The hit test's static parts: the visible free stones' rest tops, for a pointer that lands on a building.
  const tops = [];
  for (const st of stones.values()) {
    const p = P((st.i + 0.5) * CELL, (st.j + 0.5) * CELL, st.base);
    if (!hulls.some((hl, n) => inside(hl, p) && st.i + st.j + 1 < (BLD[n][0] + BLD[n][1] + BLD[n][2] + BLD[n][3] + 2) / 2)) tops.push([st.k, p]);
  }
  const nearest = (p) => tops.reduce((a, b) => (Math.hypot(b[1][0] - p[0], b[1][1] - p[1]) < Math.hypot(a[1][0] - p[0], a[1][1] - p[1]) ? b : a))[0];
  function pick(p) {
    if (hulls.some((hl) => inside(hl, p))) return nearest(p);
    const [x, y] = unproj(C, p[0], p[1], ZS);
    const k = clamp(Math.floor(y / CELL), 0, N - 1) * N + clamp(Math.floor(x / CELL), 0, N - 1);
    return free[k] ? k : nearest(p);
  }

  const B = register(stage, (_dt, now) => {
    let moving = false;
    for (const st of stones.values()) {
      const h = st.base + tval(st.z, now);
      if (h !== st.drawn) { st.drawn = h; put(st.el, prism(P, front, st.ring, st.inner, 0, h)); if (st.dot) place(st.dot, P((st.i + 0.5) * CELL, (st.j + 0.5) * CELL, h)); }
      if (!tdone(st.z, now)) moving = true;
      if (st.hi !== st.on && now >= st.at) { st.hi = st.on; st.el.sil.classList.toggle("hi", st.hi); } else if (st.hi !== st.on) moving = true;
    }
    ride(startMark, stones.get(START));
    ride(goalMark, stones.get(goal));
    return moving;
  });
  bag.add(B.unregister);

  /** Runs A* to the goal and raises its route, staggered outward from the start; the stones it leaves drop in the same order. */
  function retarget() {
    const path = astar(free, shade, goal, w), now = performance.now(), quick = reducedMotion();
    const was = new Map(route.map((k, n) => [k, n])), is = new Map(path.map((k, n) => [k, n]));
    route = path;
    for (const st of stones.values()) {
      const n = is.has(st.k) ? is.get(st.k) : was.get(st.k);
      if (n === undefined) continue;
      const delay = quick ? 0 : n * STEP, on = is.has(st.k);
      tset(st.z, on ? LIFT : 0, now, delay);
      if (on !== st.on) { st.on = on; st.at = now + delay; }
    }
    read.textContent = over ? `${goal % N}·${(goal / N) | 0} · ${path.length - 1}` : "rest";
    B.wake();
  }

  bag.add(pointer(stage, {
    move: (p) => { const k = pick(p); if (k !== goal || !over) { goal = k; over = true; retarget(); } },
    leave: () => { goal = REST; over = false; retarget(); },
  }));
  bag.add(() => svg.replaceChildren());
  retarget();

  return {
    set: (v) => { w = v; retarget(); },
    destroy: bag.dispose,
  };
}

hairline({
  name: "plaza",
  means: "A* finds the cheapest route across the plaza; with the sun weighed in, it bends through the buildings' shade.",
  rules: [1, 2, 4, 5],
  range: [0, 3, 6],
  tour: [[200, 226], [231, 211], [261, 134], null], // 8·8 straight, 8·6 bends through shade, 4·0 goes round the slab
  mount,
});
