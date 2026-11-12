"""Inline logo snippets for site/page.html: python3 brand/logo/site_snippets.py

Writes brand/logo/final/web/site-snippets.html with
  - the <head> icon links (SVG favicon that turns light teal in dark mode, PNG fallback, apple-touch icon),
    all as data URIs so the page stays one self-contained file;
  - the header lockup and the hero wordmark as inline SVG, coloured by the page's own tokens through
    classes (.logo .sym → var(--accent), .logo .wm → var(--ink)), so light and dark mode follow the page.
"""
import base64, os, urllib.parse
import kit

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "final", "web")


def data_png(name):
    with open(os.path.join(WEB, name), "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode()


def data_svg(text):
    return "data:image/svg+xml," + urllib.parse.quote(text.strip(), safe=" =:/'(),;#")


def lockup_svg():
    """Horizontal lockup without its padding: symbol (primary cut) + wordmark, same proportions as the master."""
    sym_h = 232
    d, bbox = kit.symbol_d(**kit.CUTS["primary"])
    s = sym_h / (bbox[3] - bbox[1])
    sym_w = (bbox[2] - bbox[0]) * s
    crown_cy = (kit.CUTS["primary"]["cy"] - bbox[1]) * s
    cap, gap = 0.52 * sym_h, 0.24 * sym_h
    wm_y = (crown_cy + sym_h / 2) / 2 - cap / 2
    ws = cap / kit.H
    width = sym_w + gap + kit.WM_W * ws
    sym = (f'<path class="sym" fill-rule="evenodd" transform="translate({kit.f(-bbox[0] * s)} {kit.f(-bbox[1] * s)}) '
           f'scale({kit.f(s)})" d="{d}"/>')
    wm = (f'<path class="wm" fill-rule="evenodd" transform="translate({kit.f(sym_w + gap - kit._WM_LEFT * ws)} {kit.f(wm_y)}) '
          f'scale({kit.f(ws)})" d="{kit.WM_D}"/>')
    return (f'<svg class="logo" viewBox="0 0 {kit.f(width)} {sym_h}" role="img" aria-label="SAYA">'
            f'{sym}{wm}</svg>')


def wordmark_svg():
    return (f'<svg class="logo wordmark" viewBox="0 0 {kit.f(kit.WM_W)} {kit.H}" role="img" aria-label="SAYA">'
            f'<path class="wm" fill-rule="evenodd" transform="translate({kit.f(-kit._WM_LEFT)} 0)" d="{kit.WM_D}"/></svg>')


def main():
    with open(os.path.join(WEB, "favicon.svg")) as fh:
        fav = fh.read()
    head = (f'<link rel="icon" type="image/svg+xml" href="{data_svg(fav)}">\n'
            f'<link rel="icon" type="image/png" sizes="32x32" href="{data_png("favicon-32.png")}">\n'
            f'<link rel="apple-touch-icon" href="{data_png("apple-touch-icon.png")}">')
    out = os.path.join(WEB, "site-snippets.html")
    with open(out, "w") as fh:
        fh.write("<!-- head -->\n" + head + "\n<!-- header lockup -->\n" + lockup_svg() +
                 "\n<!-- hero wordmark -->\n" + wordmark_svg() + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
