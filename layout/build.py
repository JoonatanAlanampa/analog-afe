"""Draw the analog-afe layout cells to layout/out/*.gds.

Phase-2 kickoff scope: prove the flow on real devices before the full OTA.
  nfet_test   -- the input-pair NMOS finger structure (W=5, L=0.5, 2 fingers)
  cc_pair     -- the same pair drawn COMMON-CENTROID (A B B A) with dummy
                 devices at the ends -- the matching technique the OTA needs.
"""
from pathlib import Path

import gdstk

import device as D

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def _write(cell):
    lib = gdstk.Library()
    lib.add(cell)
    lib.write_gds(str(OUT / f"{cell.name}.gds"))
    print(f"wrote {cell.name}.gds")


def build():
    c = gdstk.Cell("nfet_test")
    D.fet(c, 0.0, 0.0, W=5.0, L=0.5, nf=2, kind="n")
    _write(c)

    # nfet_lvs: single-finger device wired for LVS -- gate contact + S/G/D
    # labels. Bulk is a port (no tap; the extractor exports the untapped
    # p-substrate as one net, as the stdcells cells do).
    nl = gdstk.Cell("nfet_lvs")
    fp = D.fet(nl, 0.0, 0.0, W=5.0, L=0.5, nf=1, kind="n")
    src, drn = fp["sds"][0], fp["sds"][1]
    gx, _gc = D.poly_contact(nl, fp["gates"][0], 0.5, fp["W"] + 0.13)
    D.label(nl, "S", src, fp["W"] / 2)
    D.label(nl, "D", drn, fp["W"] / 2)
    D.label(nl, "G", gx, fp["W"] + 0.13 + 0.45)
    _write(nl)

    # common-centroid input pair: 6 fingers D A B B A D (A/B centroids coincide
    # at finger 3.5, the classic 1-D common-centroid), wrapped in a p-tap guard
    # ring. Gate straps + S/D routing (for LVS) are the next step; this proves
    # the matched geometry is DRC-clean.
    cc = gdstk.Cell("cc_pair")
    fp = D.fet(cc, 2.0, 2.0, W=5.0, L=0.5, nf=6, kind="n")
    x1 = 2.0 + fp["totx"]
    D.guard_ring(cc, 0.97, 0.97, x1 + 1.03, 8.03, w=0.5, kind="p")
    _write(cc)

    build_cc_diff()


def build_cc_diff():
    """The common-centroid pair ROUTED into a connected differential pair and
    LVS-clean. Four fingers A B B A; the S/D columns alternate so that:
      col0,col4 = A drain (OA)   col2 = B drain (OB)   col1,col3 = shared tail
    which makes A = fingers 0,3 (D=OA S=TAIL G=VA) and B = fingers 1,2 (D=OB
    S=TAIL G=VB) -- two W=10 devices with a common source, the input pair.

    Routing keeps every net on a layer/level where it can't short another:
    S/D go DOWN, gates go UP; the two nets that must span the middle (tail on
    li, OA on met1) sit at different y so their risers never cross; VB (met1)
    crosses VA (li) only where they are on different layers.
    """
    c = gdstk.Cell("cc_diff")
    y0, W, L = 2.0, 5.0, 0.5
    fp = D.fet(c, 2.0, y0, W=W, L=L, nf=4, kind="n")
    col = fp["sds"]          # x-centres col0..col4
    g = fp["gates"]          # gate x-centres g0..g3
    ytop = y0 + W + 0.13     # poly end above diff
    yin = y0 + 0.25          # risers overlap UP into the device S/D li column

    # --- OB: B drain, col2, local li label -------------------------------
    D.label(c, "OB", col[2], y0 + W / 2)

    # --- TAIL: col1 + col3, li risers down to a li strap ------------------
    ty = y0 - 0.55
    for x in (col[1], col[3]):
        D.strap(c, x - 0.085, ty, x + 0.085, yin)           # riser (overlaps li)
    D.strap(c, col[1] - 0.085, ty, col[3] + 0.085, ty + 0.17)   # bar
    D.label(c, "TAIL", col[1], ty + 0.085)

    # --- OA: col0 + col4, li risers to met1 (a level BELOW tail) ----------
    oy = y0 - 1.05
    for x in (col[0], col[4]):
        D.strap(c, x - 0.085, oy - 0.12, x + 0.085, yin)    # li riser past mcon
        D.via(c, x, oy)
    D.strap(c, col[0] - 0.14, oy - 0.15, col[4] + 0.14, oy + 0.15, layer=D.MET1)
    D.label(c, "OA", col[0], oy, layer=D.MET1LBL)

    # --- VA: g0 + g3 gate contacts, li strap high at the top -------------
    va_y = None
    for x in (g[0], g[3]):
        _gx, va_y = D.poly_contact(c, x, L, ytop, up=1.05)
    D.strap(c, g[0] - 0.085, va_y - 0.085, g[3] + 0.085, va_y + 0.085)
    D.label(c, "VA", g[0], va_y)

    # --- VB: g1 + g2 gate contacts, met1 strap (crosses VA on met1) ------
    vb_y = None
    for x in (g[1], g[2]):
        _gx, vb_y = D.poly_contact(c, x, L, ytop, up=0.35)
        D.via(c, x, vb_y)
    D.strap(c, g[1] - 0.14, vb_y - 0.15, g[2] + 0.14, vb_y + 0.15, layer=D.MET1)
    D.label(c, "VB", g[1], vb_y, layer=D.MET1LBL)

    _write(c)


if __name__ == "__main__":
    build()
