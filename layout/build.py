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

    # pfet_lvs: a PMOS in an nwell tied by an n-tap guard ring -- the first
    # p-device, exercising nwell + n-tap + psdm. Bulk = the well net (VDDN).
    pl = gdstk.Cell("pfet_lvs")
    W = 5.0
    pf = D.fet(pl, 2.0, 2.0, W=W, L=1.0, nf=1, kind="p")
    pgx, _ = D.poly_contact(pl, pf["gates"][0], 1.0, 2.0 + W + 0.13)
    D.guard_ring(pl, 0.8, 0.8, 2.0 + pf["totx"] + 1.2, 2.0 + W + 1.2,
                 w=0.5, kind="n")
    D.label(pl, "S", pf["sds"][0], 2.0 + W / 2)
    D.label(pl, "D", pf["sds"][1], 2.0 + W / 2)
    D.label(pl, "G", pgx, 2.0 + W + 0.13 + 0.45)
    D.label(pl, "VDDN", 1.05, 2.0 + W / 2)          # on the n-tap ring
    _write(pl)

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

    build_pmos_mirror()


def build_pmos_mirror():
    """The OTA's PMOS current-mirror load (xm3/xm4), common-centroid and
    LVS-clean. Same A B B A interleave, but a MIRROR not a pair: all gates tie
    to N1 and xm3 is diode-connected (its gate = its drain = N1). That diode
    tie makes the routing tidy -- N1 (all gates + the A drains col0/col4) all
    goes UP to one li strap, VDD (sources col1/col3) goes DOWN, VOUT (col2) is
    local -- so nothing has to cross. nwell is a port (floating well)."""
    c = gdstk.Cell("pmos_mirror")
    y0, W, L = 2.0, 5.0, 1.0
    fp = D.fet(c, 2.0, y0, W=W, L=L, nf=4, kind="p")
    col, g = fp["sds"], fp["gates"]
    ytop = y0 + W + 0.13
    yin = y0 + 0.25

    D.label(c, "VOUT", col[2], y0 + W / 2)          # B drain, local

    vy = y0 - 0.55                                   # VDD: col1,col3 down
    for x in (col[1], col[3]):
        D.strap(c, x - 0.085, vy, x + 0.085, yin)
    D.strap(c, col[1] - 0.085, vy, col[3] + 0.085, vy + 0.17)
    D.label(c, "VDD", col[1], vy + 0.085)

    ny = None                                        # N1: gates + col0,col4 up
    for x in g:
        _gx, ny = D.poly_contact(c, x, L, ytop, up=0.5)
    for x in (col[0], col[4]):
        D.strap(c, x - 0.085, y0 + W - 0.3, x + 0.085, ny + 0.085)
    D.strap(c, col[0] - 0.085, ny - 0.085, col[4] + 0.085, ny + 0.085)
    D.label(c, "N1", col[0], ny)
    _write(c)

    build_tail_bias()


def build_tail_bias():
    """The OTA's tail current source + bias diode (xm0/xmb) -- an NMOS current
    mirror, same shape as pmos_mirror but NMOS: xmb diode-connected sets VB,
    xm0 mirrors it to sink the tail. VB (all gates + the xmb drains) goes UP,
    VSS (sources) DOWN, TAIL (xm0 drain) local; substrate bulk is a port."""
    c = gdstk.Cell("tail_bias")
    y0, W, L = 2.0, 5.0, 1.0
    fp = D.fet(c, 2.0, y0, W=W, L=L, nf=4, kind="n")
    col, g = fp["sds"], fp["gates"]
    ytop = y0 + W + 0.13
    yin = y0 + 0.25

    D.label(c, "TAIL", col[2], y0 + W / 2)          # xm0 drain, local

    vy = y0 - 0.55                                   # VSS: col1,col3 down
    for x in (col[1], col[3]):
        D.strap(c, x - 0.085, vy, x + 0.085, yin)
    D.strap(c, col[1] - 0.085, vy, col[3] + 0.085, vy + 0.17)
    D.label(c, "VSS", col[1], vy + 0.085)

    ny = None                                        # VB: gates + col0,col4 up
    for x in g:
        _gx, ny = D.poly_contact(c, x, L, ytop, up=0.5)
    for x in (col[0], col[4]):
        D.strap(c, x - 0.085, y0 + W - 0.3, x + 0.085, ny + 0.085)
    D.strap(c, col[0] - 0.085, ny - 0.085, col[4] + 0.085, ny + 0.085)
    D.label(c, "VB", col[0], ny)
    _write(c)

    build_met2_test()


