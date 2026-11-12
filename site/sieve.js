/**
 * Sieve: 100 beads, 100 past July afternoons, lie in a raised sieve. The
 * dangerous ones are the medium dots, the safe ones the dim. A bead's size is
 * its forecast reading, cool, warm or hot, and the sieve's front holds three
 * holes of those sizes, the hot one lit at rest. The pointer picks a lane, and
 * with it a hole: the beads of that size hop to it and fall through into the
 * tray below, staggered by their distance to the hole, and settle dangerous
 * first, so the tray holds the posterior. The slider is the prior P(dangerous):
 * how many of the 100 are dangerous.
 *
 * The pattern: discrete items on tweens, a stagger by distance, and a hit test
 * on two fixed planes, the sieve's floor and the tray's, never on a bead.
 */
const {
  Cam, circ, extremes, facing, fit, hull, lerp, open, poly, proj, ringAt, rings, run, seg, unproj,
  tdone, tset, tval, tween, disposer, mk, place, pointer, register,
} = HL;

const SP = 7.2, B0 = 5.5, WT = 2.2, WR = 7, HOP = 8, STEP = 32, CUT = 0.42;
const X1 = 98, Y1 = 78, ZB = 36, ZF = 38, ZT = 42;          // the sieve, floating: bottom, floor, rim
const L0 = 69, L1 = 108.5, LF = 1.2, LT = 4.5, LB = 73.5;     // the tray on the ground, and its first row
const HX = 83, HY = [62, 39, 15], HR = [3.2, 4.4, 5.6], BR = [2.4, 3.2, 4]; // cool, warm, hot
const NAME = ["cool", "warm", "hot"], LD = [0.05, 0.25, 0.7], LS = [0.55, 0.35, 0.1];

/** A run of points ordered left to right on screen. */
const LR = (pts) => (pts[0][0] <= pts[pts.length - 1][0] ? pts : pts.slice().reverse());

