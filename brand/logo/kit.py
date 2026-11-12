"""SAYA logo kit, direction B "Into the shade": python3 brand/logo/kit.py

Writes the masters to brand/logo/final/:
  symbol/   saya-symbol.svg (primary cut), saya-symbol-small.svg (16–32 px), saya-symbol-reversed.svg (white on dark)
  lockups/  saya-horizontal.svg, saya-stacked.svg, saya-wordmark.svg, plus *-on-dark.svg
Every shape is a filled path: no strokes, no clip paths, no masks, no live text. The route in the crown is a
real hole (fill-rule evenodd), so one-colour and reversed versions keep it.
Standard library only. Every curve is an exact arc (the S's edges are ellipses offset by half the stroke).
"""
import math, os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "final")
PALETTE = {                      # the landing page's own tokens (site/page.html)
    "shade": "#0A6C82",          # steppe sky, darkened: the logo colour on light backgrounds
    "shade_light": "#4CC4DC",    # the same sky for dark backgrounds
    "ink": "#16191C",
    "ink_light": "#DFE4E9",
    "paper": "#F2F5F5",
    "night": "#0C0F10",
    "sun": "#E8B43A",            # accent for heat, never in the logo
}


def f(n):
    return f"{n:.2f}".rstrip("0").rstrip(".")


def svg(w, h, title, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(w)} {f(h)}" width="{f(w)}" height="{f(h)}" '
            f'role="img" aria-labelledby="t"><title id="t">{title}</title>\n{body}\n</svg>\n')


def write(rel, text):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(text)
    return p


# ---------------- symbol ----------------
def symbol_d(cx=128, cy=100, r=86, w=30, bend_y=162, run=72, trunk_end=226):
    """Crown + trunk outline and the route hole. The route runs up the trunk's axis to bend_y,
    then turns 30° to the right for `run` units and ends in a round cap. Returns (d, bbox)."""
    h = w / 2
    xl, xr = cx - h, cx + h
    y_edge = cy + math.sqrt(r * r - h * h)                # where the trunk's sides meet the crown
    ux, uy = math.sin(math.radians(30)), -math.cos(math.radians(30))
    bend, tip = (cx, bend_y), (cx + run * ux, bend_y + run * uy)
    nx, ny = -uy, ux                                      # normal to the right of travel
    p = lambda q, s: (q[0] + s * nx * h, q[1] + s * ny * h)
    jl, tl, tr = p(bend, -1), p(tip, -1), p(tip, 1)
    t = (xr - (bend[0] + nx * h)) / ux                    # inner corner of the bend, on x = xr
    inner = (xr, bend[1] + ny * h + uy * t)
    assert bend_y < y_edge and math.dist(tip, (cx, cy)) + h < r - 8, "route must stay inside the crown"
    outer = (f"M{f(xr)} {f(y_edge)} V{f(trunk_end)} A{f(h)} {f(h)} 0 0 1 {f(xl)} {f(trunk_end)} V{f(y_edge)} "
             f"A{f(r)} {f(r)} 0 1 1 {f(xr)} {f(y_edge)} Z")
    hole = (f"M{f(xl)} {f(y_edge)} V{f(bend_y)} A{f(h)} {f(h)} 0 0 1 {f(jl[0])} {f(jl[1])} "
            f"L{f(tl[0])} {f(tl[1])} A{f(h)} {f(h)} 0 0 1 {f(tr[0])} {f(tr[1])} "
            f"L{f(inner[0])} {f(inner[1])} V{f(y_edge)} A{f(r)} {f(r)} 0 0 1 {f(xl)} {f(y_edge)} Z")
    bbox = (cx - r, cy - r, cx + r, trunk_end + h)
    return outer + " " + hole, bbox


CUTS = {
    # primary: everything from 48 px up
    "primary": dict(cx=128, cy=100, r=86, w=30, bend_y=162, run=72, trunk_end=226),
    # small, 16–32 px: wider route and trunk so the hole stays open, a shorter turn, a bigger crown
    "small": dict(cx=128, cy=104, r=100, w=44, bend_y=170, run=60, trunk_end=228),
    # reversed (white on dark): white spreads into the dark hole, so the hole is a little wider
    # and the crown a little smaller
    "reversed": dict(cx=128, cy=100, r=85, w=32, bend_y=162, run=72, trunk_end=226),
}


def symbol_path(cut="primary", color=PALETTE["shade"]):
    d, bbox = symbol_d(**CUTS[cut])
    return f'<path fill="{color}" fill-rule="evenodd" d="{d}"/>', bbox


