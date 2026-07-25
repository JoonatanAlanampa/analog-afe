"""Render a layout cell to a PNG (sky130-ish layer colours) for the docs.

    python layout/plot.py            # cc_pair -> docs/img/layout_cc_pair.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly
from matplotlib.lines import Line2D

import gdstk

import device as D

OUT = Path(__file__).resolve().parent / "out"
IMG = Path(__file__).resolve().parents[1] / "docs" / "img"

# draw order (back -> front) with (colour, alpha, label)
STYLE = [
    (D.NWELL, "#8f8fe0", 0.18, "nwell"),
    (D.NSDM, "#e58fa0", 0.22, "nsdm (n+)"),
    (D.PSDM, "#8f9fe5", 0.22, "psdm (p+)"),
    (D.URPM, "#c060c0", 0.22, "urpm (2k impl)"),
    (D.DIFF, "#2ea02e", 0.55, "diff"),
    (D.TAP, "#1e7a4a", 0.55, "tap (body tie)"),
    (D.POLY, "#c0281e", 0.70, "poly (gate)"),
    (D.POLY_RES, "#f0d000", 0.40, "poly_res"),
    (D.LI, "#b8931e", 0.50, "li"),
    (D.MET1, "#1e3ac0", 0.45, "met1"),
    (D.MET2, "#a04ec0", 0.35, "met2"),
    (D.MET3, "#3a6ac0", 0.35, "met3"),
    (D.CAPM, "#d04878", 0.45, "capm (MIM)"),
    (D.VIA, "#404040", 0.90, "via (m1-m2)"),
    (D.VIA2, "#404040", 0.90, "via2"),
    (D.VIA3, "#303030", 0.90, "via3"),
    (D.MET4, "#20a090", 0.40, "met4"),
    (D.LICON, "#111111", 0.95, "licon"),
    (D.MCON, "#5a5a5a", 0.95, "mcon"),
]


def render(cellname, title, fingers_label=None, finger_y=7.35, nets=False,
           skip_above=None):
    """`skip_above` drops labels above a y — miller_rrf2's routing channel
    carries 39 per-pin tags at nearly the same height, which are there for the
    extraction check, not for reading. The channel's geometry still shows."""
    lib = gdstk.read_gds(str(OUT / f"{cellname}.gds"))
    cell = next(c for c in lib.cells if c.name == cellname)
    fig, ax = plt.subplots(figsize=(11, 8.5))
    for layer, col, al, _lab in STYLE:
        for p in cell.polygons:
            if (p.layer, p.datatype) == layer:
                ax.add_patch(MPoly(p.points, closed=True, facecolor=col,
                                   edgecolor=col, alpha=al, lw=0.3))
    if fingers_label:
        for x, lab in fingers_label:
            col = {"A": "#c0281e", "B": "#1e3ac0", "D": "#666666"}[lab]
            ax.text(x, finger_y, lab, ha="center", va="bottom", fontsize=13,
                    fontweight="bold", color=col)
    if nets:
        for lb in cell.labels:
            if skip_above is not None and lb.origin[1] > skip_above:
                continue
            ax.text(lb.origin[0], lb.origin[1], lb.text, ha="center",
                    va="center", fontsize=8.5, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.15", fc="#222222", ec="none",
                              alpha=0.85))
    handles = [Line2D([0], [0], marker="s", ls="", markersize=11,
                      markerfacecolor=c, markeredgecolor=c, alpha=min(a + 0.2, 1),
                      label=l) for _ly, c, a, l in STYLE]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0),
              fontsize=10, framealpha=0.95, title="sky130 layers")
    ax.set_aspect("equal")
    ax.autoscale()
    ax.margins(0.02)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("µm")
    ax.set_ylabel("µm")
    IMG.mkdir(parents=True, exist_ok=True)
    out = IMG / f"layout_{cellname}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"wrote {out}")


