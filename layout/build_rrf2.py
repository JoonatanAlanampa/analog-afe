"""Draw the miller_rrf2 layout blocks to layout/out/*.gds.

miller_rrf2 is the amplifier that actually met the spec -- folded rail-to-rail
input with a self-biased cascoded summing node, robustly under 0.1 % THD at
1 kHz across the full PVT box (docs/input-stage.md). It is a FROM-SCRATCH
layout: 25 transistors against miller_ota's 8, in five new device blocks plus
two blocks reused verbatim from the miller_ota leg.

    reused:  out_stage (W=150/W=150 -- rrf2 runs the same pout=2.5 stage 2)
             res_rz    (10 k -- the same nulling resistor)
    new:     rrf2_nin    xmb  xm0  xm1  xm2      (NMOS tail + input pair)
             rrf2_fold   xm9  xm10 xm11 xm12     (PMOS fold sources + cascodes)
             rrf2_cmir   xm13 xm14 xm15 xm16     (self-biased cascode mirror)
             rrf2_plow   xmp0 xmp1 xmp2 xmp3 xmp4 (PMOS low-side path)
             rrf2_bias_n xbn1 xbn2 xbn3          (bias chain, NMOS half)
             rrf2_bias_p xbp1 xbp2 xbp3          (bias chain, PMOS half)
             cap_cc9     the 9 pF MIM (rrf2 needs 9 p, not miller_ota's 4 p)
             miller_rrf2 the assembled, routed amplifier

`build.py` (the miller_ota leg) is NOT touched: miller_ota's cells stay exactly
as they were taped-out-prepped, and this file only ADDS cells.

THE ONE ROUTING INVARIANT everything below leans on: li and met1 are different
layers, so an li wire and a met1 wire may cross freely -- only same-layer
overlap shorts. A common-centroid strip forces device A's private terminal onto
the OUTER columns (which must be bridged ACROSS the centre) and device B's onto
the CENTRE column, so the outer net always routes on met1 and the centre net on
li, and the bridge passes over the riser harmlessly.
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


# --------------------------------------------------------------- helpers ----
def met1_drop(c, x, y0s, Ws, y_end):
    """Bring a source/drain column out on met1. The li->met1 via lands on a real
    licon stud INSIDE the strip (the stacked source contact), so it is always on
    the device li -- a via at the nominal strip edge would float, because the
    device li stops ~0.27 um short of it. Same helper the miller_ota core uses."""
    if y_end > y0s + Ws / 2:                       # exit up: stud near the top
        via_y = y0s + 0.06 + 0.34 * int((Ws - 0.56) / 0.34)
    else:                                          # exit down: first stud
        via_y = y0s + 0.06 + 0.34
    D.strap(c, x - 0.165, via_y - 0.2, x + 0.165, via_y + 0.2, layer=D.LI)
    D.via(c, x, via_y)
    D.strap(c, x - 0.14, min(via_y, y_end), x + 0.14, max(via_y, y_end),
            layer=D.MET1)
    return via_y


def m1bar(c, xs, y, name=None):
    """A met1 bar tying a set of columns, optionally labelled."""
    D.strap(c, min(xs) - 0.14, y - 0.15, max(xs) + 0.14, y + 0.15, layer=D.MET1)
    if name:
        D.label(c, name, min(xs), y, layer=D.MET1LBL)


def libar(c, x0, x1, y, name=None, lx=None, hb=0.085):
    """An li bar tying a set of gate/li risers, optionally labelled. `hb` is the
    half-height BELOW the centre line: a strap that joins gate pads to S/D li
    risers on an L=0.5 strip must be pulled down to the pad bottom (hb=0.165),
    because at that gate length the pad edge sits only 0.145 um from the outer
    S/D riser -- under the 0.17 li spacing. Merging them into one polygon is the
    right fix rather than a jog: they are the same net (the diode node)."""
    D.strap(c, x0, y - hb, x1, y + 0.085, layer=D.LI)
    if name:
        D.label(c, name, x0 + 0.1 if lx is None else lx, y)


def li_riser(c, x, y0, y1):
    """A 0.17-wide li riser (used to pull a source/drain li column to a strap)."""
    D.strap(c, x - 0.085, min(y0, y1), x + 0.085, max(y0, y1), layer=D.LI)


def li_col_top(y0, W):
    """Top y of the li cover over a source/drain licon column. This is NOT
    y0 + W: `device.fet` stacks studs on a 0.34 pitch and stops at the last one
    that fits, so the cover ends somewhere in the last 0.34 um. Eyeballing it as
    `y0 + W - 0.3` overlaps at most widths but MISSES BY 0.01 um at W = 20 --
    which DRC reports as an li.3 spacing violation and which would have been a
    silently open source connection had the gap been a hair wider. Compute it."""
    y, top, last = y0 + D.LICON_ENC, y0 + W - D.LICON_ENC, None
    while y + D.LICON_SZ <= top + 1e-6:
        last = y + D.LICON_SZ
        y += D.LICON_SZ + D.LICON_SP
    return last + D.LI_ENC


# ------------------------------------------------------------ the blocks ----
def build_rrf2_nin():
    """rrf2_nin -- the NMOS high-side input: the tail mirror (xmb diode + xm0)
    under the common-centroid input pair (xm1/xm2), tail internal.

    This is miller_ota's ota5t_core minus its PMOS mirror load: in rrf2 the pair
    does not drive a mirror at all, it drives the FOLD nodes fa/fb, which is the
    whole point of the topology (unpinning the input drains is what removes the
    1.40 V ICMR wall). Sizing from spice/miller_rrf2.sp: xmb/xm0 = W20 L1 (m4),
    xm1/xm2 = W40 L0.5 (m8), i.e. the same devices as the miller_ota core, so
    the proven strip geometry carries over unchanged and only the escape of the
    pair drains differs (fa/fb both leave upward instead of folding into a load).

    fa = device A (gates g0/g3) = the OUTER drain columns, on met1;
    fb = device B (gates g1/g2) = the CENTRE column, on li, passing under the
    fa bridge. VINN sits on A and VINP on B, matching the .sp pin order."""
    c = gdstk.Cell("rrf2_nin")
    XC = 6.0
    WT, WI = 10.0, 20.0                            # finger W -> devices W20/W40

    # ---- tail mirror: NMOS L=1 nf=4 (W=20 each), xmb diode + xm0 -----------
    x0T, y0T = XC - 2.725, 2.0
    T = D.fet(c, x0T, y0T, W=WT, L=1.0, nf=4, kind="n")
    tcol, tg = T["sds"], T["gates"]
    topT = y0T + WT
    rail_vss, vb_y = 0.6, 1.4
    for x in (tcol[1], tcol[3]):                   # sources -> VSS rail (met1)
        met1_drop(c, x, y0T, WT, rail_vss)
    m1bar(c, [tcol[1], tcol[3]], rail_vss, "VSS")
    for x in tg:                                   # vb: gates down, li
        D.poly_contact_dn(c, x, 1.0, y0T - 0.13, down=(y0T - 0.13) - vb_y)
    for x in (tcol[0], tcol[4]):                   # + the diode drains
        li_riser(c, x, vb_y, y0T)
    # the strap runs well past the strip on the left: the top level lands a via
    # pad on it, and the pad is taller than the strap, so it needs to sit clear
    # of the diode-drain riser rather than beside it.
    libar(c, x0T - 0.9, tcol[4] + 0.085, vb_y, "VB", lx=x0T - 0.8)
    tail_bar = topT + 2.3
    met1_drop(c, tcol[2], y0T, WT, tail_bar)       # xm0 drain -> tail

    # ---- input pair: NMOS L=0.5 nf=4 (W=40 each), xm1/xm2 ------------------
    x0I, y0I = XC - 1.725, topT + 5.0
    I = D.fet(c, x0I, y0I, W=WI, L=0.5, nf=4, kind="n")
    icol, ig = I["sds"], I["gates"]
    itop, ibot = y0I + WI, y0I - 0.13
    for x in (icol[1], icol[3]):                   # pair sources -> tail bar
        met1_drop(c, x, y0I, WI, tail_bar)
    m1bar(c, [min(icol[1], tcol[2]), max(icol[3], tcol[2])], tail_bar)
    vinn_y, vinp_y = y0I - 0.8, y0I - 1.5          # gates escape downward on li
    for x in (ig[0], ig[3]):                                    # VINN -> fa
        D.poly_contact_dn(c, x, 0.5, ibot, down=ibot - vinn_y)
    libar(c, x0I - 0.95, ig[3] + 0.165, vinn_y, "VINN", lx=x0I - 0.85)
    for x in (ig[1], ig[2]):                                    # VINP -> fb
        D.poly_contact_dn(c, x, 0.5, ibot, down=ibot - vinp_y)
    libar(c, ig[1] - 0.165, x0I + I["totx"] + 0.95, vinp_y, "VINP",
          lx=x0I + I["totx"] + 0.85)
    fa_bar, fb_y = itop + 2.0, itop + 3.6
    for x in (icol[0], icol[4]):                   # fa: outer drains, met1
        met1_drop(c, x, y0I, WI, fa_bar)
    m1bar(c, [icol[0], icol[4]], fa_bar, "FA")
    li_riser(c, icol[2], li_col_top(y0I, WI) - 0.2, fb_y + 0.085)  # fb: centre drain, li
    D.label(c, "FB", icol[2], fb_y)
    _write(c)


def build_rrf2_cmir():
    """rrf2_cmir -- the self-biased cascode current mirror (xm13/xm14 mirror,
    xm15/xm16 cascode) that is THE fix of miller_rrf2: it holds the folded
    path's output impedance high so it stops shunting the summing node cb at low
    V_CM (docs/input-stage.md). yref and cbm are internal.

    xm13/xm14 share gate AND source, so they are drawn common-centroid (the
    matching that sets the mirror ratio). xm15/xm16 share only their gate --
    their sources are yref and cbm, two different nets -- so a common-centroid
    interleave is impossible (the shared columns of an A-B-B-A strip must be one
    net) and they are drawn as two separate 2-finger devices, one over each
    mirror leg. That is the natural stacked-cascode floorplan anyway.

    Levels, bottom-up: VSS rail (met1) / mirror strip / yref strap (li) / cbm
    bridge (met1) / cascode devices / ca gate strap (li) / ca+cb pads (met1)."""
    c = gdstk.Cell("rrf2_cmir")
    XC, WM, WC = 6.0, 10.0, 10.0                   # finger W -> W20 everywhere

    # ---- mirror: NMOS L=0.5 nf=4 (W=20 each), xm13 diode + xm14 -----------
    x0M, y0M = XC - 1.725, 2.0
    M = D.fet(c, x0M, y0M, W=WM, L=0.5, nf=4, kind="n")
    mcol, mg = M["sds"], M["gates"]
    topM = y0M + WM
    rail_vss = 0.6
    for x in (mcol[1], mcol[3]):
        met1_drop(c, x, y0M, WM, rail_vss)
    m1bar(c, [mcol[1], mcol[3]], rail_vss, "VSS")

    # ---- cascode devices: two separate NMOS L=0.5 nf=2 (W=20 each) --------
    y0C = 16.5
    A = D.fet(c, XC - 4.0, y0C, W=WC, L=0.5, nf=2, kind="n")   # xm15 (ref leg)
    B = D.fet(c, XC + 2.13, y0C, W=WC, L=0.5, nf=2, kind="n")  # xm16 (out leg)
    acol, ag = A["sds"], A["gates"]
    bcol, bg = B["sds"], B["gates"]
    topC = y0C + WC

    # yref (li): mirror gates + mirror outer drains + xm15's source columns.
    # The strap runs left far enough to pick up xm15, which sits left of the
    # mirror strip; xm15's other source column lands on it from directly above.
    yref_y = topM + 0.13 + 0.5
    for x in mg:
        D.poly_contact(c, x, 0.5, topM + 0.13, up=0.5)
    for x in (mcol[0], mcol[4]):
        li_riser(c, x, li_col_top(y0M, WM) - 0.2, yref_y + 0.085)
    for x in (acol[0], acol[2]):                   # xm15 sources come DOWN
        li_riser(c, x, yref_y, y0C + 0.25)
    libar(c, min(acol[0], mcol[0]) - 0.085, mcol[4] + 0.085, yref_y, hb=0.165)

    # cbm (met1): mirror centre drain bridged right to xm16's source columns.
    # It crosses the yref li strap and xm15's li risers -- different layer.
    cbm_y = 14.5
    met1_drop(c, mcol[2], y0M, WM, cbm_y)
    for x in (bcol[0], bcol[2]):
        met1_drop(c, x, y0C, WC, cbm_y)
    m1bar(c, [mcol[2], bcol[2]], cbm_y)

    # ca (li strap over both cascode gates, tied up to the xm15 drain on met1)
    ca_y = topC + 0.13 + 0.55
    for x in ag + bg:
        D.poly_contact(c, x, 0.5, topC + 0.13, up=0.55)
    libar(c, ag[0] - 0.165, bg[1] + 0.165, ca_y)
    pad_y = topC + 3.0
    met1_drop(c, acol[1], y0C, WC, pad_y)          # xm15 drain = ca (diode)
    D.via(c, acol[1], ca_y)                        # ...tie it to the gate strap
    D.label(c, "CA", acol[1], pad_y, layer=D.MET1LBL)
    m1bar(c, [acol[1]], pad_y)
    met1_drop(c, bcol[1], y0C, WC, pad_y)          # xm16 drain = cb (crosses
    m1bar(c, [bcol[1]], pad_y)                     # the ca strap, no via)
    D.label(c, "CB", bcol[1], pad_y, layer=D.MET1LBL)
    _write(c)


def build_rrf2_bias_n():
    """rrf2_bias_n -- the NMOS half of the bias chain: xbn1/xbn3 (the two W5 legs
    that mirror the master vb into the pb and vbp branches) and xbn2 (the W20
    diode that turns the pb current into the cascode reference pc).

    xbn1/xbn3 share gate (vb) and source (vss), so they interleave A-B-B-A: pb
    is the outer drain (met1), vbp the centre one (li). xbn2 is a plain 4-finger
    diode -- odd columns are its drain, even columns its source -- with gates and
    drain merged on one strap above.

    The PMOS half is a separate cell (rrf2_bias_p) on purpose: pb, pc and vbp are
    top-level nets anyway (they feed the fold and the low-side path), so splitting
    the chain at those nets keeps four signals out of a two-layer channel that
    can only carry two."""
    c = gdstk.Cell("rrf2_bias_n")
    rail_vss = 0.6

    # ---- xbn1 / xbn3: common gate vb, common source vss, drains pb / vbp ---
    x0A, y0A, WA = 2.0, 2.0, 2.5                   # finger W -> W5 devices
    A = D.fet(c, x0A, y0A, W=WA, L=1.0, nf=4, kind="n")
    acol, ag = A["sds"], A["gates"]
    vb_y = 1.4
    for x in (acol[1], acol[3]):
        met1_drop(c, x, y0A, WA, rail_vss)
    for x in ag:                                   # vb gates escape down on li
        D.poly_contact_dn(c, x, 1.0, y0A - 0.13, down=(y0A - 0.13) - vb_y)
    libar(c, x0A - 0.8, ag[3] + 0.165, vb_y, "VB", lx=x0A - 0.7)
    pb_bar = y0A + WA + 2.0
    for x in (acol[0], acol[4]):                   # pb = outer drains (met1)
        met1_drop(c, x, y0A, WA, pb_bar)
    m1bar(c, [acol[0], acol[4]], pb_bar, "PB")
    vbp_y = y0A + WA + 3.1                         # vbp = centre drain (li)
    li_riser(c, acol[2], li_col_top(y0A, WA) - 0.2, vbp_y + 0.085)
    D.label(c, "VBP", acol[2], vbp_y)

    # ---- xbn2: the pc diode (W20). Gates + odd (drain) columns on one strap -
    x0B, y0B, WB = 10.0, 2.0, 5.0                  # finger W -> W20 device
    B = D.fet(c, x0B, y0B, W=WB, L=1.0, nf=4, kind="n")
    bcol, bg = B["sds"], B["gates"]
    topB = y0B + WB
    for x in (bcol[0], bcol[2], bcol[4]):          # even columns = source
        met1_drop(c, x, y0B, WB, rail_vss)
    pc_y = topB + 0.13 + 0.5
    for x in bg:
        D.poly_contact(c, x, 1.0, topB + 0.13, up=0.5)
    libar(c, bg[0] - 0.165, bg[3] + 0.165, pc_y)
    for x in (bcol[1], bcol[3]):                   # odd columns = drain = pc
        met1_drop(c, x, y0B, WB, pc_y)
        D.via(c, x, pc_y)                          # ...merged with the gates
    m1bar(c, [bcol[1], bcol[3]], pc_y, "PC")

    m1bar(c, [acol[1], bcol[4]], rail_vss, "VSS")  # one VSS rail under both
    _write(c)


def build_rrf2_bias_p():
    """rrf2_bias_p -- the PMOS half of the bias chain: the xbp1/xbp2 mirror that
    turns the pb leg current into the fold's top-source bias, and the xbp3 diode
    that makes vbp for the PMOS tail of the low-side path.

    xbp1/xbp2 share gate (pb) and source (vdd) -> common-centroid, with the diode
    node pb on the outer columns + gates (li, below) and pc on the centre column
    (met1, below, crossing under). xbp3 is a plain 4-finger diode like xbn2 but
    escaping downward. One nwell covers both groups -- they are both at vdd, so
    merging avoids an nwell-to-nwell spacing gap between them."""
    c = gdstk.Cell("rrf2_bias_p")
    rail_vdd = 9.5

    # ---- xbp1 / xbp2: PMOS mirror, diode node pb, output pc ---------------
    x0A, y0A, WA = 2.0, 2.0, 5.0                   # finger W -> W10 devices
    A = D.fet(c, x0A, y0A, W=WA, L=1.0, nf=4, kind="p")
    acol, ag = A["sds"], A["gates"]
    pb_y = 1.4
    for x in (acol[1], acol[3]):                   # sources -> VDD rail
        met1_drop(c, x, y0A, WA, rail_vdd)
    for x in ag:                                   # pb: gates + outer drains
        D.poly_contact_dn(c, x, 1.0, y0A - 0.13, down=(y0A - 0.13) - pb_y)
    for x in (acol[0], acol[4]):
        li_riser(c, x, pb_y, y0A)
    libar(c, x0A - 0.8, acol[4] + 0.085, pb_y, "PB", lx=x0A - 0.7)
    pc_y = 0.6                                     # pc: centre drain on met1
    met1_drop(c, acol[2], y0A, WA, pc_y)
    m1bar(c, [acol[2]], pc_y, "PC")

    # ---- xbp3: the vbp diode (W10) ---------------------------------------
    x0B, y0B, WB = 10.0, 2.0, 2.5
    B = D.fet(c, x0B, y0B, W=WB, L=1.0, nf=4, kind="p")
    bcol, bg = B["sds"], B["gates"]
    for x in (bcol[0], bcol[2], bcol[4]):          # even columns = source
        met1_drop(c, x, y0B, WB, rail_vdd)
    vbp_y = 1.4
    for x in bg:
        D.poly_contact_dn(c, x, 1.0, y0B - 0.13, down=(y0B - 0.13) - vbp_y)
    libar(c, bg[0] - 0.165, bg[3] + 0.165, vbp_y)
    for x in (bcol[1], bcol[3]):                   # odd columns = drain = vbp
        met1_drop(c, x, y0B, WB, vbp_y)
        D.via(c, x, vbp_y)
    m1bar(c, [bcol[1], bcol[3]], vbp_y, "VBP")

    m1bar(c, [acol[1], bcol[4]], rail_vdd, "VDD")  # one VDD rail over both
    D._r(c, D.NWELL, 1.6, 1.55, 15.85, 7.4)        # merged well (both at vdd)
    D.label(c, "VNW", 8.7, 7.1)
    _write(c)


def build_rrf2_fold():
    """rrf2_fold -- the PMOS half of the folded high-side path: the top current
    sources xm9/xm10 that feed the fold nodes fa/fb, and the cascodes xm11/xm12
    that carry the folded signal current down to the summing nodes ca/cb.

    xm9/xm10 share gate (pb) and source (vdd) -> common-centroid, fa on the outer
    columns (met1) and fb on the centre one (li). xm11/xm12 share ONLY their gate
    -- their sources are fa and fb -- so they cannot interleave (an A-B-B-A strip
    forces its shared columns onto one net) and are drawn as two separate
    2-finger devices, one under each fold node.

    The fold nodes are what makes the whole topology work: the NMOS input drains
    land here at ~VDD-|Vdsat| instead of being pinned to ~0.9 V by a diode mirror,
    which is why the 1.40 V ICMR wall disappears. They are ports as well as
    internal nets -- rrf2_nin's pair drains join them at the top level.

    Levels, bottom-up: ca/cb pads (met1) / pc gate strap (li) / cascodes /
    fb bridge (li) / fa bridge (met1) / source strip / pb gate strap (li) /
    VDD rail. fa runs on met1 and fb on li precisely so the fa bridge can cross
    the fb riser, and the cascode sources then tap whichever layer their node is
    on -- xm11 upward on met1, xm12 upward on li."""
    c = gdstk.Cell("rrf2_fold")
    XC = 6.0

    # ---- cascodes: two separate PMOS L=0.5 nf=2 (W=40 each) ---------------
    y0C, WC = 2.0, 20.0
    A = D.fet(c, 2.0, y0C, W=WC, L=0.5, nf=2, kind="p")     # xm11 (ca leg)
    B = D.fet(c, 9.0, y0C, W=WC, L=0.5, nf=2, kind="p")     # xm12 (cb leg)
    acol, ag = A["sds"], A["gates"]
    bcol, bg = B["sds"], B["gates"]
    topC = y0C + WC
    pc_y, out_y = 1.4, 0.5
    for x in ag + bg:                              # pc: common gate, down on li
        D.poly_contact_dn(c, x, 0.5, y0C - 0.13, down=(y0C - 0.13) - pc_y)
    libar(c, ag[0] - 0.165, bg[1] + 0.165, pc_y, "PC", lx=ag[0] - 0.05)
    for x, nm in ((acol[1], "CA"), (bcol[1], "CB")):        # drains down on met1
        met1_drop(c, x, y0C, WC, out_y)            # (crossing the pc strap)
        m1bar(c, [x], out_y, nm)

    # ---- fold-node bridges: fa on met1, fb on li -------------------------
    fb_y, fa_bar = 24.0, 25.5
    for x in (acol[0], acol[2]):                   # xm11 sources -> fa (met1)
        met1_drop(c, x, y0C, WC, fa_bar)
    for x in (bcol[0], bcol[2]):                   # xm12 sources -> fb (li)
        li_riser(c, x, li_col_top(y0C, WC) - 0.2, fb_y - 0.085)

    # ---- top current sources: PMOS L=1 nf=4 (W=30 each), xm9/xm10 --------
    x0U, y0U, WU = XC - 2.725, 28.0, 15.0
    U = D.fet(c, x0U, y0U, W=WU, L=1.0, nf=4, kind="p")
    ucol, ug = U["sds"], U["gates"]
    topU = y0U + WU
    rail_vdd = 46.0
    for x in (ucol[1], ucol[3]):                   # sources -> VDD rail
        met1_drop(c, x, y0U, WU, rail_vdd)
    m1bar(c, [ucol[1], ucol[3]], rail_vdd, "VDD")
    pb_y = topU + 0.13 + 0.5                       # pb: gates up on li
    for x in ug:
        D.poly_contact(c, x, 1.0, topU + 0.13, up=0.5)
    libar(c, x0U - 0.6, ug[3] + 0.165, pb_y, "PB", lx=x0U - 0.5)
    for x in (ucol[0], ucol[4]):                   # fa = outer drains (met1)
        met1_drop(c, x, y0U, WU, fa_bar)
    m1bar(c, [acol[0], ucol[4]], fa_bar, "FA")
    li_riser(c, ucol[2], fb_y - 0.085, y0U)        # fb = centre drain (li)
    libar(c, ucol[2] - 0.085, bcol[2] + 0.085, fb_y, "FB", lx=ucol[2])

    D._r(c, D.NWELL, 1.7, 1.7, 11.15, 43.3)        # merged well (all at vdd)
    D.label(c, "VNW", 10.5, 26.5)      # clear of the fb riser at x = ucol[2]
    _write(c)


def build_rrf2_plow():
    """rrf2_plow -- the PMOS low-side path: tail xmp0, the PMOS input pair
    xmp1/xmp2, and their NMOS mirror load xmp3/xmp4. tailp and nP are internal;
    the pair's output joins the summing node cb.

    This is the half that covers the LOW end of the common-mode range (an NMOS
    pair starves there), and it is the half the margin-tuning pass scaled 1.5x --
    tail and pair m12, mirror m6 -- because the trough gain, ~15 dB under the
    peak, was what pushed the temperature corners over 0.1 %. So the sizing here
    is deliberately asymmetric with the high side: W60/W60/W30, not W40/W20.

    The gates escape UPWARD, which is the one non-obvious choice in the cell. The
    gap between the pair and the mirror has to carry nP and cb, and a common-
    centroid strip forces nP onto the outer columns (a bridge across the middle)
    and cb onto the centre one -- so that gap is exactly full at two layers. Any
    gate strap routed down there would have to span the centre too, and would
    short one of them: VINN bridges g0 to g3, so it cannot avoid the middle."""
    c = gdstk.Cell("rrf2_plow")
    XC = 6.0
    rail_vss = 0.6

    # ---- mirror load: NMOS L=1 nf=4 (W=30 each), xmp3 diode + xmp4 --------
    x0N, y0N, WN = XC - 2.725, 2.0, 15.0
    N = D.fet(c, x0N, y0N, W=WN, L=1.0, nf=4, kind="n")
    ncol, ng = N["sds"], N["gates"]
    topN = y0N + WN
    for x in (ncol[1], ncol[3]):
        met1_drop(c, x, y0N, WN, rail_vss)
    m1bar(c, [ncol[1], ncol[3]], rail_vss, "VSS")
    np_bar = topN + 0.63                           # nP: mirror gates + outer
    for x in ng:                                   # drains, on met1 so the
        _gx, yc = D.poly_contact(c, x, 1.0, topN + 0.13, up=0.5)   # bridge can
        D.via(c, x, yc)                            # cross the cb li riser
    for x in (ncol[0], ncol[4]):
        met1_drop(c, x, y0N, WN, np_bar)

    # ---- input pair: PMOS L=0.5 nf=4 (W=60 each), xmp1/xmp2 --------------
    x0P, y0P, WP = XC - 1.725, 21.0, 30.0
    P = D.fet(c, x0P, y0P, W=WP, L=0.5, nf=4, kind="p")
    pcol, pg = P["sds"], P["gates"]
    topP = y0P + WP
    for x in (pcol[0], pcol[4]):                   # nP = outer drains, down
        met1_drop(c, x, y0P, WP, np_bar)
    m1bar(c, [min(ncol[0], pcol[0]), max(ncol[4], pcol[4])], np_bar)
    li_riser(c, pcol[2], li_col_top(y0N, WN) - 0.2, y0P + 0.3)    # cb = centre drains, li
    D.label(c, "CB", pcol[2], 19.0)
    tailp_bar = topP + 2.5
    for x in (pcol[1], pcol[3]):                   # pair sources -> tailp
        met1_drop(c, x, y0P, WP, tailp_bar)
    vinp_y = topP + 0.13 + 0.55                    # gates escape UP, two levels
    vinn_y = topP + 0.13 + 1.35
    # Both straps run PAST the strip -- VINP to the right, VINN to the left --
    # so the top level has somewhere to land a met1 via pad. Inside the strip
    # the only clear window is between the two source risers, and cb already
    # occupies it (it leaves on the centre column).
    for x in (pg[1], pg[2]):                                    # VINP -> cb
        D.poly_contact(c, x, 0.5, topP + 0.13, up=0.55)
    libar(c, pg[1] - 0.165, x0P + P["totx"] + 0.95, vinp_y, "VINP", lx=pg[1])
    for x in (pg[0], pg[3]):                                    # VINN -> nP
        D.poly_contact(c, x, 0.5, topP + 0.13, up=1.35)
    libar(c, x0P - 0.95, pg[3] + 0.165, vinn_y, "VINN", lx=pg[0])

    # ---- tail: PMOS L=1 nf=4 (W=60), xmp0 --------------------------------
    x0T, y0T, WT = XC - 2.725, 56.0, 15.0
    T = D.fet(c, x0T, y0T, W=WT, L=1.0, nf=4, kind="p")
    tcol, tg = T["sds"], T["gates"]
    topT = y0T + WT
    rail_vdd = 74.0
    for x in (tcol[0], tcol[2], tcol[4]):          # even columns = source
        met1_drop(c, x, y0T, WT, rail_vdd)
    m1bar(c, [tcol[0], tcol[4]], rail_vdd, "VDD")
    for x in (tcol[1], tcol[3]):                   # odd columns = drain = tailp
        met1_drop(c, x, y0T, WT, tailp_bar)
    m1bar(c, [min(pcol[1], tcol[1]), max(pcol[3], tcol[3])], tailp_bar)
    vbp_y = topT + 0.13 + 0.5
    for x in tg:
        D.poly_contact(c, x, 1.0, topT + 0.13, up=0.5)
    libar(c, x0T - 0.6, tg[3] + 0.165, vbp_y, "VBP", lx=x0T - 0.5)

    # merged nwell over both PMOS groups (both at vdd); it stays 3.7 um clear of
    # the NMOS mirror's diffusion below, and is wide enough to the left of the
    # pair to host the top level's n-tap with the 0.18 um nwell enclosure.
    D._r(c, D.NWELL, XC - 3.4, 20.7, XC + 3.4, 71.3)
    D.label(c, "VNW", XC, 53.0)
    _write(c)


def build_cap_cc9():
    """cap_cc9 -- the 9 pF MIM compensation cap. Same construction as the
    miller_ota leg's cap_cc (met3 bottom plate, capm top plate, via3 up to a met4
    pad) at the value miller_rrf2 actually runs: the margin-tuning pass took Cc
    from 8 p to 9 p to hold PM >= 73 deg once the PMOS low-side path was scaled
    1.5x. cap_mim is ~2 fF/um^2, so 9 pF wants 4500 um^2 -> a 67.08 um square."""
    c = gdstk.Cell("cap_cc9")
    side = 67.08                    # 4499.7 um^2 * 2 fF/um^2 = 8.999 pF
    # (67.08, not the exact 67.0820: every drawn coordinate must land on the
    # sky130 5 nm grid, and side/2 feeds the via3/met4 stack -- so the side has
    # to be a multiple of 0.01. The 0.006 % value error is far inside tolerance.)
    xc = 2.0 + side / 2
    D._r(c, D.CAPM, 2.0, 2.0, 2.0 + side, 2.0 + side)
    D._r(c, D.MET3, 0.5, 1.8, 2.2 + side, 2.2 + side)
    D.label(c, "P1", 1.15, xc, layer=D.MET3LBL)
    D._r(c, D.VIA3, xc - 0.1, xc - 0.1, xc + 0.1, xc + 0.1)
    D._r(c, D.MET4, xc - 0.6, xc - 0.6, xc + 0.6, xc + 0.6)
    D.label(c, "P2", xc, xc, layer=D.MET4LBL)
    _write(c)


# ------------------------------------------------- the assembled amplifier ----
# Floorplan: the seven device blocks in one row, left to right in signal order
# (bias chain, NMOS input, fold, cascode mirror, PMOS low side, output stage),
# then the compensation branch. The blocks' x-ranges are DISJOINT, which is what
# makes the channel router below safe: every block's vertical risers live inside
# its own x-window, so risers from different blocks can never collide.
PLACE = {
    "rrf2_bias_n": (0.0, 0.0),
    "rrf2_bias_p": (18.0, 0.0),
    "rrf2_nin": (37.0, 0.0),
    "rrf2_fold": (49.0, 0.0),
    "rrf2_cmir": (63.0, 0.0),
    "rrf2_plow": (75.0, 0.0),
    "out_stage": (87.0, 0.0),
    "res_rz": (105.0, 50.0),
    "cap_cc9": (109.0, 0.0),
}

# One horizontal met3 track per net; each pin reaches its track on a vertical
# met2 riser. Two layers, one direction each, so a riser and a track never share
# a layer and the whole channel is short-free by construction.
#
# TRACK HEIGHT IS NOT ARBITRARY, and the first version got it wrong. The bias,
# input and rail nets sit in a channel ABOVE every block (y >= 80). The four
# SIGNAL-PATH nets do not: they run low, down among the blocks they connect.
#
# Why the split: tb/parasitics_rrf2.py measured what the interconnect costs, and
# the answer is entirely lopsided. 193 fF spread over the eight bias/input nets
# costs 0.00 deg of phase margin -- they are diode-connected or driven, so they
# sit at 1/gm and do not care. 103 fF on cb/ca/fa/fb costs 3.15 deg, which was
# enough to push the worst-corner phase margin UNDER the 60 deg spec. cb alone
# is 62 % of it, because Rz sits in SERIES with Cc: above 1/(2*pi*Rz*Cc) = 1.8 MHz
# the Miller branch is just a 10 kohm resistor and stops shunting the summing
# node, so a parasitic there is fully exposed at the ~18 MHz UGF.
#
# And the wires were long for a reason that turned out to be a habit: the channel
# floor was placed above the TALLEST block (rrf2_plow, ~74 um), so all 37 pins
# climbed ~67 um whether they needed to or not. But met3 is free over every block
# -- the blocks only use li/met1 -- so a track never had to clear anything. The
# four nets that matter connect ADJACENT blocks, so their tracks now sit beside
# their own pins and their risers are a few um instead of tens.
#
# The eight that cost nothing are deliberately left where they were: moving
# verified geometry to buy capacitance that provably does not matter would be
# rework for its own sake.
TRACK = {"VSS": 80.0, "VDD": 81.5, "VB": 83.0, "PB": 84.5, "PC": 86.0,
         "VBP": 87.5, "VINN": 95.0, "VINP": 96.5,
         # --- signal path: low, among the blocks (see above) ---
         "CA": 16.0,     # pins at y 0.5 (fold) and 29.5 (cmir)
         "FA": 31.5,     # pins at y 39.0 (nin) and 25.5 (fold)
         "CB": 33.0,     # pins at y 0.5 / 19.0 / 29.5 / 37.68 / 50.3
         "FB": 34.5}     # pins at y 40.6 (nin) and 24.0 (fold)

# (net, block, local x, local y, pin layer, tag). The local x of each tap is
# picked to clear the block's own met1 by >= 0.14 (a via pad is 0.32 wide) and
# to keep every riser in a block >= 0.5 from its neighbours. `tag` becomes a
# unique top-level label on the riser, which is what makes the extraction check
# in run_rrf2_extract.py meaningful: the sub-cells all call this net "CB", so
# only distinct per-pin names can prove they actually merged.
TAPS = [
    ("VB",   "rrf2_bias_n",  1.300,  1.40, "li", "vb_bias"),
    ("PB",   "rrf2_bias_n",  3.000,  6.50, "m1", "pb_biasn"),
    ("VBP",  "rrf2_bias_n",  4.725,  7.60, "li", "vbp_biasn"),
    ("VSS",  "rrf2_bias_n",  9.000,  0.60, "m1", "vss_biasn"),
    ("PC",   "rrf2_bias_n", 12.500,  7.63, "m1", "pc_biasn"),

    ("PB",   "rrf2_bias_p",  1.300,  1.40, "li", "pb_biasp"),
    ("PC",   "rrf2_bias_p",  4.725,  0.60, "m1", "pc_biasp"),
    ("VDD",  "rrf2_bias_p",  9.000,  9.50, "m1", "vdd_biasp"),
    ("VBP",  "rrf2_bias_p", 12.500,  1.40, "m1", "vbp_biasp"),

    ("VB",   "rrf2_nin",     2.600,  1.40, "li", "vb_nin"),
    ("VINN", "rrf2_nin",     4.500, 16.20, "li", "vinn_nin"),
    ("FA",   "rrf2_nin",     5.300, 39.00, "m1", "fa_nin"),
    ("FB",   "rrf2_nin",     6.000, 40.60, "li", "fb_nin"),
    ("VSS",  "rrf2_nin",     7.200,  0.60, "m1", "vss_nin"),
    ("VINP", "rrf2_nin",     8.575, 15.50, "li", "vinp_nin"),

    ("CA",   "rrf2_fold",    2.935,  0.50, "m1", "ca_fold"),
    ("PB",   "rrf2_fold",    4.000, 43.63, "li", "pb_fold"),
    ("FA",   "rrf2_fold",    4.600, 25.50, "m1", "fa_fold"),
    ("VDD",  "rrf2_fold",    5.300,  8.50, "li", "vdd_nwfold"),   # n-tap below
    ("PC",   "rrf2_fold",    6.000,  1.40, "li", "pc_fold"),
    ("VDD",  "rrf2_fold",    6.800, 46.00, "m1", "vdd_fold"),
    ("FB",   "rrf2_fold",    7.500, 24.00, "li", "fb_fold"),
    ("CB",   "rrf2_fold",    9.935,  0.50, "m1", "cb_fold"),

    ("CA",   "rrf2_cmir",    2.935, 29.50, "m1", "ca_cmir"),
    ("VSS",  "rrf2_cmir",    6.000,  0.60, "m1", "vss_cmir"),
    ("CB",   "rrf2_cmir",    9.065, 29.50, "m1", "cb_cmir"),

    ("VBP",  "rrf2_plow",    2.800, 71.63, "li", "vbp_plow"),
    ("VDD",  "rrf2_plow",    3.500, 35.00, "li", "vdd_nwplow"),   # n-tap below
    ("VINN", "rrf2_plow",    4.200, 52.48, "li", "vinn_plow"),
    ("VDD",  "rrf2_plow",    5.000, 74.00, "m1", "vdd_plow"),
    ("CB",   "rrf2_plow",    6.000, 19.00, "li", "cb_plow"),
    ("VSS",  "rrf2_plow",    7.000,  0.60, "m1", "vss_plow"),
    ("VINP", "rrf2_plow",    7.800, 51.68, "li", "vinp_plow"),

    ("VB",   "out_stage",    1.800,  1.30, "li", "vb_out"),
    ("VSS",  "out_stage",    8.000,  0.60, "m1", "vss_out"),
    ("VDD",  "out_stage",    8.600, 39.00, "m1", "vdd_out"),
    ("CB",   "out_stage",   11.600, 37.68, "li", "cb_out"),       # = stage-2 gate
]


def _abs(block, x, y):
    dx, dy = PLACE[block]
    return x + dx, y + dy


def _m2(top, x0, y0, x1, y1):
    D.strap(top, min(x0, x1) - 0.16, min(y0, y1) - 0.16,
            max(x0, x1) + 0.16, max(y0, y1) + 0.16, D.MET2)


def _check_risers():
    """Guard the one failure mode this floorplan can still have: two met2 risers
    too close together. They are only ever in danger inside a single block (the
    blocks' x-windows are disjoint), so check there, and separately check the
    met3 landing pads of risers that share a track."""
    for block in PLACE:
        xs = sorted(x for (_n, b, x, _y, _k, _t) in TAPS if b == block)
        for a, b in zip(xs, xs[1:]):
            assert b - a >= 0.5, f"{block}: risers {a} and {b} too close"
    for net, ty in TRACK.items():
        xs = sorted(_abs(b, x, 0)[0] for (n, b, x, _y, _k, _t) in TAPS
                    if n == net)
        for a, b in zip(xs, xs[1:]):
            assert b - a >= 0.7, f"{net} track {ty}: met3 pads {a}/{b} too close"


def build_miller_rrf2():
    """miller_rrf2 -- the whole amplifier, assembled and routed.

    Stage 1 is the folded rail-to-rail input summed at cb through a self-biased
    cascode mirror; stage 2 and the compensation branch are miller_ota's, reused
    unchanged: rrf2 runs the same pout=2.5 output devices and the same 10 k
    nulling resistor, and only the cap changes (9 p, so cap_cc9).

    Routing is a two-layer channel: one met3 track per net above the blocks, one
    met2 riser per pin. li and met1 stay inside the blocks, so met2 can cross any
    block freely and met3 can cross any riser freely. The compensation branch is
    the exception -- it climbs met2 -> met3 -> met4 to reach the MIM plates, the
    same way miller_ota's does, and vout takes its long run to the cap on met3
    (not met2) because the out_stage rail risers already occupy met2 there."""
    _check_risers()
    top = gdstk.Cell("miller_rrf2")
    pins = {}
    for name, (dx, dy) in PLACE.items():
        sub = gdstk.read_gds(str(OUT / f"{name}.gds")).cells[0]
        top.add(gdstk.Reference(sub, (dx, dy)))
        pins[name] = {l.text: (l.origin[0] + dx, l.origin[1] + dy)
                      for l in sub.labels}

    # ---- body ties -------------------------------------------------------
    # substrate: one p-tap in the gap between the input and the fold, bridged on
    # met1 to rrf2_nin's VSS rail (which the channel then carries everywhere).
    D.tap(top, 47.6, 1.0, 48.4, 1.9, kind="p")
    D.via(top, 48.0, 1.45)
    D.strap(top, 47.86, 0.60, 48.14, 1.55, layer=D.MET1)
    D.strap(top, 44.29, 0.45, 48.14, 0.75, layer=D.MET1)
    D.label(top, "vss_tap", 48.0, 1.9)
    # nwells. bias_p and out_stage reach their VDD rail directly on met1; fold
    # and plow have no clear met1 path to their rail, so their taps ride the
    # channel instead (their TAPS rows above).
    D.tap(top, 26.2, 2.5, 26.8, 6.5, kind="n")            # inside bias_p's well
    D.via(top, 26.5, 4.5)
    D.strap(top, 26.36, 4.5, 26.64, 9.5, layer=D.MET1)
    D.label(top, "nw_biasp", 26.5, 4.5)          # ON the tap li, not beside it
    D.tap(top, 53.9, 5.0, 54.7, 12.0, kind="n")           # inside fold's well
    D.tap(top, 78.15, 25.0, 78.85, 45.0, kind="n")        # inside plow's well
    D._r(top, D.NWELL, 98.0, 22.0, 100.4, 37.2)           # widen out_stage's
    D.tap(top, 99.2, 26.0, 99.9, 33.0, kind="n")
    D.via(top, 99.55, 29.5)
    D.strap(top, 99.41, 29.5, 99.69, 39.0, layer=D.MET1)
    D.strap(top, 98.00, 38.85, 99.69, 39.15, layer=D.MET1)
    D.label(top, "nw_out", 99.55, 29.5)          # ON the tap li, not beside it

    # ---- the channel: a met2 riser per pin, a met3 track per net ---------
    for net, block, lx, ly, kind, tag in TAPS:
        x, y = _abs(block, lx, ly)
        if kind == "li":
            D.via_li_met2(top, x, y)
        else:
            D.via2(top, x, y)
        ty = TRACK[net]
        _m2(top, x, y, x, ty)
        D.via_met2_met3(top, x, ty)
        # Label at the riser's MIDPOINT, not a fixed offset below the track.
        # Now that the signal-path tracks sit low, several pins are ABOVE their
        # track and the riser runs downward -- `ty - 0.8` would land past the end
        # of it, on nothing. A label that misses its shape does not fail; it
        # quietly weakens the extraction assertion it exists to make (this leg
        # has already been bitten once, by two nwell-tap labels).
        D.label(top, tag, x, (y + ty) / 2.0, layer=D.MET2LBL)
    for net, ty in TRACK.items():
        xs = [_abs(b, x, 0)[0] for (n, b, x, _y, _k, _t) in TAPS if n == net]
        if net == "CB":                       # CB also reaches Rz.P (below)
            xs.append(103.0)
        D.strap(top, min(xs) - 0.16, ty - 0.16, max(xs) + 0.16, ty + 0.16,
                D.MET3)
        D.label(top, net.lower(), min(xs), ty, layer=D.MET3LBL)

    # ---- compensation branch: cb -Rz- nz -Cc- vout -----------------------
    # cb -> Rz.P: out of the resistor on met2, left, then up onto the CB track.
    rP, rM = pins["res_rz"]["P"], pins["res_rz"]["M"]
    D.via_li_met2(top, *rP)
    _m2(top, rP[0], rP[1], 103.0, rP[1])
    _m2(top, 103.0, rP[1], 103.0, TRACK["CB"])
    D.via_met2_met3(top, 103.0, TRACK["CB"])
    # nz: Rz.M -> met2 -> down onto the Cc bottom plate (met3), in the strip
    # left of capm where a met3 label attaches to the plate.
    p1, p2 = pins["cap_cc9"]["P1"], pins["cap_cc9"]["P2"]
    D.via_li_met2(top, *rM)
    xp1 = 110.2
    _m2(top, rM[0], rM[1], xp1, rM[1])
    D.via_met2_met3(top, xp1, rM[1])
    D.label(top, "nz", 108.6, rM[1], layer=D.MET2LBL)
    # vout: out_stage's output bar -> met2 -> met3 across the open gap -> met4
    # over the cap to the top plate. The long run is on met3 because out_stage's
    # VSS/VDD risers already own met2 at those x.
    ov = _abs("out_stage", 6.0, 19.5)
    D.via2(top, *ov)
    D.via_met2_met3(top, *ov)
    xs4 = 104.0
    D.strap(top, ov[0] - 0.16, ov[1] - 0.16, xs4 + 0.16, ov[1] + 0.16, D.MET3)
    D.via_met3_met4(top, xs4, ov[1])
    D.strap(top, xs4 - 0.16, ov[1] - 0.16, p2[0] + 0.16, ov[1] + 0.16, D.MET4)
    D.strap(top, p2[0] - 0.16, ov[1] - 0.16, p2[0] + 0.16, p2[1] + 0.16, D.MET4)
    D.label(top, "vout", xs4, ov[1], layer=D.MET3LBL)

    top.flatten()
    lib = gdstk.Library()
    lib.add(top)
    lib.write_gds(str(OUT / "miller_rrf2.gds"))
    print("wrote miller_rrf2.gds")


def build():
    build_rrf2_nin()
    build_rrf2_cmir()
    build_rrf2_bias_n()
    build_rrf2_bias_p()
    build_rrf2_fold()
    build_rrf2_plow()
    build_cap_cc9()
    build_miller_rrf2()


if __name__ == "__main__":
    build()
