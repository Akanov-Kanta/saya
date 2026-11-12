/**
 * Fork: a pavement on a city block forks round a kerbed island into a short
 * straight lane in the sun and a longer one that bows back under an arcade,
 * and the two meet again. At the fork a switch blade, like railway points,
 * pivots on its boss to one lane. The pointer's x across the stage is p, the
 * chance of dangerous heat: the sun lane's paving stones heave with it, each
 * on its own spring. One Bellman update, Q of each route from its walk and
 * sun minutes, picks the route; the blade swings to it on the 700ms tween
 * and the chosen lane's kerb takes the bright stroke. At rest it is a hot
 * day, the blade is set to the shade and is the bright mark. The slider is
 * the heat-stress penalty, which moves the break-even p.
 */
const {
  Cam, circ, clamp, facing, fillet, fit, open, poly, prism, proj, rad, rings,
  spring, stepS, tdone, tset, tval, tween, disposer, mk, pointer, put, register, solid,
} = HL;

// SAYA's sample run: a wheelchair user (v 1.5), AITU to Mega Silk Way. Walk and sun minutes per route.
const SHORT = { walk: 28.9, sun: 28.9 }, SHADE = { walk: 30.2, sun: 24.5 };
const V = 1.5, GAMMA = 0.9, HD = Math.min(0.99, 0.03 * V), HS = Math.min(0.99, 0.002 * V);
/** P(heat stress) on a route with `sun` minutes in the sun, when dangerous heat has probability p. */
const stress = (p, sun) => p * (1 - (1 - HD) ** sun) + (1 - p) * (1 - (1 - HS) ** sun);
/** One Bellman update from Comfortable: the walk now, and the discounted penalty if heat stress follows. */
const Q = (r, p, pen) => -r.walk + GAMMA * (stress(p, r.sun) * -pen);
const shaded = (p, pen) => Q(SHADE, p, pen) > Q(SHORT, p, pen);

// The block, along x: the pavement forks at XF, bows D back, and rejoins at L - XF.
const L = 150, HW = 6, XF = 20, D = 30, AL = rad(58), Y0 = -46, Y1 = 14, PB = 5, KH = 2.5;
// The arcade over the bow: NB arches on piers PW wide along its face at FY, one more at its end, a back wall at YB, a roof.
const AX0 = 50, AX1 = 100, AH = 20, NB = 4, PW = 3, FY = HW - D + 2.5, YB = -D - HW - 5;
// The sun lane's stones, how far they heave, the heat at rest; the blade's pivot and length.
const NS = 8, HMAX = 7.5, P_REST = 0.8, BX = XF - 1, BL = 15;

const sn = Math.sin(AL), cot = Math.cos(AL) / sn, mir = (x) => L - x;
/** x where the fork's slant through a reaches the line y, on the ground. */
const xAt = (a, y) => a[0] - (y - a[1]) * cot;
const iA = [XF + HW * sn, HW * Math.cos(AL)], oA = [XF - HW * sn, -HW * Math.cos(AL)];
const IY = FY + 0.5, N1 = xAt(iA, -HW), I1 = xAt(iA, IY), Q1 = xAt(oA, -HW), O1 = xAt(oA, -HW - D);
const SX0 = N1 + 5, SG = 1.2, SW = (mir(N1) - 3 - SX0 - (NS - 1) * SG) / NS;
/** Stone i's height at heat p: one swell along the lane, highest past its middle. */
const heave = (p, i) => 1.2 + p * HMAX * Math.exp(-(((i - 4.5) / 2.4) ** 2));

/** The blade's footprint turned by a about the pivot: the hull of a heel round r1 and a tip round r2, as a ring. */
function blade(a, r1, r2) {
  const b = Math.acos((r1 - r2) / BL), c = Math.cos(a), s = Math.sin(a), ring = [];
  const add = (cx, r, t) => {
    const nu = Math.cos(t), nv = Math.sin(t), u = cx + r * nu, v = r * nv;
    ring.push({ u: BX + c * u - s * v, v: s * u + c * v, nu: c * nu - s * nv, nv: s * nu + c * nv });
  };
  for (let k = 0; k <= 6; k++) add(BL, r2, -b + (2 * b * k) / 6);
  for (let k = 0; k <= 12; k++) add(0, r1, b + ((2 * Math.PI - 2 * b) * k) / 12);
  return ring;
}