def build_met2_test():
    """Validate the met2 layer before the core uses it: two met1 pads joined by
    a met2 strap through a via at each end, and that strap passing OVER a met1
    wire of another net (a crossing that must be DRC-clean because they are
    different layers -- exactly what met2 buys the 5T core)."""
    c = gdstk.Cell("met2_test")
    D.strap(c, 1.0, 1.0, 1.4, 1.4, layer=D.MET1)      # pad A (met1)
    D.strap(c, 4.0, 1.0, 4.4, 1.4, layer=D.MET1)      # pad B (met1)
    D.via2(c, 1.2, 1.2)
    D.via2(c, 4.2, 1.2)
    D.strap(c, 1.04, 1.04, 4.36, 1.36, layer=D.MET2)  # met2 joins A--B
    D.strap(c, 2.5, 0.2, 2.7, 3.0, layer=D.MET1)      # met1 wire it crosses
    _write(c)

    build_ota5t_core()


def build_ota5t_core():
    """The whole 5T OTA (xmb/xm0/xm1/xm2/xm3/xm4) assembled and routed -- the
    piece the three sub-blocks were building toward. Three common-centroid nf=4
    strips STACKED: tail/bias (NMOS, bottom) -> input pair (NMOS, middle) ->
    mirror load (PMOS, top). The scaled W=10 devices match the sub-block LVS
    refs; bulk stays a port (VNB substrate, VNW nwell) this milestone.

    Routing plan (every crossing is on a different layer, so nothing shorts):
      * upper gap (input<->mirror): n1 on met1 at the OUTER columns (col0/col4),
        vout on li at the CENTRE (col2) -- different x AND layer, never touch;
        the input gates are kept OUT of this gap entirely.
      * input gates escape DOWNWARD (poly_contact_dn) and go out on MET2 -- vinp
        left, vinn right -- crossing the li tail routing on a different layer.
      * lower gap (tail<->input): tail on li (input sources down, xm0 drain up).
      * diode nodes vb (tail) and n1 (mirror) use the proven mirror idiom (gates
        + A-drains to one strap, sources to the rail on the other layer).
    """
    c = gdstk.Cell("ota5t_core")
    XC = 6.0                                   # shared centre x (col2 of each)

    def met1_drop(x, y0s, Ws, y_end):
        """Bring a S/D column out on met1. The li->met1 via lands on a real S/D
        licon stud INSIDE the strip (the standard stacked source contact), so it
        is guaranteed to sit on the device li -- the device li stops ~0.27um
        short of the nominal strip edge, so a via placed at the edge would float.
        met1 then runs from the via out to y_end, crossing any foreign li strap a
        layer above."""
        if y_end > y0s + Ws / 2:                     # up: stud near the top edge
            via_y = y0s + 0.06 + 0.34 * int((Ws - 0.56) / 0.34)
        else:                                        # down: first stud
            via_y = y0s + 0.06 + 0.34
        D.strap(c, x - 0.165, via_y - 0.2, x + 0.165, via_y + 0.2, layer=D.LI)
        D.via(c, x, via_y)
        D.strap(c, x - 0.14, min(via_y, y_end), x + 0.14, max(via_y, y_end),
                layer=D.MET1)

    # ---- tail/bias group: NMOS L=1 nf=4, xmb diode + xm0 (bottom) ----------
    x0T, y0T = XC - 2.725, 2.0
    T = D.fet(c, x0T, y0T, W=5.0, L=1.0, nf=4, kind="n")
    tcol, tg = T["sds"], T["gates"]
    # VSS rail (met1); sources col1/col3 drop to it on met1 so the VB li strap
    # can cross them a layer below
    rail_vss = 0.6
    for x in (tcol[1], tcol[3]):
        met1_drop(x, y0T, 5.0, rail_vss)
    D.strap(c, tcol[1] - 0.14, rail_vss - 0.15, tcol[3] + 0.14, rail_vss + 0.15,
            layer=D.MET1)
    D.label(c, "VSS", tcol[1], rail_vss, layer=D.MET1LBL)
    # VB (diode node): gates + col0/col4 to a LOW li strap, exit left. It passes
    # under the strip and over the VSS met1 -- both a layer away.
    vb_y = 1.4
    for x in tg:
        D.poly_contact_dn(c, x, 1.0, y0T - 0.13, down=(y0T - 0.13) - vb_y)
    for x in (tcol[0], tcol[4]):
        D.strap(c, x - 0.085, vb_y, x + 0.085, y0T, layer=D.LI)
    D.strap(c, x0T - 0.35, vb_y - 0.085, tcol[4] + 0.085, vb_y + 0.085, layer=D.LI)
    D.label(c, "VB", x0T - 0.25, vb_y)
    # TAIL (xm0 drain, col2) up to the tail bar on met1
    tail_bar = 9.3
    met1_drop(tcol[2], y0T, 5.0, tail_bar)

    # ---- input pair group: NMOS L=0.5 nf=4, xm1/xm2 (middle) --------------
    x0I, y0I = XC - 1.725, 12.0
    I = D.fet(c, x0I, y0I, W=5.0, L=0.5, nf=4, kind="n")
    icol, ig = I["sds"], I["gates"]
    itop, ibot = y0I + 5.0, y0I - 0.13
    # TAIL: sources col1/col3 down to the tail bar on met1; the bar ties xm0 too
    for x in (icol[1], icol[3]):
        met1_drop(x, y0I, 5.0, tail_bar)
    D.strap(c, min(icol[1], tcol[2]) - 0.14, tail_bar - 0.15,
            max(icol[3], tcol[2]) + 0.14, tail_bar + 0.15, layer=D.MET1)
    D.label(c, "TAIL", icol[2], tail_bar, layer=D.MET1LBL)
    # input gates escape DOWN as pure-li straps at two heights (vinp wide/left,
    # vinn narrow/right); they cross the tail met1 a layer above
    for x in (ig[0], ig[3]):                                     # VINP
        D.poly_contact_dn(c, x, 0.5, ibot, down=ibot - 11.2)
    D.strap(c, x0I - 0.95, 11.2 - 0.085, ig[3] + 0.165, 11.2 + 0.085, layer=D.LI)
    D.label(c, "VINP", x0I - 0.85, 11.2)
    for x in (ig[1], ig[2]):                                     # VINN
        D.poly_contact_dn(c, x, 0.5, ibot, down=ibot - 10.5)
    D.strap(c, ig[1] - 0.165, 10.5 - 0.085, x0I + I["totx"] + 0.95, 10.5 + 0.085,
            layer=D.LI)
    D.label(c, "VINN", x0I + I["totx"] + 0.85, 10.5)
    # n1 (A drains col0/col4) up on met1; vout (B drain col2) up on li
    n1_bar = 21.3
    for x in (icol[0], icol[4]):
        met1_drop(x, y0I, 5.0, n1_bar)
    D.strap(c, icol[2] - 0.085, itop - 0.5, icol[2] + 0.085, 22.0, layer=D.LI)  # vout

    # ---- mirror load group: PMOS L=1 nf=4, xm3 diode + xm4 (top) ----------
    x0M, y0M = XC - 2.725, 22.0
    M = D.fet(c, x0M, y0M, W=5.0, L=1.0, nf=4, kind="p")
    mcol, mg = M["sds"], M["gates"]
    mtop = y0M + 5.0
    D.label(c, "VNW", x0M + M["totx"] / 2, mtop + 0.25)          # nwell port
    # VDD rail (met1) above; sources col1/col3 up to it
    rail_vdd = 28.4
    for x in (mcol[1], mcol[3]):
        met1_drop(x, y0M, 5.0, rail_vdd)
    D.strap(c, mcol[1] - 0.14, rail_vdd - 0.15, mcol[3] + 0.14, rail_vdd + 0.15,
            layer=D.MET1)
    D.label(c, "VDD", mcol[1], rail_vdd, layer=D.MET1LBL)
    # N1: gates (poly down) + col0/col4 (met1 down) all to the met1 n1 bar
    for x in mg:
        _gx, yc = D.poly_contact_dn(c, x, 1.0, y0M - 0.13, down=(y0M - 0.13) - 21.5)
        D.via(c, x, yc)
    for x in (mcol[0], mcol[4]):
        met1_drop(x, y0M, 5.0, n1_bar)
    D.strap(c, mcol[0] - 0.14, n1_bar - 0.15, mcol[4] + 0.14, n1_bar + 0.15,
            layer=D.MET1)
    D.label(c, "N1", mcol[0], n1_bar, layer=D.MET1LBL)
    # VOUT (B drain col2) down on li to meet the input's vout li
    D.strap(c, mcol[2] - 0.085, 21.0, mcol[2] + 0.085, y0M + 0.4, layer=D.LI)
    D.label(c, "VOUT", mcol[2], 21.5)
    _write(c)

    build_out_stage()


