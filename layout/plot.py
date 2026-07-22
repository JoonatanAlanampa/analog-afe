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
    (D.DIFF, "#2ea02e", 0.55, "diff"),
    (D.POLY, "#c0281e", 0.70, "poly (gate)"),
    (D.LI, "#b8931e", 0.50, "li"),
    (D.LICON, "#111111", 0.95, "licon"),
]


def render(cellname, fingers_label=None):
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
            ax.text(x, 7.35, lab, ha="center", va="bottom", fontsize=13,
                    fontweight="bold", color=col)
    handles = [Line2D([0], [0], marker="s", ls="", markersize=11,
                      markerfacecolor=c, markeredgecolor=c, alpha=min(a + 0.2, 1),
                      label=l) for _ly, c, a, l in STYLE]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0),
              fontsize=10, framealpha=0.95, title="sky130 layers")
    ax.set_aspect("equal")
    ax.autoscale()
    ax.margins(0.02)
    ax.set_title(f"{cellname} — common-centroid NMOS input pair (D A B B A D) "
                 "+ p-tap guard ring\nDRC-clean, sky130A_mr deck",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("µm")
    ax.set_ylabel("µm")
    IMG.mkdir(parents=True, exist_ok=True)
    out = IMG / f"layout_{cellname}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"wrote {out}")


if __name__ == "__main__":
    # gate x-centres for the D A B B A D annotation (device at x0=2, SD=0.29,
    # L=0.5): first gate centre at 2 + SD + L/2, pitch SD + L
    x0, sd, L = 2.0, 0.29, 0.5
    xs = [x0 + sd + L / 2 + i * (sd + L) for i in range(6)]
    render("cc_pair", list(zip(xs, ["D", "A", "B", "B", "A", "D"])))