/** A convex outline as [ring, inner]: each point with its outward normal, and the ring inset by b for the crease. */
function ringOf(pts, b) {
  const n = pts.length, cx = pts.reduce((s, q) => s + q[0], 0) / n, cy = pts.reduce((s, q) => s + q[1], 0) / n;
  const ring = pts.map((q, i) => {
    const a = pts[(i + n - 1) % n], c = pts[(i + 1) % n], len = Math.hypot(c[0] - a[0], c[1] - a[1]) || 1;
    const k = (c[1] - a[1]) * (q[0] - cx) - (c[0] - a[0]) * (q[1] - cy) < 0 ? -1 : 1;
    return { u: q[0], v: q[1], nu: (k * (c[1] - a[1])) / len, nv: (-k * (c[0] - a[0])) / len };
  });
  return [ring, ring.map((q) => ({ ...q, u: q.u - b * q.nu, v: q.v - b * q.nv }))];
}

/** A wall in its own plane, as (s, z): from a0 to a1, AH tall, with a round arch cut up from the ground over each [s0, s1]. */
function wall(a0, a1, gaps) {
  const pts = [[a0, 0], [a0, AH], [a1, AH], [a1, 0]], r = [0.4, 1.6, 0.01, 0.01];
  for (const [s0, s1] of gaps.slice().reverse()) {
    pts.push([s1, 0], [s1, AH - 4.5], [s0, AH - 4.5], [s0, 0]);
    r.push(0.4, (s1 - s0) / 2, (s1 - s0) / 2, 0.4);
  }
  return fillet(pts, r, 4);
}

/** The arcade's face and its end wall as one outline, folded round the corner they share, so that corner is never drawn. */
function arcade(P, dx, dy) {
  const w = (AX1 - AX0 - (NB + 1) * PW) / NB, bays = [];
  for (let k = 0; k < NB; k++) bays.push([AX0 + PW + k * (w + PW), AX0 + (k + 1) * (w + PW)]);
  const face = wall(AX0, AX1, bays), end = wall(YB, FY, [[-D - HW, HW - D]]);
  return poly([
    ...face.slice(15).concat(face.slice(0, 15)).map(([s, z]) => P(Math.min(s, AX1 + dx), FY + dy, z)),
    ...end.slice(0, 15).reverse().concat(end.slice(15).reverse()).map(([s, z]) => P(AX1 + dx, Math.min(s, FY + dy), z)),
  ]);
}