def build_out_stage():
    """The miller_ota SECOND STAGE: xm5 (PMOS common-source) over xm6 (NMOS
    current-sink load) sharing the output node -- a class-A output stage, the
    same shape as a CMOS inverter. xm5 pulls VOUT toward VDD under gate N2 (the
    stage-1 output); xm6 sinks a fixed current set by VB. Scaled W=10 (nf=2) to
    match the sub-block refs; bulks are ports (VNB substrate, VNW nwell).

    Layout: the two devices face each other, VOUT shared on met1 in the gap
    (both drains are the centre column). Sources go to the rails (vss down, vdd
    up); the gates escape to the sides on li -- VB left (down), N2 right (up)."""
    c = gdstk.Cell("out_stage")
    XC = 5.0

    def met1_drop(x, y0s, Ws, y_end):
        if y_end > y0s + Ws / 2:
            via_y = y0s + 0.06 + 0.34 * int((Ws - 0.56) / 0.34)
        else:
            via_y = y0s + 0.06 + 0.34
        D.strap(c, x - 0.165, via_y - 0.2, x + 0.165, via_y + 0.2, layer=D.LI)
        D.via(c, x, via_y)
        D.strap(c, x - 0.14, min(via_y, y_end), x + 0.14, max(via_y, y_end),
                layer=D.MET1)

    vout_bar, rail_vss, rail_vdd = 8.5, 0.6, 16.5

    # ---- xm6: NMOS current-sink load, L=1 nf=2 (bottom) ------------------
    x0n, y0n = XC - 1.435, 2.0
    N = D.fet(c, x0n, y0n, W=5.0, L=1.0, nf=2, kind="n")
    nc, ng = N["sds"], N["gates"]
    met1_drop(nc[1], y0n, 5.0, vout_bar)                 # VOUT (drain, up)
    for x in (nc[0], nc[2]):                             # VSS (sources, down)
        met1_drop(x, y0n, 5.0, rail_vss)
    D.strap(c, nc[0] - 0.14, rail_vss - 0.15, nc[2] + 0.14, rail_vss + 0.15,
            layer=D.MET1)
    D.label(c, "VSS", nc[0], rail_vss, layer=D.MET1LBL)
    for x in ng:                                         # VB (gates, down/left)
        D.poly_contact_dn(c, x, 1.0, y0n - 0.13, down=(y0n - 0.13) - 1.3)
    D.strap(c, x0n - 0.85, 1.3 - 0.085, ng[1] + 0.165, 1.3 + 0.085, layer=D.LI)
    D.label(c, "VB", x0n - 0.75, 1.3)

    # ---- xm5: PMOS common-source, L=0.5 nf=2 (top) ----------------------
    x0p, y0p = XC - 0.935, 10.0
    P = D.fet(c, x0p, y0p, W=5.0, L=0.5, nf=2, kind="p")
    pc, pg = P["sds"], P["gates"]
    D.label(c, "VNW", x0p + P["totx"] / 2, y0p + 5.0 + 0.25)     # nwell port
    met1_drop(pc[1], y0p, 5.0, vout_bar)                 # VOUT (drain, down)
    D.strap(c, XC - 0.14, vout_bar - 0.15, XC + 0.14, vout_bar + 0.15,
            layer=D.MET1)
    D.label(c, "VOUT", XC, vout_bar, layer=D.MET1LBL)
    for x in (pc[0], pc[2]):                             # VDD (sources, up)
        met1_drop(x, y0p, 5.0, rail_vdd)
    D.strap(c, pc[0] - 0.14, rail_vdd - 0.15, pc[2] + 0.14, rail_vdd + 0.15,
            layer=D.MET1)
    D.label(c, "VDD", pc[0], rail_vdd, layer=D.MET1LBL)
    ny2 = None                                           # N2 (gates, up/right)
    for x in pg:
        _gx, ny2 = D.poly_contact(c, x, 0.5, y0p + 5.0 + 0.13, up=0.55)
    D.strap(c, pg[0] - 0.165, ny2 - 0.085, x0p + P["totx"] + 0.85, ny2 + 0.085,
            layer=D.LI)
    D.label(c, "N2", x0p + P["totx"] + 0.75, ny2)
    _write(c)

    build_res_rz()


