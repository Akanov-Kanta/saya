/**
 * Shade: five buildings around a crossroads. The pointer is the sun: its
 * direction from the block's centre, on the ground, is the azimuth of the real
 * sun over Astana on 15 July, which gives the hour and the sun's height. Each
 * building throws its shadow away from the pointer, and the stretches of the
 * streets' centre lines in shade take the bright stroke. Rest is 16:00, SAYA's
 * default hour. The slider is the buildings' height, as a multiplier.
 */
const {
  Cam, clamp, facing, fit, hull, lerp, open, poly, prism, proj, put, rad, rings, ringAt, rrect,
  spring, stepS, unproj, disposer, mk, place, pointer, register, solid,
} = HL;

// The sun over Astana (51.10 N, 71.41 E) on 15 July 2026, every half hour from 06:00 to
// 19:00: [hour, azimuth clockwise from north, altitude], both in degrees, from SAYA's sun.py.
const SUN = [
  [6.0, 72.3, 13.7], [6.5, 77.8, 18.3], [7.0, 83.3, 22.9], [7.5, 89.0, 27.6], [8.0, 94.9, 32.3], [8.5, 101.2, 37.0], [9.0, 108.1, 41.5],
  [9.5, 115.6, 45.9], [10.0, 124.0, 50.0], [10.5, 133.6, 53.6], [11.0, 144.6, 56.7], [11.5, 156.9, 59.0], [12.0, 170.5, 60.3], [12.5, 184.7, 60.5],
  [13.0, 198.5, 59.6], [13.5, 211.4, 57.6], [14.0, 222.8, 54.7], [14.5, 232.8, 51.2], [15.0, 241.6, 47.3], [15.5, 249.4, 43.0], [16.0, 256.5, 38.5],
  [16.5, 262.9, 33.9], [17.0, 269.0, 29.2], [17.5, 274.7, 24.5], [18.0, 280.3, 19.8], [18.5, 285.8, 15.2], [19.0, 291.3, 10.7],
];
const H0 = SUN[0][0], H1 = SUN[SUN.length - 1][0], REST = 16;

/** [azimuth, altitude] at hour h, between the table's rows. */
function sunAt(h) {
  const t = (clamp(h, H0, H1) - H0) / 0.5, i = Math.min(SUN.length - 2, Math.floor(t)), f = t - i;
  return [lerp(SUN[i][1], SUN[i + 1][1], f), lerp(SUN[i][2], SUN[i + 1][2], f)];
}
/** The hour at which the sun stands at azimuth az; the night sector, north, holds the nearer end of the day. */
function hourOf(az) {
  if (az <= SUN[0][1]) return H0;
  if (az >= SUN[SUN.length - 1][1]) return H1;
  let i = 0;
  while (az > SUN[i + 1][1]) i++;
  return SUN[i][0] + (0.5 * (az - SUN[i][1])) / (SUN[i + 1][1] - SUN[i][1]);
}
const pad = (n) => String(n).padStart(2, "0"), clock = (h) => { const m = Math.round(h * 6) * 10; return pad(Math.floor(m / 60)) + ":" + pad(m % 60); };

// The block is 120 × 120 with a crossroads through its middle; the streets are the gaps between
// four plots. North is toward the viewer (straight down on screen) and east to the left, so the sun
// stands behind the block for most of the day and its shadows fall where the camera can see them.
const NO = [Math.SQRT1_2, Math.SQRT1_2], EA = [-Math.SQRT1_2, Math.SQRT1_2];
const EXT = 120, MID = 60, CAP = 70, HATCH = 3.5, TOWER = 58;
const PLOTS = [[2, 2, 52, 52], [68, 2, 118, 52], [2, 68, 52, 118], [68, 68, 118, 118]];
const BUILDINGS = [
  [8, 10, 46, 40, 24],      // north-west: a mid-rise slab
  [78, 10, 102, 34, TOWER], // north-east: the tower
  [8, 76, 40, 110, 14],     // south-west: a low block
  [74, 74, 112, 94, 30],    // south-east: a long block
  [82, 102, 106, 114, 8],   // south-east: a pavilion behind it, nearest the viewer
];

