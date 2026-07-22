"""sky130 analog device primitives (gdstk) for the analog-afe layout leg.

Phase 2 starts here. The layer map and the spacings below are mirrored from
the `stdcells` flow (read-only), which is DRC/LVS-clean on the same PDK, so a
device drawn to these dimensions inherits that geometry by construction. What
is new is the ANALOG parameterisation: wide multi-finger W, arbitrary L, and
(in build.py) common-centroid pairs with dummies and a guard ring -- the
matching techniques a standard-cell generator never needs.

A single finger is diff crossed by a poly gate; each source/drain diff column
carries a stack of licon contacts up to `li`, and the whole active is wrapped
in its implant (nsdm for NMOS, psdm for PMOS). PMOS additionally sits in an
nwell. Body/well ties come from the guard ring in build.py.
"""
import gdstk

# sky130 GDS layers (datatype), from stdcells/flow/layout.py
NWELL = (64, 20)
DIFF = (65, 20)
NSDM = (93, 44)
PSDM = (94, 20)
POLY = (66, 20)
NPC = (95, 20)
LICON = (66, 44)
LI = (67, 20)
LILBL = (67, 5)
MCON = (67, 44)
MET1 = (68, 20)
MET1LBL = (68, 5)
VIA = (68, 44)           # met1 <-> met2 via
MET2 = (69, 20)
MET2LBL = (69, 5)
POLY_RES = (66, 13)      # poly-resistor body marker (defines the resistive run)
URPM = (79, 20)          # 2k-ohm (xhigh) poly-resistor implant
BND = (235, 4)

# rule-derived dimensions (um), matched to the clean stdcells cells
LICON_SZ = 0.17          # licon1.1 exact
LICON_SP = 0.17          # licon1.2 min spacing  -> pitch 0.34
LICON_ENC = 0.06         # difftap encloses licon (licon1.5b)
LICON_GATE = 0.06        # licon to poly gate (licon1.11 = 0.055; 0.06 margin)
LI_ENC = 0.08            # li encloses licon (li side enclosure)
POLY_ENDCAP = 0.13       # poly beyond diff (poly.8)
SD = 0.29                # source/drain diff column width (0.06+0.17+0.06)
IMPLANT_ENC = 0.13       # implant/nwell encloses diff (>= 0.125)


def _r(cell, layer, x0, y0, x1, y1):
    cell.add(gdstk.rectangle((round(x0, 3), round(y0, 3)),
                             (round(x1, 3), round(y1, 3)),
                             layer=layer[0], datatype=layer[1]))


def _licon_col(cell, xc, y0, W):
    """A column of licon contacts up a source/drain edge of height W, with an
    li cover that encloses them. Returns the li x-extents."""
    y = y0 + LICON_ENC
    top = y0 + W - LICON_ENC
    last = None
    while y + LICON_SZ <= top + 1e-6:
        _r(cell, LICON, xc - LICON_SZ / 2, y, xc + LICON_SZ / 2, y + LICON_SZ)
        last = y + LICON_SZ
        y += LICON_SZ + LICON_SP
    if last is not None:
        lx0, lx1 = xc - LICON_SZ / 2 - LI_ENC, xc + LICON_SZ / 2 + LI_ENC
        _r(cell, LI, lx0, y0 + LICON_ENC - LI_ENC, lx1, last + LI_ENC)
        return lx0, lx1
    return None


def fet(cell, x0, y0, W, L, nf=1, kind="n"):
    """Multi-finger FET at (x0,y0). Returns a dict with the diff span, the gate
    x-centres and the source/drain x-centres (for routing/labels)."""
    sdm = NSDM if kind == "n" else PSDM
    totx = (nf + 1) * SD + nf * L
    _r(cell, DIFF, x0, y0, x0 + totx, y0 + W)
    _r(cell, sdm, x0 - IMPLANT_ENC, y0 - IMPLANT_ENC,
       x0 + totx + IMPLANT_ENC, y0 + W + IMPLANT_ENC)
    if kind == "p":
        _r(cell, NWELL, x0 - IMPLANT_ENC - 0.05, y0 - IMPLANT_ENC - 0.05,
           x0 + totx + IMPLANT_ENC + 0.05, y0 + W + IMPLANT_ENC + 0.05)
    gates, sds = [], []
    x = SD
    sds.append(SD / 2)                                  # first S/D column
    for _i in range(nf):
        _r(cell, POLY, x0 + x, y0 - POLY_ENDCAP, x0 + x + L, y0 + W + POLY_ENDCAP)
        gates.append(x + L / 2)
        x += L
        sds.append(x + SD / 2)
        x += SD
    for xc in sds:
        _licon_col(cell, x0 + xc, y0, W)
    return dict(totx=totx, W=W, gates=[x0 + g for g in gates],
                sds=[x0 + s for s in sds])


def label(cell, name, x, y, layer=LILBL):
    cell.add(gdstk.Label(name, (round(x, 3), round(y, 3)),
                         layer=layer[0], texttype=layer[1]))