# ---------------- wordmark: monoline, round caps and joins, outlined ----------------
H, W = 120, 22                   # cap height and stroke
h = W / 2
TOP, BOT = h, H - h              # centreline top and bottom: round caps reach 0 and H
X_S, X_A1, X_Y, X_A2 = 38, 138, 232, 330


def P(x, y):
    return f"{f(x)} {f(y)}"


def letter_S(cx, up_ry=23, up_rx=33, lo_rx=36, t_up=-32, t_lo=148):
    """Outlined monoline S: each bowl's edges are ellipses offset by ±h, which meet the next bowl
    tangentially at the spine; the terminals are round caps."""
    lo_ry = (BOT - TOP) / 2 - up_ry
    cu, mid = TOP + up_ry, TOP + 2 * up_ry
    cl = mid + lo_ry
    e = lambda cy, rx, ry, deg: (cx + rx * math.cos(math.radians(deg)), cy + ry * math.sin(math.radians(deg)))
    uo, ui = e(cu, up_rx + h, up_ry + h, t_up), e(cu, up_rx - h, up_ry - h, t_up)
    lo, li = e(cl, lo_rx + h, lo_ry + h, t_lo), e(cl, lo_rx - h, lo_ry - h, t_lo)
    return (f"M{P(*uo)} A{P(up_rx + h, up_ry + h)} 0 1 0 {P(cx, mid + h)} "
            f"A{P(lo_rx - h, lo_ry - h)} 0 1 1 {P(*li)} A{P(h, h)} 0 0 0 {P(*lo)} "
            f"A{P(lo_rx + h, lo_ry + h)} 0 1 0 {P(cx, mid - h)} "
            f"A{P(up_rx - h, up_ry - h)} 0 1 1 {P(*ui)} A{P(h, h)} 0 0 0 {P(*uo)} Z"), cx - up_rx - h


def letter_A(cx, bar_at=0.68):
    """Outlined A: legs on a 1:2 slope, round apex and feet, the bar sits inside the legs; the counter
    is a hole."""
    dx = (BOT - TOP) / 2
    s5 = math.sqrt(5)
    no = (-2 / s5 * h, -1 / s5 * h)                       # outward normal of the left leg, times h
    bar = TOP + (BOT - TOP) * bar_at
    slope = dx / (BOT - TOP)                              # x per y along a leg
    fl, fr, ap = (cx - dx, BOT), (cx + dx, BOT), (cx, TOP)
    apex_in = TOP - no[1] - no[0] / slope                 # the legs' inner edges meet on the axis
    x_in = lambda y: (y - apex_in) * slope                # half-width between the inner edges at y
    yb, yt = bar + h, bar - h
    outer = (f"M{P(fl[0] + no[0], fl[1] + no[1])} L{P(ap[0] + no[0], ap[1] + no[1])} "
             f"A{P(h, h)} 0 0 1 {P(ap[0] - no[0], ap[1] + no[1])} L{P(fr[0] - no[0], fr[1] + no[1])} "
             f"A{P(h, h)} 0 0 1 {P(fr[0] + no[0], fr[1] - no[1])} L{P(cx + x_in(yb), yb)} "
             f"L{P(cx - x_in(yb), yb)} L{P(fl[0] - no[0], fl[1] - no[1])} "
             f"A{P(h, h)} 0 0 1 {P(fl[0] + no[0], fl[1] + no[1])} Z")
    counter = f"M{P(cx, apex_in)} L{P(cx + x_in(yt), yt)} L{P(cx - x_in(yt), yt)} Z"
    return outer + " " + counter


def letter_Y(cx):
    """Outlined Y: 45° arms with round tips, a stem with a round foot; the joins are concave corners."""
    mid = (TOP + BOT) / 2
    a, k = mid - TOP, h / math.sqrt(2)
    tl, tr = (cx - a, TOP), (cx + a, TOP)
    crotch_y = (tl[1] - k) + ((cx - (tl[0] + k)))         # left arm's inner edge reaches the axis
    side_y = (tl[1] + k) + ((cx - h) - (tl[0] - k))       # left arm's outer edge reaches the stem
    return (f"M{P(tl[0] - k, tl[1] + k)} A{P(h, h)} 0 0 1 {P(tl[0] + k, tl[1] - k)} L{P(cx, crotch_y)} "
            f"L{P(tr[0] - k, tr[1] - k)} A{P(h, h)} 0 0 1 {P(tr[0] + k, tr[1] + k)} L{P(cx + h, side_y)} "
            f"L{P(cx + h, BOT)} A{P(h, h)} 0 0 1 {P(cx - h, BOT)} L{P(cx - h, side_y)} Z")