/** Shade as hatching: segments of the lines x + y = k·HATCH inside a convex polygon. The lines are
 * level on screen and shared by every shadow, so two shadows that overlap hatch as one. */
function hatch(pts) {
  const u = pts.map(([x, y]) => x + y), out = [];
  for (let c = Math.ceil(Math.min(...u) / HATCH) * HATCH; c < Math.max(...u); c += HATCH) {
    const hit = [];
    pts.forEach((a, i) => {
      const j = (i + 1) % pts.length, b = pts[j], ua = u[i] - c, ub = u[j] - c;
      if (ua < 0 !== ub < 0) { const t = ua / (ua - ub); hit.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]); }
    });
    if (hit.length >= 2) out.push(hit);
  }
  return out;
}

/** Clips a polygon to a convex window, both as [x, y] lists. */
function clipTo(pts, win) {
  let area = 0;
  for (let i = 0; i < win.length; i++) { const a = win[i], b = win[(i + 1) % win.length]; area += a[0] * b[1] - b[0] * a[1]; }
  const s = Math.sign(area);
  for (let e = 0; e < win.length && pts.length >= 3; e++) {
    const a = win[e], b = win[(e + 1) % win.length];
    const side = (p) => s * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]));
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i], q = pts[(i + 1) % pts.length], sp = side(p), sq = side(q);
      if (sp >= 0) out.push(p);
      if ((sp >= 0) !== (sq >= 0)) { const t = sp / (sp - sq); out.push([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]); }
    }
    pts = out;
  }
  return pts.length >= 3 ? pts : [];
}
/** Whether [x, y] lies inside a convex polygon. */
function inside(pts, x, y) {
  const signs = pts.map((a, i) => { const b = pts[(i + 1) % pts.length]; return Math.sign((b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])); });
  return !(signs.includes(1) && signs.includes(-1));
}