function mount({ stage, svg, read }, value) {
  const bag = disposer();
  let pen = value, p = null;

  const C = Cam(45, 0.5, 2.1);
  fit(C, [[0, Y0, -PB], [L, Y1, -PB], [L, Y0, -PB], [0, Y1, -PB], [AX0, YB - 1.5, AH + 2.5]], 200, 166);
  const P = proj(C), front = facing(C), G = (pts) => pts.map(([x, y]) => P(x, y, 0));

  const g = mk("g", {}, svg);
  const [pr, pi] = rings(0, Y0, L, Y1, 10, 2.2);
  put(solid(g), prism(P, front, pr, pi, -PB, 0));

  // The pavement's kerbs, drawn on the block: the trunk's, then each lane's outer kerb, which is the one that lights.
  const line = (pts) => mk("path", { d: open(G(pts)), class: "nf" }, g);
  const edge = fillet([[0, -HW], [Q1, -HW], [O1, -HW - D], [mir(O1), -HW - D], [mir(Q1), -HW], [L, -HW], [L, HW], [0, HW]],
    [0.01, 5, 21, 21, 5, 0.01, 0.01, 0.01], 4);
  line(edge.slice(0, 6)); line(edge.slice(24, 26)); line([[0, HW], [N1, HW]]); line([[mir(N1), HW], [L, HW]]);
  const lanes = { shade: line(edge.slice(5, 25)), sun: line([[N1, HW], [mir(N1), HW]]) };

  // The arcade, back to front: its back wall, the far side of its face and end, the near side, then the roof.
  const [wr, wi] = rings(AX0, YB, AX1, YB + 2, 1, 0.5);
  put(solid(g), prism(P, front, wr, wi, 0, AH));
  mk("path", { d: arcade(P, -2, -2), class: "lo" }, g);
  mk("path", { d: arcade(P, 0, 0), class: "sil" }, g);
  const [rr, ri] = rings(AX0 - 2, YB - 1.5, AX1 + 2, FY + 1.5, 2, 1);
  put(solid(g), prism(P, front, rr, ri, AH, AH + 2.5));

  // The island between the lanes, nearer than the arcade's foot: a kerbed solid with its nose at the fork.
  const [ir, ii] = ringOf(fillet([[N1, -HW], [I1, IY], [mir(I1), IY], [mir(N1), -HW]], [2.5, 9, 9, 2.5], 4), 0.9);
  put(solid(g), prism(P, front, ir, ii, 0, KH));

  // The switch: a tapered blade on a round boss at the fork.
  const bl = solid(g), boss = solid(g);
  const at = (ring) => ring.map((q) => ({ ...q, u: q.u + BX }));
  put(boss, prism(P, front, at(circ(3, 20)), at(circ(2.2, 20)), 0, 4.6));

  const stones = [];
  for (let i = 0; i < NS; i++) {
    const x0 = SX0 + i * (SW + SG), [ring, inner] = rings(x0, -HW + 1, x0 + SW, HW - 1, 1.8, 0.8);
    stones.push({ ring, inner, el: solid(g), sp: spring(heave(P_REST, i), { eps: 0.04 }), drawn: NaN });
  }

  const ang = tween(-AL);
  let drawnA = NaN;
  const B = register(stage, (dt, now) => {
    let moving = false;
    for (const s of stones) {
      if (stepS(s.sp, dt)) moving = true;
      const h = Math.max(0.8, s.sp.x);
      if (h !== s.drawn) { s.drawn = h; put(s.el, prism(P, front, s.ring, s.inner, 0, h)); }
    }
    const a = tval(ang, now);
    if (a !== drawnA) { drawnA = a; put(bl, prism(P, front, blade(a, 2.3, 0.7), blade(a, 1.5, 0.3), 0, 3)); }
    return moving || !tdone(ang, now);
  });
  bag.add(B.unregister);

  /** p is the pointer's x and nothing else, so the moving blade can never feed back into the choice. */
  function update() {
    const shade = p === null || shaded(p, pen);
    tset(ang, shade ? -AL : 0, performance.now(), 0);
    stones.forEach((s, i) => { s.sp.t = heave(p === null ? P_REST : p, i); });
    bl.sil.classList.toggle("hi", p === null);
    lanes.shade.classList.toggle("hi", p !== null && shade);
    lanes.sun.classList.toggle("hi", p !== null && !shade);
    read.textContent = p === null ? "rest" : `p ${p.toFixed(2)} · ${shade ? "shaded" : "shortest"}`;
    B.wake();
  }

  bag.add(pointer(stage, {
    move: (pt) => { p = clamp((pt[0] - 40) / 320, 0, 1); update(); },
    leave: () => { p = null; update(); },
  }));
  bag.add(() => svg.replaceChildren());
  update();

  return {
    set: (v) => { pen = v; update(); },
    destroy: bag.dispose,
  };
}

hairline({
  name: "fork",
  means: "One Bellman update at the fork: as dangerous heat gets likelier, the switch sends the wheelchair user into the shade.",
  rules: [1, 4, 5, 8],
  range: [45, 60, 90],
  tour: [[72, 196], [296, 150], [98, 176], null],
  mount,
});