def poly_contact(cell, xg, L, y_top, up=0.45):
    """Extend a gate poly (centre xg, width L, ending at y_top) upward by `up`
    and cap it with a poly pad + npc + licon + li -- the gate terminal. Sizes
    mirror the clean stdcells pad (poly/li enclose the licon by 0.08, npc by
    0.10). Returns the li-patch centre for a label or a strap."""
    yc = y_top + up
    _r(cell, POLY, xg - L / 2, y_top - 0.02, xg + L / 2, yc + 0.085)   # riser
    _r(cell, POLY, xg - 0.165, yc - 0.165, xg + 0.165, yc + 0.165)     # pad
    _r(cell, NPC, xg - 0.185, yc - 0.185, xg + 0.185, yc + 0.185)
    _r(cell, LICON, xg - 0.085, yc - 0.085, xg + 0.085, yc + 0.085)
    _r(cell, LI, xg - 0.165, yc - 0.165, xg + 0.165, yc + 0.165)
    return xg, yc


def poly_contact_dn(cell, xg, L, y_bot, down=0.45):
    """Like `poly_contact`, but the gate terminal drops BELOW the device (riser
    from the poly end `y_bot` downward by `down`). The core takes the input-pair
    gates out on the bottom side so the upper gap is free for n1/vout. Returns
    the li-patch centre."""
    yc = y_bot - down
    _r(cell, POLY, xg - L / 2, yc - 0.085, xg + L / 2, y_bot + 0.02)   # riser
    _r(cell, POLY, xg - 0.165, yc - 0.165, xg + 0.165, yc + 0.165)     # pad
    _r(cell, NPC, xg - 0.185, yc - 0.185, xg + 0.185, yc + 0.185)
    _r(cell, LICON, xg - 0.085, yc - 0.085, xg + 0.085, yc + 0.085)
    _r(cell, LI, xg - 0.165, yc - 0.165, xg + 0.165, yc + 0.165)
    return xg, yc


def strap(cell, x0, y0, x1, y1, layer=LI):
    """A routing rectangle (li by default). Min li width 0.17 -- callers keep
    the thinner dimension >= 0.17."""
    _r(cell, layer, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def via(cell, xc, yc):
    """li -> met1 via: an mcon capped by a met1 pad. Pad 0.28 x 0.30 mirrors
    the stdcells pin (min met1 area, and enough enclosure of the 0.17 mcon)."""
    _r(cell, MCON, xc - 0.085, yc - 0.085, xc + 0.085, yc + 0.085)
    _r(cell, MET1, xc - 0.14, yc - 0.15, xc + 0.14, yc + 0.15)


def via2(cell, xc, yc):
    """met1 -> met2 via: a VIA (0.15 exact) capped by a met1 pad below and a
    met2 pad above, each enclosing it by 0.085 (0.32 sq). The caller's own met1
    routing usually is the pad below, but drawing it makes the stack complete
    wherever `via2` is dropped."""
    _r(cell, VIA, xc - 0.075, yc - 0.075, xc + 0.075, yc + 0.075)
    _r(cell, MET1, xc - 0.16, yc - 0.16, xc + 0.16, yc + 0.16)
    _r(cell, MET2, xc - 0.16, yc - 0.16, xc + 0.16, yc + 0.16)


def guard_ring(cell, x0, y0, x1, y1, w=0.5, kind="p"):
    """A tap ring around (x0,y0)-(x1,y1): a diff ring, its implant as a ring
    (p+ for an NMOS body tie, n+ for an nwell tie -- NOT a filled rectangle,
    so it never overlaps the device's own implant inside), licon+li+met1 up to
    a metal ring for the VSS/well connection. This is the analog structure a
    standard cell never draws: it collects substrate current and isolates the
    matched pair. n-taps additionally carry nwell."""
    sdm = PSDM if kind == "p" else NSDM
    bars = [(x0, y0, x1, y0 + w), (x0, y1 - w, x1, y1),
            (x0, y0, x0 + w, y1), (x1 - w, y0, x1, y1)]
    for a, b, c, d in bars:
        _r(cell, DIFF, a, b, c, d)
        _r(cell, sdm, a - 0.03, b - 0.03, c + 0.03, d + 0.03)
        _r(cell, LI, a, b, c, d)          # li IS the tap connection; met1
    if kind == "n":                       # stitching is a routing step
        _r(cell, NWELL, x0 - 0.1, y0 - 0.1, x1 + 0.1, y1 + 0.1)
    # licon studs along each bar, centred in the w-wide track (diff->li tap)
    def stud(xc, yc):
        _r(cell, LICON, xc - 0.085, yc - 0.085, xc + 0.085, yc + 0.085)
    xx = x0 + w / 2
    while xx <= x1 - w / 2 + 1e-6:
        stud(xx, y0 + w / 2)
        stud(xx, y1 - w / 2)
        xx += 0.34
    yy = y0 + w / 2 + 0.34
    while yy <= y1 - w / 2 - 0.34 + 1e-6:
        stud(x0 + w / 2, yy)
        stud(x1 - w / 2, yy)
        yy += 0.34