/** A fixed, well-mixed number in [0, 1) for bead n and key k: the mix never changes. */
function hash(n, k) {
  let h = Math.imul(n + 1, 0x9e3779b1) ^ Math.imul(k + 7, 0x85ebca77);
  h = Math.imul(h ^ (h >>> 15), 0xc2b2ae3d);
  h = Math.imul(h ^ (h >>> 13), 0x27d4eb2f);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** n beads split by the three likelihoods, rounded so they add up to n; a tie goes to the warmer reading. */
function split(n, lik) {
  const raw = lik.map((l) => Math.round(l * n * 1e6) / 1e6), out = raw.map(Math.floor);
  let left = n - out[0] - out[1] - out[2];
  for (const k of [2, 1, 0].sort((a, b) => raw[b] - out[b] - (raw[a] - out[a]))) if (left > 0) { out[k]++; left--; }
  return out;
}

/** A rounded tray from z0 to zt, its floor at zf: `far` is painted before what it holds, `near` after; each entry is [d, class]. */
function tray(P, front, outer, inner, z0, zf, zt) {
  const iF = LR(ringAt(P, run(inner, front), zt)), oT = LR(ringAt(P, run(outer, front), zt)), oB = LR(ringAt(P, run(outer, front), z0));
  return {
    far: [
      [poly(hull(ringAt(P, outer, z0).concat(ringAt(P, outer, zt)))), "sil"],
      [poly(ringAt(P, inner, zt)), "nf"],
      [open(ringAt(P, run(inner, (q) => !front(q)), zf)), "nf lo"],
    ],
    near: [
      [poly([...iF, oT[oT.length - 1], ...oB.slice().reverse(), oT[0]]), "fo"],
      [open(oT), "nf lo"],
      [open(iF), "nf"],
      [open([oT[0], ...oB, oT[oT.length - 1]]), "nf sil"],
    ],
  };
}

/** Hole k through the sieve's floor: its rim, and the far inside wall seen through it, cut where the rim hides it. */
function hole(P, k) {
  const ring = circ(HR[k], 24).map((q) => ({ ...q, u: q.u + HX, v: q.v + HY[k] }));
  const cy = P(HX, HY[k], ZF)[1], d = (P(0, 0, ZB)[1] - P(0, 0, ZF)[1]) / 2;
  const back = run(ring, (q) => P(q.u, q.v, ZF)[1] - cy < -d);
  return { rim: poly(ringAt(P, ring, ZF)), wall: open(ringAt(P, back, ZB)) };
}

function mount({ stage, svg, read }, value) {
  const bag = disposer();
  let p = value, act = -1;

  // Fitted with a bead at the top of its hop, so nothing leaves the frame in any pose.
  const C = Cam(45, 0.5, 2.25);
  fit(C, [[0, 0, ZT + HOP], [X1, 0, ZT], [0, Y1, ZT], [X1, Y1, ZB], [L1, 0, 0], [L1, Y1, 0], [0, Y1, 0]], 200, 166);
  const P = proj(C), front = facing(C);
  const [so, si] = rings(0, 0, X1, Y1, WR, WT), [to, ti] = rings(L0, 0, L1, Y1, WR, WT);
  const sieve = tray(P, front, so, si, ZB, ZF, ZT), low = tray(P, front, to, ti, 0, LF, LT);

  // Back to front: the drops, the tray and what falls into it, then the sieve, its holes and its beads.
  // The tray never overlaps the sieve on screen, so a falling bead can pass behind the sieve and into the tray.
  const g = mk("g", {}, svg);
  for (const q of extremes(P, so).slice(0, 2)) mk("path", { d: seg(P(q.u, q.v, ZB), P(q.u, q.v, 0)), class: "nf dash" }, g);
  for (const [d, cls] of low.far) mk("path", { d, class: cls }, g);
  const downG = mk("g", {}, g);
  for (const [d, cls] of low.near) mk("path", { d, class: cls }, g);
  for (const [d, cls] of sieve.far) mk("path", { d, class: cls }, g);
  const holes = [0, 1, 2].map((k) => {
    const h = hole(P, k);
    mk("path", { d: h.wall, class: "nf lo" }, g);
    return mk("path", { d: h.rim, class: "nf" }, g);
  });
  const upG = mk("g", {}, g);
  for (const [d, cls] of sieve.near) mk("path", { d, class: cls }, g);

  // The beads, a 10 × 10 on the sieve's floor, appended diagonal by diagonal from the back corner.
  const beads = [];
  for (let s = 0; s <= 18; s++) for (let i = 0; i < 10; i++) {
    const j = s - i;
    if (j < 0 || j > 9) continue;
    const n = i * 10 + j, x = B0 + i * SP, y = B0 + j * SP;
    beads.push({ x, y, u: hash(n, 3960), v: hash(n, 2), dist: HY.map((hy) => Math.hypot(HX - x, hy - y)), el: mk("circle", {}, upG), tw: tween(0), down: false, drawn: NaN });
  }
  const byU = beads.slice().sort((a, b) => a.u - b.u);

  /** The prior sets how many are dangerous; each class is then split by its likelihoods; in the tray, dangerous ones come first. */
  function assign() {
    const nD = Math.round(p * 100);
    [[byU.slice(0, nD), LD, true], [byU.slice(nD), LS, false]].forEach(([set, lik, dang]) => {
      const c = split(set.length, lik);
      set.sort((a, b) => a.v - b.v).forEach((b, k) => { b.dang = dang; b.r = k < c[0] ? 0 : k < c[0] + c[1] ? 1 : 2; });
    });
    for (let r = 0; r < 3; r++) {
      beads.filter((b) => b.r === r).sort((a, b) => b.dang - a.dang || a.dist[r] - b.dist[r]).forEach((b, k) => { b.slot = Math.min(k, 49); });
    }
    for (const b of beads) {
      b.el.setAttribute("r", BR[b.r]);
      b.el.setAttribute("class", b.dang ? "dot m" : "dot off");
      b.drawn = NaN;
    }
  }

  /** Bead b at t: 0 in its place on the sieve, CUT in its hole, 1 in its place in the tray, five deep and filled from the left. */
  function where(b, t) {
    const hy = HY[b.r];
    if (t <= CUT) {
      const u = t / CUT;
      return P(lerp(b.x, HX, u), lerp(b.y, hy, u), lerp(ZF + 1.2, ZF, u) + HOP * 4 * u * (1 - u));
    }
    const v = (t - CUT) / (1 - CUT), lx = LB + (b.slot % 5) * SP, ly = B0 + (9 - Math.floor(b.slot / 5)) * SP;
    return P(lerp(HX, lx, v), lerp(hy, ly, v), lerp(ZF, LF + 1.2, v));
  }

  assign();
  const B = register(stage, (_dt, now) => {
    let moving = false;
    for (const b of beads) {
      const t = tval(b.tw, now);
      if (!tdone(b.tw, now)) moving = true;
      if (t === b.drawn) continue;
      b.drawn = t;
      place(b.el, where(b, t));
      // through the hole, a bead moves in the paint order to the tray's layer, behind the sieve
      if ((t > CUT) !== b.down) { b.down = t > CUT; (b.down ? downG : upG).append(b.el); }
    }
    return moving;
  });
  bag.add(B.unregister);

  /** The lane under the pointer, read on the sieve's floor, then on the tray's: both rest geometry. -1 off the figure. */
  const lane = (y) => (y < 27 ? 2 : y < 50.5 ? 1 : 0);
  function zone([sx, sy]) {
    const a = unproj(C, sx, sy, ZF);
    if (a[0] > -5 && a[0] < X1 + 4 && a[1] > -5 && a[1] < Y1 + 5) return lane(a[1]);
    const b = unproj(C, sx, sy, 0);
    if (b[0] > 50 && b[0] < L1 + 6 && b[1] > -40 && b[1] < Y1 + 6) return lane(b[1]);
    return -1;
  }

  function caption(r) {
    const n = beads.filter((b) => b.r === r), d = n.filter((b) => b.dang).length;
    const post = (LD[r] * p) / (LD[r] * p + LS[r] * (1 - p));
    return `${NAME[r]} ${d}/${n.length} · ${post.toFixed(2)}`;
  }

  /** Sends the chosen reading's beads down and every other bead home, each after its distance to its own hole. */
  function retarget() {
    const now = performance.now();
    for (const b of beads) tset(b.tw, b.r === act ? 1 : 0, now, (b.dist[b.r] / SP) * STEP);
    holes.forEach((h, k) => h.classList.toggle("hi", k === (act < 0 ? 2 : act)));
    read.textContent = act < 0 ? "rest" : caption(act);
    B.wake();
  }
  const choose = (a) => { if (a !== act) { act = a; retarget(); } };

  retarget();
  bag.add(pointer(stage, { move: (pt) => choose(zone(pt)), leave: () => choose(-1) }));
  bag.add(() => svg.replaceChildren());

  return {
    set: (v) => { p = v; assign(); retarget(); },
    destroy: bag.dispose,
  };
}

hairline({
  name: "sieve",
  means: "100 July afternoons: pick the forecast and the ones that match fall through. Their dangerous share is the posterior.",
  rules: [1, 2, 4, 5],
  range: [0.1, 0.3, 0.5],
  tour: [[209, 182], [246, 164], [284, 144], null],
  mount,
});