def wordmark_d():
    s, left = letter_S(X_S)
    d = " ".join([s, letter_A(X_A1), letter_Y(X_Y), letter_A(X_A2)])
    return d, left, X_A2 + (BOT - TOP) / 2 + h


WM_D, _WM_LEFT, _WM_RIGHT = wordmark_d()
WM_W = _WM_RIGHT - _WM_LEFT
WM_TOP, WM_BOT = 0, H


def wordmark_path(color):
    return f'<path fill="{color}" fill-rule="evenodd" transform="translate({f(-_WM_LEFT)} 0)" d="{WM_D}"/>'


def place(body, bbox, x, y, height):
    """Scale content with `bbox` so its height is `height` and its top-left lands at (x, y)."""
    bx0, by0, bx1, by1 = bbox
    s = height / (by1 - by0)
    return f'<g transform="translate({f(x - bx0 * s)} {f(y - by0 * s)}) scale({f(s)})">{body}</g>', (bx1 - bx0) * s


# ---------------- lockups ----------------
def horizontal(sym_color, wm_color, cut="primary"):
    pad, sym_h = 12, 232
    sym, bbox = symbol_path(cut, sym_color)
    g_sym, sym_w = place(sym, bbox, pad, pad, sym_h)
    s = sym_h / (bbox[3] - bbox[1])
    crown_cy = pad + (CUTS[cut]["cy"] - bbox[1]) * s
    cap = 0.52 * sym_h                                    # wordmark cap height to symbol height
    gap = 0.24 * sym_h
    wm_y = (crown_cy + 128) / 2 - cap / 2                 # between the crown's centre and the box centre
    g_wm, wm_w = place(wordmark_path(wm_color), (0, WM_TOP, WM_W, WM_BOT), pad + sym_w + gap, wm_y, cap)
    width = pad + sym_w + gap + wm_w + pad
    return width, 256, f'<g id="symbol">{g_sym}</g>\n<g id="wordmark">{g_wm}</g>'


def stacked(sym_color, wm_color, cut="primary"):
    pad, sym_h, gap, cap = 16, 200, 40, 84
    sym, bbox = symbol_path(cut, sym_color)
    s = sym_h / (bbox[3] - bbox[1])
    sym_w = (bbox[2] - bbox[0]) * s
    wm_w = WM_W * cap / H
    width = max(sym_w, wm_w) + 2 * pad
    g_sym, _ = place(sym, bbox, (width - sym_w) / 2, pad, sym_h)
    g_wm, _ = place(wordmark_path(wm_color), (0, WM_TOP, WM_W, WM_BOT), (width - wm_w) / 2, pad + sym_h + gap, cap)
    return width, pad + sym_h + gap + cap + pad, f'<g id="symbol">{g_sym}</g>\n<g id="wordmark">{g_wm}</g>'


def wordmark_only(color):
    pad, cap = 16, 120
    g, w = place(wordmark_path(color), (0, WM_TOP, WM_W, WM_BOT), pad, pad, cap)
    return w + 2 * pad, cap + 2 * pad, f'<g id="wordmark">{g}</g>'


def main():
    P = PALETTE
    for cut, color, name in (("primary", P["shade"], "saya-symbol"), ("small", P["shade"], "saya-symbol-small"),
                             ("reversed", "#FFFFFF", "saya-symbol-reversed")):
        body, _ = symbol_path(cut, color)
        write(f"symbol/{name}.svg", svg(256, 256, "SAYA symbol", body))
    for name, fn, args in (
        ("saya-horizontal", horizontal, (P["shade"], P["ink"])),
        ("saya-horizontal-on-dark", horizontal, (P["shade_light"], P["ink_light"], "reversed")),
        ("saya-stacked", stacked, (P["shade"], P["ink"])),
        ("saya-stacked-on-dark", stacked, (P["shade_light"], P["ink_light"], "reversed")),
    ):
        w, h, body = fn(*args)
        write(f"lockups/{name}.svg", svg(w, h, "SAYA logo", body))
    for name, color in (("saya-wordmark", P["ink"]), ("saya-wordmark-on-dark", P["ink_light"])):
        w, h, body = wordmark_only(color)
        write(f"lockups/{name}.svg", svg(w, h, "SAYA wordmark", body))
    print("wrote", ROOT)


if __name__ == "__main__":
    main()