def build_res_rz():
    """The Miller nulling resistor Rz -- a sky130 xhigh_po precision poly
    resistor (2000 ohm/sq), the leg's FIRST passive and first PDK special-marker
    device. The resistive body is poly UNDER the poly_res(66/13) marker, with
    urpm(79/20) + psdm defining the 2k-ohm flavour; a contacted poly terminal at
    each end sits OUTSIDE the body (that is what the extractor reads as a
    terminal). W = 0.69 um, L = 3.45 um (5 squares) -> ~10 kOhm = the applied
    THD-fix Rz (design-notes.md 12)."""
    c = gdstk.Cell("res_rz")
    xc, W, L, ext = 2.0, 0.69, 3.45, 0.6
    x0, x1 = xc - W / 2, xc + W / 2
    ytot = 2 * ext + L
    D._r(c, D.POLY, x0, 0.0, x1, ytot)                       # the poly strip
    D._r(c, D.POLY_RES, x0, ext, x1, ext + L)                # resistive body
    D._r(c, D.URPM, xc - 0.635, ext - 0.1, xc + 0.635, ext + L + 0.1)  # >=1.27 wide
    D._r(c, D.PSDM, xc - 0.77, -0.2, xc + 0.77, ytot + 0.2)

    def term(name, yc):                                      # poly contact = pin
        D._r(c, D.LICON, xc - 0.085, yc - 0.085, xc + 0.085, yc + 0.085)
        D._r(c, D.NPC, xc - 0.185, yc - 0.185, xc + 0.185, yc + 0.185)
        D._r(c, D.LI, xc - 0.165, yc - 0.165, xc + 0.165, yc + 0.165)
        D.label(c, name, xc, yc)
    term("P", 0.3)
    term("M", ytot - 0.3)
    _write(c)


if __name__ == "__main__":
    build()
