"""SAYA logo concepts as SVG: .venv/bin/python brand/logo/gen.py <version>  (needs shapely, in the project venv)

Three concepts, each a symbol on a 256 canvas and a horizontal lockup (height 256):
  a-fork       letterform: the Y of SAYA is a route fork, the road not taken is cut off
  b-shade      pictorial: a route walks into the shade of a crown and turns light there
  c-shadeline  wordmark: the letters are thin in the sun above a line and bold in the shade below it
Exploration files: strokes with round caps and clip paths. Outline and flatten before a final master.
"""
import math, os, sys

V = sys.argv[1] if len(sys.argv) > 1 else "v5"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concepts", V)
os.makedirs(OUT, exist_ok=True)
INK, PAPER = "#111111", "#ffffff"


def f(n):
    return f"{n:.2f}".rstrip("0").rstrip(".")


def svg(w, h, title, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(w)} {f(h)}" width="{f(w)}" height="{f(h)}" '
            f'role="img" aria-labelledby="t"><title id="t">{title}</title>\n{body}\n</svg>\n')


def stroke(d, w, color=INK):
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{f(w)}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def poly(pts):
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in pts)


def ell(cx, cy, rx, ry, deg):
    t = math.radians(deg)
    return cx + rx * math.cos(t), cy + ry * math.sin(t)


def s_centreline(cx, top_c, bot_c, up_ry, up_rx, lo_rx, t_up=-32, t_lo=148):
    """Monoline S: the upper bowl runs over the top and down the left, the lower bowl round the right."""
    lo_ry = (bot_c - top_c) / 2 - up_ry
    mid = top_c + 2 * up_ry
    ux, uy = ell(cx, top_c + up_ry, up_rx, up_ry, t_up)
    lx, ly = ell(cx, mid + lo_ry, lo_rx, lo_ry, t_lo)
    return (f"M{f(ux)} {f(uy)} A{f(up_rx)} {f(up_ry)} 0 1 0 {f(cx)} {f(mid)} "
            f"A{f(lo_rx)} {f(lo_ry)} 0 1 1 {f(lx)} {f(ly)}")


# ---------- wordmark: monoline on a 120 cap height, round caps and joins (no sharp corners) ----------
H, W = 120, 22
TOP, BOT = W / 2, H - W / 2           # centreline top and bottom
MID = (TOP + BOT) / 2
X_S, X_A1, X_Y, X_A2 = 38, 134, 228, 326
WM_WIDTH = X_A2 + (BOT - TOP) / 2 + W / 2


def wm_paths(y_right="solid"):
    """Centrelines of S, A, Y, A. Returns a list of path data strings."""
    d = [s_centreline(X_S, TOP, BOT, up_ry=23, up_rx=33, lo_rx=36)]
    dx = (BOT - TOP) / 2                                  # A legs on a 1:2 slope
    bar = TOP + (BOT - TOP) * 0.68
    bx = dx * (bar - TOP) / (BOT - TOP)
    for cx in (X_A1, X_A2):
        d += [poly([(cx - dx, BOT), (cx, TOP), (cx + dx, BOT)]), poly([(cx - bx, bar), (cx + bx, bar)])]
    a = MID - TOP                                         # Y arms at 45°
    d.append(poly([(X_Y - a, TOP), (X_Y, MID), (X_Y, BOT)]))
    if y_right == "solid":
        d.append(poly([(X_Y, MID), (X_Y + a, TOP)]))
    else:                                                 # "break": the arm is cut once
        L = a * math.sqrt(2)
        t0 = (W / 2 + W * 0.7 + W / 2) / L
        d.append(poly([(X_Y + a * t0, MID - a * t0), (X_Y + a, TOP)]))
    return d


def wordmark(y_right="solid"):
    return "\n".join(stroke(d, W) for d in wm_paths(y_right))


# ---------- outlines (shapely, from the project venv): strokes → filled paths, no clip paths ----------
def s_points(cx, top_c, bot_c, up_ry, up_rx, lo_rx, t_up=-32, t_lo=148, n=90):
    lo_ry = (bot_c - top_c) / 2 - up_ry
    cy_up, cy_lo = top_c + up_ry, top_c + 2 * up_ry + lo_ry
    up = [ell(cx, cy_up, up_rx, up_ry, t_up + (-270 - t_up) * i / n) for i in range(n + 1)]
    lo = [ell(cx, cy_lo, lo_rx, lo_ry, -90 + (t_lo + 90) * i / n) for i in range(1, n + 1)]
    return up + lo


def wm_lines(y_right="solid"):
    """Centrelines of S, A, Y, A as point lists (same geometry as wm_paths)."""
    out = [s_points(X_S, TOP, BOT, up_ry=23, up_rx=33, lo_rx=36)]
    dx = (BOT - TOP) / 2
    bar = TOP + (BOT - TOP) * 0.68
    bx = dx * (bar - TOP) / (BOT - TOP)
    for cx in (X_A1, X_A2):
        out += [[(cx - dx, BOT), (cx, TOP), (cx + dx, BOT)], [(cx - bx, bar), (cx + bx, bar)]]
    a = MID - TOP
    out += [[(X_Y - a, TOP), (X_Y, MID), (X_Y, BOT)], [(X_Y, MID), (X_Y + a, TOP)]]
    return out


def geom_path(g):
    polys = getattr(g, "geoms", [g])
    d = []
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            c = list(ring.coords)[:-1]
            d.append("M" + " L".join(f"{f(x)} {f(y)}" for x, y in c) + "Z")
    return f'<path fill="{INK}" fill-rule="evenodd" d="{" ".join(d)}"/>'


