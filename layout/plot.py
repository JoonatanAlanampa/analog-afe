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
    (D.POLY, "#c0281e", 0.70, "poly (gate)"),
    (D.POLY_RES, "#f0d000", 0.40, "poly_res"),
    (D.LI, "#b8931e", 0.50, "li"),
    (D.MET1, "#1e3ac0", 0.45, "met1"),
    (D.MET3, "#3a6ac0", 0.35, "met3"),
    (D.CAPM, "#d04878", 0.45, "capm (MIM)"),
    (D.VIA3, "#303030", 0.90, "via3"),
    (D.MET4, "#20a090", 0.40, "met4"),
    (D.LICON, "#111111", 0.95, "licon"),
    (D.MCON, "#5a5a5a", 0.95, "mcon"),
]


def render(cellname, title, fingers_label=None, finger_y=7.35, nets=False):
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
    render("ota5t_core", "ota5t_core — the whole 5T OTA, assembled and routed\n"
           "PMOS mirror over NMOS input pair over tail/bias; shared nodes "
           "(n1/vout/tail) on met1+li, input gates on li\n"
           "DRC-clean + LVS MATCH to all six transistors", nets=True)
    render("out_stage", "out_stage — the miller_ota second stage (class-A "
           "output)\nxm5 PMOS common-source over xm6 NMOS sink, VOUT shared on "
           "met1; gates VB (left) / N2 (right)\nDRC-clean + LVS MATCH",
           nets=True)
    render("res_rz", "res_rz — the Miller nulling resistor Rz (xhigh_po poly "
           "resistor)\npoly body under poly_res+urpm+psdm, W=0.69 L=3.45 (5 sq)"
           "; contacted at each end (P/M)\nDRC-clean + extraction-verified: "
           "R=10000 ohm", nets=True)
    render("cap_cc", "cap_cc — the Miller compensation cap Cc (MIM cap on met3)\n"
           "bottom plate met3 (P1), top plate capm (P2) contacted up via3->met4;"
           " 10x10 um -> ~200 fF\nDRC-clean + extraction-verified: cap_mim "
           "C=2e-13 F", nets=True)
    render("miller_ota", "miller_ota — the whole two-stage amplifier, wired\n"
           "5T core | class-A output | Rz | Cc;  VDD/VSS rails tied, and n2 "
           "(stage-1 out -> xm5 gate -> Rz) + vb routed over-the-cell on met2\n"
           "DRC-clean", nets=True)