if __name__ == "__main__":
    sd, L = 0.29, 0.5
    xs6 = [2.0 + sd + L / 2 + i * (sd + L) for i in range(6)]
    render("cc_pair", "cc_pair — common-centroid NMOS input pair (D A B B A D) "
           "+ p-tap guard ring\nDRC-clean, sky130A_mr deck",
           list(zip(xs6, ["D", "A", "B", "B", "A", "D"])))
    xs4 = [2.0 + sd + L / 2 + i * (sd + L) for i in range(4)]
    render("cc_diff", "cc_diff — common-centroid input pair, ROUTED "
           "(A B B A)\nDRC-clean + LVS MATCH to two W=10 NMOS",
           list(zip(xs4, ["A", "B", "B", "A"])), finger_y=8.4, nets=True)
    Lp = 1.0
    xs4p = [2.0 + sd + Lp / 2 + i * (sd + Lp) for i in range(4)]
    render("pmos_mirror", "pmos_mirror — common-centroid PMOS current mirror "
           "(A=xm3 diode, B=xm4)\nDRC-clean + LVS MATCH to two W=10 PMOS",
           list(zip(xs4p, ["A", "B", "B", "A"])), finger_y=8.0, nets=True)
    render("ota5t_core", "ota5t_core — the whole 5T OTA, production full-W\n"
           "PMOS mirror (W=20) over NMOS input pair (W=40) over tail/bias "
           "(W=20); shared nodes on met1+li, input gates on li\n"
           "DRC-clean + LVS MATCH; VINN→n1 / VINP→n2 (inverting convention)",
           nets=True)
    render("out_stage", "out_stage — the miller_ota second stage (class-A "
           "output), production full-W\nxm5 PMOS common-source over xm6 NMOS "
           "sink, W=150 (10 fingers), VOUT shared on met1; gates VB / N2\n"
           "DRC-clean + LVS MATCH", nets=True)
    render("res_rz", "res_rz — the Miller nulling resistor Rz (xhigh_po poly "
           "resistor)\npoly body under poly_res+urpm+psdm, W=0.69 L=3.45 (5 sq)"
           "; contacted at each end (P/M)\nDRC-clean + extraction-verified: "
           "R=10000 ohm", nets=True)
    render("cap_cc", "cap_cc — the Miller compensation cap Cc (MIM cap on met3)\n"
           "bottom plate met3 (P1), top plate capm (P2) contacted up via3->met4;"
           " 44.7x44.7 um -> 4 pF\nDRC-clean + extraction-verified: cap_mim "
           "C=4e-12 F", nets=True)
    render("miller_ota", "miller_ota — the whole two-stage amplifier, "
           "PRODUCTION FULL-W\n5T core (in W40 / mir+tail W20) | class-A output "
           "(W150) | Rz 10k | Cc 4pF;  rails + n2/vb + the Rz/Cc Miller branch\n"
           "all routed. DRC-clean + extraction-verified (10 devices, W's, nets, "
           "body ties)", nets=True)

    # ---- miller_rrf2: the spec-meeting amplifier -------------------------
    render("rrf2_nin", "rrf2_nin — miller_rrf2's NMOS high side: tail mirror "
           "(xmb/xm0, W20) under the common-centroid input pair (xm1/xm2, W40)\n"
           "the pair's drains leave as the FOLD nodes fa (outer cols, met1) and "
           "fb (centre col, li) — unpinned, which is what kills the 1.40 V wall\n"
           "DRC-clean + LVS MATCH", nets=True)
    render("rrf2_fold", "rrf2_fold — the PMOS fold: top sources xm9/xm10 (W30, "
           "common-centroid) feeding fa/fb, cascodes xm11/xm12 (W40) down to "
           "ca/cb\nxm11/xm12 share only their gate (sources are fa and fb), so "
           "they cannot interleave — two separate 2-finger devices\n"
           "DRC-clean + LVS MATCH", nets=True)
    render("rrf2_cmir", "rrf2_cmir — the self-biased cascode mirror, THE fix of "
           "miller_rrf2 (xm13/xm14 mirror, xm15/xm16 cascode, all W20)\n"
           "both references diode-connected, so the reference leg carries the "
           "ACTUAL folded current and self-matches — a wide-swing cascode with "
           "an independent bias collapsed\nDRC-clean + LVS MATCH", nets=True)
    render("rrf2_plow", "rrf2_plow — the PMOS low side: tail xmp0 (W60) over the "
           "input pair xmp1/xmp2 (W60) over their NMOS mirror load xmp3/xmp4 "
           "(W30)\nscaled 1.5x vs the high side — the margin tune that lifted "
           "the trough gain and took the temperature corners under 0.1 %\n"
           "gates escape UPWARD: nP and cb already fill the gap below\n"
           "DRC-clean + LVS MATCH", nets=True)
    render("miller_rrf2", "miller_rrf2 — the whole spec-meeting amplifier, "
           "FROM-SCRATCH LAYOUT (25 transistors + Rz + Cc, 177 x 96 µm)\n"
           "bias | NMOS input | fold | cascode mirror | PMOS low side | class-A "
           "output (reused) | Rz 10k | Cc 9pF\ntwo-layer channel above: one met3 "
           "track per net, one met2 riser per pin\n"
           "DRC-clean + every block LVS MATCH + extraction-verified "
           "(27 devices, 14 nets, body ties, polarity)", nets=True,
           skip_above=78.0)