def shade_line_geom(lines, thin, bold, line_y):
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    buf = lambda pts, w: LineString(pts).buffer(w / 2, quad_segs=12, cap_style="round", join_style="round")
    thin_u = unary_union([buf(p, thin) for p in lines])
    bold_u = unary_union([buf(p, bold) for p in lines]).intersection(box(-1e3, line_y, 1e4, 1e4))
    return unary_union([thin_u, bold_u]).simplify(0.15)


def shadeline_wordmark(thin=10, bold=24, uid=None):
    """Thin everywhere, bold below the shade line at mid height. One filled path."""
    return geom_path(shade_line_geom(wm_lines(), thin, bold, MID))


def lockup(symbol_body, wm_body, name):
    sym_h, cap, gap = 176, 92, 44
    sc, ws = sym_h / 256, cap / H
    x_wm = sym_h + gap
    total = x_wm + WM_WIDTH * ws + 8
    body = (f'<g id="symbol" transform="translate(0 {f((256 - sym_h) / 2)}) scale({f(sc)})">{symbol_body}</g>\n'
            f'<g id="wordmark" transform="translate({f(x_wm)} {f((256 - cap) / 2)}) scale({f(ws)})">{wm_body}</g>')
    return svg(round(total), 256, f"SAYA logo, {name}, horizontal", body)


def wordmark_only(wm_body, name):
    pad = 16
    w = WM_WIDTH * (2 + 0) + 0
    sc = (256 - 2 * 68) / H                               # cap height 120 inside a 256-high lockup
    width = WM_WIDTH * sc + 2 * pad
    return svg(round(width), 256, f"SAYA logo, {name}, wordmark",
               f'<g id="wordmark" transform="translate({f(pad)} 68) scale({f(sc)})">{wm_body}</g>')


# ---------- A: Fork ----------
def fork_symbol(w=36, gap_k=0.75):
    cx, junction, bottom, a = 128, 114, 222, 84           # 45° arms; sits 2 units above centre (optical)
    L = a * math.sqrt(2)
    u = lambda d: (cx + a * d / L, junction - a * d / L)
    start = w / 2 + w * gap_k + w / 2                     # the cut arm starts one gap after the junction
    return (stroke(poly([(cx - a, junction - a), (cx, junction), (cx, bottom)]), w) +
            stroke(poly([u(start), u(L)]), w))


# ---------- B: Into the shade ----------
def shade_symbol(w=30, uid=None):
    """Crown and trunk as one filled path; the route inside the crown is a real hole (evenodd).
    Route centreline: up x=128 to y=162, then a 30° turn to the right, ending at (164, 100)."""
    cx, cy, r, h = 128, 100, 86, w / 2
    xl, xr = cx - h, cx + h
    y_edge = cy + math.sqrt(r * r - h * h)                # where the trunk's sides meet the crown
    bend, tip = (128.0, 162.0), (164.0, 100.0)
    ux, uy = tip[0] - bend[0], tip[1] - bend[1]
    L = math.hypot(ux, uy)
    ux, uy = ux / L, uy / L
    nx, ny = -uy, ux                                      # normal to the right of travel
    p = lambda q, s: (q[0] + s * nx * h, q[1] + s * ny * h)
    jl, tl, tr = p(bend, -1), p(tip, -1), p(tip, 1)
    t = (xr - (bend[0] + nx * h)) / ux                    # inner corner of the bend on x = xr
    inner = (xr, bend[1] + ny * h + uy * t)
    outer = (f"M{f(xr)} {f(y_edge)} V226 A{f(h)} {f(h)} 0 0 1 {f(xl)} 226 V{f(y_edge)} "
             f"A{r} {r} 0 1 1 {f(xr)} {f(y_edge)} Z")
    hole = (f"M{f(xl)} {f(y_edge)} V{f(bend[1])} A{f(h)} {f(h)} 0 0 1 {f(jl[0])} {f(jl[1])} "
            f"L{f(tl[0])} {f(tl[1])} A{f(h)} {f(h)} 0 0 1 {f(tr[0])} {f(tr[1])} "
            f"L{f(inner[0])} {f(inner[1])} V{f(y_edge)} A{r} {r} 0 0 1 {f(xl)} {f(y_edge)} Z")
    return f'<path fill="{INK}" fill-rule="evenodd" d="{outer} {hole}"/>'


# ---------- C: Shade line ----------
def shadeline_symbol(thin=17, bold=42, uid=None):
    top_c, bot_c = 12 + bold / 2, 232 - bold / 2
    pts = s_points(125, top_c, bot_c, up_ry=(bot_c - top_c) / 4 - 2, up_rx=70, lo_rx=76)
    return geom_path(shade_line_geom([pts], thin, bold, (top_c + bot_c) / 2))


def write(name, text):
    with open(os.path.join(OUT, name), "w") as fh:
        fh.write(text)


write("a-fork-symbol.svg", svg(256, 256, "SAYA symbol, Fork", fork_symbol()))
write("a-fork-lockup.svg", lockup(fork_symbol(), wordmark("break"), "Fork"))
write("b-shade-symbol.svg", svg(256, 256, "SAYA symbol, Into the shade", shade_symbol()))
write("b-shade-lockup.svg", lockup(shade_symbol(uid="crl"), wordmark(), "Into the shade"))
write("c-shadeline-symbol.svg", svg(256, 256, "SAYA symbol, Shade line", shadeline_symbol()))
write("c-shadeline-lockup.svg", wordmark_only(shadeline_wordmark(), "Shade line"))
print("wrote", OUT)