function mount({ stage, svg, read }, value) {
  const bag = disposer();
  let hs = value;

  // Fitted to the plinth and the tower at the slider's tallest, so nothing leaves the frame.
  const C = Cam(45, 0.5, 1.6);
  fit(C, [[-4, -4, -5], [EXT + 4, EXT + 4, -5], [EXT + 4, -4, -5], [-4, EXT + 4, -5], [78, 10, TOWER * 1.3], [102, 10, TOWER * 1.3]], 200, 162);
  const P = proj(C), front = facing(C);
  const flat = (pts, z = 0) => pts.map(([x, y]) => P(x, y, z));

  const g = mk("g", {}, svg);
  const [pr, pi] = rings(-4, -4, EXT + 4, EXT + 4, 9, 2.2);
  put(solid(g), prism(P, front, pr, pi, -5, 0));
  const win = pi.map((q) => [q.u, q.v]);

  // the four plots, flat on the ground: their kerbs are the streets' edges
  for (const [x0, y0, x1, y1] of PLOTS) mk("path", { d: poly(ringAt(P, rrect(x0, y0, x1, y1, 5, 4), 0)), class: "nf lo" }, g);

  // shadows lie on the ground, under everything that stands
  const shadows = mk("path", { class: "nf" }, g);
  const sunny = mk("path", { class: "nf lo" }, g), shady = mk("path", { class: "nf hi" }, g);

  // the buildings, back to front by the middle of their footprints
  const mid = (q) => q[0] + q[1] + q[2] + q[3];
  const order = BUILDINGS.map((b, i) => i).sort((a, b) => mid(BUILDINGS[a]) - mid(BUILDINGS[b]));
  const houses = BUILDINGS.map(([x0, y0, x1, y1, h]) => {
    const ring = rrect(x0, y0, x1, y1, 4, 4);
    return { x0, y0, x1, y1, h, ring, foot: ring.map((q) => [q.u, q.v]), rings: rings(x0, y0, x1, y1, 4, 1.4), g: null };
  });
  for (const i of order) houses[i].g = mk("g", {}, g);

  /** A building at the current height: a solid, and its windows as dim dots on the two faces the camera sees. */
  function build(b) {
    b.g.replaceChildren();
    const top = b.h * hs, el = solid(b.g);
    put(el, prism(P, front, b.rings[0], b.rings[1], 0, top));
    for (let z = 5; z <= top - 3; z += 6) {
      for (let y = b.y0 + 5; y <= b.y1 - 4; y += 6) place(mk("circle", { r: 0.75, class: "dot off" }, b.g), P(b.x1, y, z));
      for (let x = b.x0 + 5; x <= b.x1 - 4; x += 6) place(mk("circle", { r: 0.75, class: "dot off" }, b.g), P(x, b.y1, z));
    }
  }
  houses.forEach(build);

  // the two streets' centre lines, sampled every unit
  const LINES = [Array.from({ length: EXT + 1 }, (_, k) => [MID, k]), Array.from({ length: EXT + 1 }, (_, k) => [k, MID])];

  /** The shadows at hour h, in world [x, y], before clipping to the plinth. */
  function cast(h) {
    const [az, alt] = sunAt(h);
    return houses.map((b) => {
      const L = Math.min(CAP, (b.h * hs) / Math.tan(rad(alt)));
      const c = Math.cos(rad(az)), n = Math.sin(rad(az)), dx = -(NO[0] * c + EA[0] * n) * L, dy = -(NO[1] * c + EA[1] * n) * L;
      return hull(b.foot.concat(b.foot.map(([x, y]) => [x + dx, y + dy])));
    });
  }

  let drawnH = NaN, drawnS = NaN;
  function draw(h) {
    if (h === drawnH && hs === drawnS) return;
    drawnH = h; drawnS = hs;
    const sh = cast(h);
    shadows.setAttribute("d", sh.map((s) => clipTo(s, win)).filter((c) => c.length).flatMap(hatch).map((s) => open(flat(s))).join(""));
    let lit = "", dim = "";
    for (const line of LINES) {
      let run = [], was = null;
      const flush = () => { if (run.length > 1) { if (was) lit += open(flat(run)); else dim += open(flat(run)); } };
      for (const p of line) {
        const s = sh.some((poly_) => inside(poly_, p[0], p[1]));
        if (s !== was && was !== null) { run.push(p); flush(); run = [p]; } else run.push(p);
        was = s;
      }
      flush();
    }
    shady.setAttribute("d", lit);
    sunny.setAttribute("d", dim);
  }

  const hour = spring(REST, { eps: 0.002 });
  draw(REST);
  const B = register(stage, (dt) => { const m = stepS(hour, dt); draw(hour.x); return m; });
  bag.add(B.unregister);

  bag.add(pointer(stage, {
    move: (p) => {
      const [x, y] = unproj(C, p[0], p[1], 0), dx = x - MID, dy = y - MID;
      if (Math.hypot(dx, dy) < 8) return; // over the crossroads the direction is unsure: keep the last one
      const az = ((Math.atan2(dx * EA[0] + dy * EA[1], dx * NO[0] + dy * NO[1]) * 180) / Math.PI + 360) % 360;
      hour.t = hourOf(az);
      read.textContent = clock(hour.t);
      B.wake();
    },
    leave: () => { hour.t = REST; read.textContent = "rest"; B.wake(); },
  }));
  bag.add(() => svg.replaceChildren());

  return {
    set: (v) => { hs = v; houses.forEach(build); drawnS = NaN; draw(hour.x); },
    destroy: bag.dispose,
  };
}

hairline({
  name: "shade",
  means: "Your pointer is the sun over Astana: the buildings' shadows swing away from it, and the shaded street goes bright.",
  rules: [1, 3, 5, 6],
  range: [0.7, 1, 1.3],
  tour: [[124, 171], [225, 146], [279, 191], null],
  mount,
});
