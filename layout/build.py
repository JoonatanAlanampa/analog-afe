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
    mirror load (PMOS, top). PRODUCTION FULL-W (the taped-out sizing): the device
    widths are scaled to the miller_ota.sp netlist by FINGER WIDTH, keeping the
    proven nf=4 A-B-B-A interleave (so every x-coordinate and the LVS topology are
    unchanged -- only the strip heights and the y-axis remap). Each device is two
    fingers: input pair xm1/xm2 = W=40um (m8, finger 20), mirror xm3/xm4 and
    tail/bias xm0/xmb = W=20um (m4, finger 10). Bulk stays a port (VNB substrate,
    VNW nwell); the top-level assembly adds the body ties.

    Routing plan (every crossing is on a different layer, so nothing shorts):
      * upper gap (input<->mirror): n1 on met1 at the OUTER columns (col0/col4),
        vout on li at the CENTRE (col2) -- different x AND layer, never touch;
        the input gates are kept OUT of this gap entirely.
      * input gates escape DOWNWARD (poly_contact_dn) on li -- vinn left (-> n1),
        vinp right (-> n2/vout) -- crossing the li tail routing on a diff layer.
      * lower gap (tail<->input): tail on li (input sources down, xm0 drain up).
      * diode nodes vb (tail) and n1 (mirror) use the proven mirror idiom (gates
        + A-drains to one strap, sources to the rail on the other layer).

    FEEDBACK-SIGN: the input labels match miller_ota.sp's inverting convention --
    xm1 (gate=VINN) drains to n1 (the diode/mirror side); xm2 (gate=VINP) drives
    n2 (=vout, the stage-1 output into stage 2). Device A (gates g0/g3, drains
    the OUTER columns col0/col4 = n1) carries VINN; device B (gates g1/g2, drain
    col2 = vout) carries VINP. Getting this backwards gives positive feedback and
    a latched output -- a silent failure, so it is asserted by the label choice.
    """
    c = gdstk.Cell("ota5t_core")
    XC = 6.0                                   # shared centre x (col2 of each)
    WT, WI, WM = 10.0, 20.0, 10.0              # finger widths -> dev W 20/40/20

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

    # ---- tail/bias group: NMOS L=1 nf=4 (W=20 each), xmb diode + xm0 (bottom)
    x0T, y0T = XC - 2.725, 2.0
    T = D.fet(c, x0T, y0T, W=WT, L=1.0, nf=4, kind="n")
    tcol, tg = T["sds"], T["gates"]
    topT = y0T + WT
    # VSS rail (met1); sources col1/col3 drop to it on met1 so the VB li strap
    # can cross them a layer below
    rail_vss = 0.6
    for x in (tcol[1], tcol[3]):
        met1_drop(x, y0T, WT, rail_vss)
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
    tail_bar = topT + 2.3
    met1_drop(tcol[2], y0T, WT, tail_bar)

    # ---- input pair group: NMOS L=0.5 nf=4 (W=40 each), xm1/xm2 (middle) ----
    x0I, y0I = XC - 1.725, topT + 5.0
    I = D.fet(c, x0I, y0I, W=WI, L=0.5, nf=4, kind="n")
    icol, ig = I["sds"], I["gates"]
    itop, ibot = y0I + WI, y0I - 0.13
    # TAIL: sources col1/col3 down to the tail bar on met1; the bar ties xm0 too
    for x in (icol[1], icol[3]):
        met1_drop(x, y0I, WI, tail_bar)
    D.strap(c, min(icol[1], tcol[2]) - 0.14, tail_bar - 0.15,
            max(icol[3], tcol[2]) + 0.14, tail_bar + 0.15, layer=D.MET1)
    D.label(c, "TAIL", icol[2], tail_bar, layer=D.MET1LBL)
    # input gates escape DOWN as pure-li straps at two heights. VINN (-> n1, the
    # diode side) on device A gates g0/g3, VINP (-> n2/vout) on device B gates
    # g1/g2 -- matching miller_ota.sp's inverting convention. They cross the tail
    # met1 a layer above.
    vinn_y, vinp_y = y0I - 0.8, y0I - 1.5
    for x in (ig[0], ig[3]):                                     # VINN (-> n1)
        D.poly_contact_dn(c, x, 0.5, ibot, down=ibot - vinn_y)
    D.strap(c, x0I - 0.95, vinn_y - 0.085, ig[3] + 0.165, vinn_y + 0.085,
            layer=D.LI)
    D.label(c, "VINN", x0I - 0.85, vinn_y)
    for x in (ig[1], ig[2]):                                     # VINP (-> n2/vout)
        D.poly_contact_dn(c, x, 0.5, ibot, down=ibot - vinp_y)
    D.strap(c, ig[1] - 0.165, vinp_y - 0.085, x0I + I["totx"] + 0.95,
            vinp_y + 0.085, layer=D.LI)
    D.label(c, "VINP", x0I + I["totx"] + 0.85, vinp_y)
    # n1 (A drains col0/col4) up on met1; vout (B drain col2) up on li
    y0M = itop + 5.0
    n1_bar = y0M - 0.7
    for x in (icol[0], icol[4]):
        met1_drop(x, y0I, WI, n1_bar)
    D.strap(c, icol[2] - 0.085, itop - 0.5, icol[2] + 0.085, y0M, layer=D.LI)  # vout

    # ---- mirror load group: PMOS L=1 nf=4 (W=20 each), xm3 diode + xm4 (top)
    x0M = XC - 2.725
    M = D.fet(c, x0M, y0M, W=WM, L=1.0, nf=4, kind="p")
    mcol, mg = M["sds"], M["gates"]
    mtop = y0M + WM
    D.label(c, "VNW", x0M + M["totx"] / 2, mtop + 0.25)          # nwell port
    # VDD rail (met1) above; sources col1/col3 up to it
    rail_vdd = mtop + 1.4
    for x in (mcol[1], mcol[3]):
        met1_drop(x, y0M, WM, rail_vdd)
    D.strap(c, mcol[1] - 0.14, rail_vdd - 0.15, mcol[3] + 0.14, rail_vdd + 0.15,
            layer=D.MET1)
    D.label(c, "VDD", mcol[1], rail_vdd, layer=D.MET1LBL)
    # N1: gates (poly down) + col0/col4 (met1 down) all to the met1 n1 bar
    for x in mg:
        _gx, yc = D.poly_contact_dn(c, x, 1.0, y0M - 0.13,
                                    down=(y0M - 0.13) - (n1_bar + 0.2))
        D.via(c, x, yc)
    for x in (mcol[0], mcol[4]):
        met1_drop(x, y0M, WM, n1_bar)
    D.strap(c, mcol[0] - 0.14, n1_bar - 0.15, mcol[4] + 0.14, n1_bar + 0.15,
            layer=D.MET1)
    D.label(c, "N1", mcol[0], n1_bar, layer=D.MET1LBL)
    # VOUT (B drain col2) down on li to meet the input's vout li
    D.strap(c, mcol[2] - 0.085, n1_bar + 0.3, mcol[2] + 0.085, y0M + 0.4,
            layer=D.LI)
    D.label(c, "VOUT", mcol[2], y0M - 0.3)
    _write(c)

    build_out_stage()


def build_out_stage():
    """The miller_ota SECOND STAGE: xm5 (PMOS common-source) over xm6 (NMOS
    current-sink load) sharing the output node -- a class-A output stage, the
    same shape as a CMOS inverter. xm5 pulls VOUT toward VDD under gate N2 (the
    stage-1 output); xm6 sinks a fixed current set by VB.

    PRODUCTION FULL-W (the corner-verified THD fix, pout=2.5): both devices are
    W=150um -- 10 fingers of W=15 each (m30 of the w5 unit device). These are
    single (unmatched) devices, so instead of a common-centroid interleave they
    are plain multi-finger FETs: for nf fingers the nf+1 S/D columns alternate,
    ODD columns = drain (VOUT), EVEN columns = source (rail), all gates common.
    Bulks are ports (VNB substrate, VNW nwell); the assembly adds the ties.

    Layout: the two devices face each other, VOUT shared on met1 in the gap.
    Sources go to the rails (vss down, vdd up) on met1 bars spanning the even
    columns; the gates escape to the sides on li -- VB left (down), N2 right
    (up). The VOUT bar in the gap ties every odd column of both devices."""
    c = gdstk.Cell("out_stage")
    XC, NF, WF = 7.0, 10, 15.0                # 10 fingers x W15 = W150 each

    def met1_drop(x, y0s, Ws, y_end):
        if y_end > y0s + Ws / 2:
            via_y = y0s + 0.06 + 0.34 * int((Ws - 0.56) / 0.34)
        else:
            via_y = y0s + 0.06 + 0.34
        D.strap(c, x - 0.165, via_y - 0.2, x + 0.165, via_y + 0.2, layer=D.LI)
        D.via(c, x, via_y)
        D.strap(c, x - 0.14, min(via_y, y_end), x + 0.14, max(via_y, y_end),
                layer=D.MET1)

    def bar(xs, y, name=None, lbl=D.MET1LBL):
        D.strap(c, min(xs) - 0.14, y - 0.15, max(xs) + 0.14, y + 0.15,
                layer=D.MET1)
        if name:
            D.label(c, name, min(xs), y, layer=lbl)

    y0n, y0p = 2.0, 22.0
    topn, topp = y0n + WF, y0p + WF
    vout_bar = topn + 2.5
    rail_vss, rail_vdd = 0.6, topp + 2.0

    # ---- xm6: NMOS current-sink load, L=1 (bottom) -----------------------
    Ln = 1.0
    totn = (NF + 1) * D.SD + NF * Ln
    x0n = XC - totn / 2
    N = D.fet(c, x0n, y0n, W=WF, L=Ln, nf=NF, kind="n")
    nc, ng = N["sds"], N["gates"]
    dn = [nc[i] for i in range(1, NF + 1, 2)]            # odd cols -> VOUT
    sn = [nc[i] for i in range(0, NF + 1, 2)]            # even cols -> VSS
    for x in dn:
        met1_drop(x, y0n, WF, vout_bar)
    for x in sn:
        met1_drop(x, y0n, WF, rail_vss)
    bar(sn, rail_vss, "VSS")
    for x in ng:                                         # VB (gates, down/left)
        D.poly_contact_dn(c, x, Ln, y0n - 0.13, down=(y0n - 0.13) - 1.3)
    D.strap(c, x0n - 0.85, 1.3 - 0.085, ng[-1] + 0.165, 1.3 + 0.085, layer=D.LI)
    D.label(c, "VB", x0n - 0.75, 1.3)

    # ---- xm5: PMOS common-source, L=0.5 (top) ----------------------------
    Lp = 0.5
    totp = (NF + 1) * D.SD + NF * Lp
    x0p = XC - totp / 2
    P = D.fet(c, x0p, y0p, W=WF, L=Lp, nf=NF, kind="p")
    pc, pg = P["sds"], P["gates"]
    D.label(c, "VNW", XC, topp + 0.25)                   # nwell port
    dp = [pc[i] for i in range(1, NF + 1, 2)]            # odd cols -> VOUT
    sp = [pc[i] for i in range(0, NF + 1, 2)]            # even cols -> VDD
    for x in dp:
        met1_drop(x, y0p, WF, vout_bar)
    bar(dn + dp, vout_bar, "VOUT")                       # the shared output node
    for x in sp:
        met1_drop(x, y0p, WF, rail_vdd)
    bar(sp, rail_vdd, "VDD")
    ny2 = None                                           # N2 (gates, up/right)
    for x in pg:
        _gx, ny2 = D.poly_contact(c, x, Lp, topp + 0.13, up=0.55)
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

    build_cap_cc()


def build_cap_cc():
    """The Miller compensation cap Cc -- a sky130 MIM capacitor (cap_mim on
    metal3). The bottom plate is met3 (P1); the top plate is capm (89/44, P2),
    contacted UP through via3 to a met4 pad -- the MIM dielectric between capm and
    met3 IS the capacitor. Unlike the poly resistor this is a 2-terminal device,
    so it LVS-compares as a plain C.

    PRODUCTION FULL-VALUE: the applied THD fix uses Cc = 4 pF. cap_mim is
    ~2 fF/um^2, so a 44.72 x 44.72 um plate (~2000 um^2) draws the full 4 pF
    (the earlier milestone used a 10x10 scaled 200 fF demonstrator)."""
    c = gdstk.Cell("cap_cc")
    side = 44.72                    # ~2000 um^2 * 2 fF/um^2 ~= 4 pF
    xc = 2.0 + side / 2
    # top plate (capm) -> the cap area
    D._r(c, D.CAPM, 2.0, 2.0, 2.0 + side, 2.0 + side)
    # bottom plate (met3): encloses capm by >=0.14 and extends left for the P1
    # terminal (met3 outside capm = met3_ncap, where a met3 label attaches)
    D._r(c, D.MET3, 0.5, 1.8, 2.2 + side, 2.2 + side)
    D.label(c, "P1", 1.15, xc, layer=D.MET3LBL)
    # top-plate contact: via3 on capm up to a met4 pad = P2 (capm/via3/met4 are
    # one net; via3 over capm bonds to capm, never the met3 under it)
    D._r(c, D.VIA3, xc - 0.1, xc - 0.1, xc + 0.1, xc + 0.1)
    D._r(c, D.MET4, xc - 0.6, xc - 0.6, xc + 0.6, xc + 0.6)
    D.label(c, "P2", xc, xc, layer=D.MET4LBL)
    _write(c)

    build_miller_ota()


def build_miller_ota():
    """The whole two-stage Miller amplifier at PRODUCTION FULL-W, assembled from
    the four individually-verified blocks: the 5T core (stage 1, input W=40 /
    mirror+tail W=20), the class-A output (stage 2, W=150), the nulling resistor
    Rz (10k) and the compensation cap Cc (4 pF). Every block is placed as an
    instance; the pins are looked up from each placed sub-cell (`pins[...]`) so
    the routes follow the real geometry, and the whole thing is flattened + body-
    tied + extraction-verified by run_amp_extract.py.

    Floorplan (left->right): core | out_stage | (Rz above) | Cc. The blocks only
    use li/met1 internally, so met2 is a free over-the-cell routing layer for the
    inter-stage signals; the compensation branch climbs met2->met3->met4 to reach
    the MIM cap. Rails: VSS ties on met1 (both stages' rails sit at y~0.6); VDD
    ties on met2 (the two rails are at different heights). Every crossing is
    inter-layer. n2 (stage-1 out) runs a met2 trunk at y=38, kept BELOW the VDD
    tie (y>=39) so the two nets never meet."""
    top = gdstk.Cell("miller_ota")
    place = {"ota5t_core": (0.0, 0.0), "out_stage": (12.0, 0.0),
             "res_rz": (27.0, 31.0), "cap_cc": (32.0, 0.0)}
    pins = {}
    for name, (dx, dy) in place.items():
        sub = gdstk.read_gds(str(OUT / f"{name}.gds")).cells[0]
        top.add(gdstk.Reference(sub, (dx, dy)))
        pins[name] = {l.text: (l.origin[0] + dx, l.origin[1] + dy)
                      for l in sub.labels}
    core, out, rz, cap = (pins[k] for k in
                          ("ota5t_core", "out_stage", "res_rz", "cap_cc"))

    def m2(x0, y0, x1, y1):                       # a met2 wire between two points
        D.strap(top, min(x0, x1) - 0.16, min(y0, y1) - 0.16,
                max(x0, x1) + 0.16, max(y0, y1) + 0.16, D.MET2)

    # --- VSS rail tie (met1): both rails sit at y~0.6, so a straight bridge -----
    D.strap(top, core["VSS"][0] - 0.14, 0.45, out["VSS"][0] + 0.14, 0.75, D.MET1)

    # --- VDD rail tie (met2): core rail (y53.4) up, across, down onto out rail --
    D.via2(top, *core["VDD"])                                      # core rail m1->m2
    m2(core["VDD"][0], core["VDD"][1], 16.0, core["VDD"][1])       # across the top
    m2(16.0, core["VDD"][1], 16.0, out["VDD"][1])                  # down the gap
    D.via2(top, 16.0, out["VDD"][1])                               # onto out rail

    # --- n2: stage-1 out (core VOUT) -> stage-2 gate (out N2) -> Rz.P ----------
    # tap the core end on the TALL mirror-drain li column (y~44, continuous
    # 42..51.8), not the label point (41.7) which sits in a notch under it.
    cn2, oN2, rP = (core["VOUT"][0], 44.0), out["N2"], rz["P"]
    for p in (cn2, oN2, rP):
        D.via_li_met2(top, *p)
    ytr = 38.0
    m2(cn2[0], cn2[1], cn2[0], ytr)                                # core n2 up
    m2(cn2[0], ytr, 28.0, ytr)                                     # trunk (kept < VDD)
    m2(oN2[0], oN2[1], oN2[0], ytr)                                # out N2 up to trunk
    m2(28.0, ytr, 28.0, rP[1])                                     # down toward Rz.P
    m2(28.0, rP[1], rP[0], rP[1])                                  # into Rz.P
    D.label(top, "n2", 12.0, ytr, layer=D.MET2LBL)

    # --- vb: stage-1 tail diode -> stage-2 sink gate, along the bottom ---------
    # tap left of the VB label so the li pad clears the tail-drain riser (3.335).
    cvb, ovb, yb = (2.95, core["VB"][1]), out["VB"], 2.6
    D.via_li_met2(top, *cvb)
    D.via_li_met2(top, *ovb)
    m2(cvb[0], cvb[1], cvb[0], yb)
    m2(cvb[0], yb, ovb[0], yb)
    m2(ovb[0], ovb[1], ovb[0], yb)
    D.label(top, "vb", 7.0, yb, layer=D.MET2LBL)

    # --- compensation branch: n2 -Rz- nz -Cc- vout ----------------------------
    # nz: Rz.M -> met2 -> via2 down onto the Cc bottom plate (met3 P1, in the
    # strip left of capm)
    rM, p1 = rz["M"], cap["P1"]
    D.via_li_met2(top, *rM)
    xp1 = 33.2                                     # in the P1 met3 strip (32.5..34)
    m2(rM[0], rM[1], xp1, rM[1])
    D.via_met2_met3(top, xp1, rM[1])
    D.label(top, "nz", 31.0, rM[1], layer=D.MET2LBL)
    # vout: out VOUT (met1) -> met2 -> an ISOLATED met2/met3/met4 stack left of
    # the cap (never on the met3 P1 plate) -> met4 across the cap to P2
    ov, p2, xs = out["VOUT"], cap["P2"], 31.0
    D.via2(top, *ov)                                               # met1 -> met2
    m2(ov[0], ov[1], xs, ov[1])
    D.via_met2_met3(top, xs, ov[1])
    D.via_met3_met4(top, xs, ov[1])
    D.strap(top, xs - 0.28, ov[1] - 0.28, xs + 0.28, ov[1] + 0.28, D.MET3)  # min area
    D.strap(top, xs - 0.16, ov[1] - 0.16, p2[0] + 0.16, ov[1] + 0.16, D.MET4)
    D.strap(top, p2[0] - 0.16, ov[1] - 0.16, p2[0] + 0.16, p2[1] + 0.16, D.MET4)

    # --- substrate body tie: a p+ tap in the gap, wired to the VSS rail --------
    D.tap(top, 9.5, 1.0, 10.3, 1.9, kind="p")
    D.via(top, 9.9, 1.45)
    D.strap(top, 9.9 - 0.14, 0.6, 9.9 + 0.14, 1.55, layer=D.MET1)
    D.label(top, "vss_tap", 9.9, 1.9, layer=D.LILBL)

    # --- nwell body ties: an n+ tap in each well -> VDD (wells widened for room)
    # stage-1 mirror well -> core VDD rail
    D._r(top, D.NWELL, 8.6, 41.9, 9.9, 52.1)
    D.tap(top, 9.0, 45.0, 9.6, 49.0, kind="n")
    D.via(top, 9.3, 47.0)
    D.strap(top, 9.3 - 0.14, 47.0, 9.3 + 0.14, 53.4, layer=D.MET1)     # up
    D.strap(top, 7.0, 53.25, 9.3 + 0.14, 53.55, layer=D.MET1)          # to VDD rail
    D.label(top, "nw1_tap", 9.2, 50.0, layer=D.LILBL)
    # stage-2 PMOS well -> out VDD rail
    D._r(top, D.NWELL, 23.2, 22.0, 25.4, 37.2)
    D.tap(top, 24.4, 26.0, 25.0, 33.0, kind="n")
    D.via(top, 24.7, 29.0)
    D.strap(top, 24.7 - 0.14, 29.0, 24.7 + 0.14, 39.0, layer=D.MET1)   # up
    D.strap(top, 22.95, 38.85, 24.7 + 0.14, 39.15, layer=D.MET1)       # to VDD rail
    D.label(top, "nw2_tap", 24.6, 34.0, layer=D.LILBL)
    top.flatten()
    lib = gdstk.Library()
    lib.add(top)
    lib.write_gds(str(OUT / "miller_ota.gds"))
    print("wrote miller_ota.gds")


if __name__ == "__main__":
    build()
