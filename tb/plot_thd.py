"""Render the THD story as one figure for the README.

Two panels, both straight out of `docs/thd.md` (regenerate that with
`python tb/thd.py`, then this):

  left  -- THD vs output swing: the buffer is a clean line source only to
           ~0.75 V pp, then knees past both targets at the 1 V pp spec swing.
  right -- THD vs phase margin: raising output drive alone (fixed ×1
           compensation) walks THD down but straight into the 60 deg wall;
           the co-designed fix point clears both.

Numbers are the measured values in docs/thd.md -- kept as literals here with
that provenance, because this is a view of that table, not a new measurement.
Colours are the Okabe-Ito colourblind-safe set.

    python tb/plot_thd.py        # -> docs/img/thd.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUTPNG = ROOT / "docs" / "img" / "thd.png"

# Okabe-Ito (colourblind-safe)
BLUE, VERM, GREEN, GRAY, INK = "#0072B2", "#D55E00", "#009E73", "#9AA0A6", "#1A1A1A"

# --- docs/thd.md, "vs output level" ---------------------------------------
LEVEL = [(0.1, 0.000246), (0.3, 0.000596), (0.5, 0.01283), (0.6, 0.03148),
         (0.7, 0.05914), (0.8, 0.11034), (0.9, 0.37612), (1.0, 1.43859),
         (1.5, 12.8311)]

# --- docs/thd.md, "output-stage drive" : (pout, THD%, PM deg, Iq uA) -------
DRIVE = [(1.0, 1.439, 68.3, 80), (1.5, 0.624, 63.2, 111),
         (2.0, 0.216, 54.6, 142), (3.0, 0.300, 39.7, 203)]

# --- the co-designed fix (tb/thd.py fix, corner-verified in corners.md) ----
# (pout, Cc pF, Rz k, THD%, PM deg, Iq uA)
FIX = (2.5, 4.0, 10, 0.167, 81.0, 173)

PM_SPEC, THD_TGT, THD_OLD = 60.0, 0.1, 1.0


def style():
    plt.rcParams.update({
        "figure.dpi": 200, "font.size": 10.5, "font.family": "DejaVu Sans",
        "axes.edgecolor": GRAY, "axes.linewidth": 0.8, "axes.titlesize": 11,
        "axes.titleweight": "bold", "axes.labelcolor": INK, "text.color": INK,
        "xtick.color": INK, "ytick.color": INK, "axes.grid": True,
        "grid.color": "#E6E8EB", "grid.linewidth": 0.8,
        "axes.axisbelow": True, "figure.facecolor": "white",
        "axes.facecolor": "white", "svg.fonttype": "none",
    })


def panel_knee(ax):
    xs = [v for v, _ in LEVEL]
    ys = [t for _, t in LEVEL]
    ax.set_yscale("log")
    ax.axhspan(1e-4, THD_TGT, color=GREEN, alpha=0.07, zorder=0)
    ax.axhline(THD_TGT, color=GREEN, lw=1.4, ls="--")
    ax.axhline(1.0, color=VERM, lw=1.4, ls="--")
    ax.plot(xs, ys, color=BLUE, lw=2.0, marker="o", ms=5,
            markerfacecolor="white", markeredgecolor=BLUE, markeredgewidth=1.6,
            zorder=5)
    # spec swing marker
    ax.plot([1.0], [1.43859], marker="o", ms=8, color=VERM, zorder=6)
    ax.annotate("1.44 %\nat 1 Vpp\nspec swing", xy=(1.0, 1.439),
                xytext=(0.62, 3.2), color=VERM, fontsize=9.5, ha="center",
                arrowprops=dict(arrowstyle="->", color=VERM, lw=1.2))
    ax.text(0.12, THD_TGT * 1.25, "0.1 % line-level target", color=GREEN,
            fontsize=9, va="bottom")
    ax.text(0.12, 1.0 * 1.25, "1 % (old spec row 12)", color=VERM,
            fontsize=9, va="bottom")
    ax.text(0.5, 2.5e-4, "clean\n< 0.1 %", color=GREEN, fontsize=9,
            ha="center", va="center")
    ax.set_xlim(0.05, 1.55)
    ax.set_ylim(1e-4, 20)
    ax.set_xlabel("output swing  (V pp)")
    ax.set_ylabel("THD  (%)")
    ax.set_title("The problem: distortion knee (1 kHz)")


def panel_fix(ax):
    ax.set_yscale("log")
    # the PM-spec wall: everything right of 60 deg meets phase margin
    ax.axvspan(PM_SPEC, 90, color=GREEN, alpha=0.06, zorder=0)
    ax.axvline(PM_SPEC, color=GRAY, lw=1.2, ls="--")
    ax.text(PM_SPEC + 0.7, 0.13, "60° PM spec", color=GRAY, fontsize=8.5,
            ha="left", va="center", rotation=90)
    # reference THD levels
    ax.axhline(THD_OLD, color=VERM, lw=1.2, ls="--")
    ax.axhline(THD_TGT, color=BLUE, lw=1.2, ls=":")
    ax.text(36, THD_OLD * 1.1, "1 % (old spec)", color=VERM, fontsize=8.5,
            va="bottom")
    ax.text(36, THD_TGT * 1.1, "0.1 % aspiration — needs class-AB",
            color=BLUE, fontsize=8.5, va="bottom")
    # drive sweep (fixed x1 compensation) — walks down AND left into the wall
    pm = [d[2] for d in DRIVE]
    th = [d[1] for d in DRIVE]
    ax.plot(pm, th, color=VERM, lw=1.8, marker="s", ms=6, zorder=4,
            label="raise drive only (Cc 2p / Rz 20k)")
    for pout, thd, pmd, _ in DRIVE:
        off = (5, 7) if pout != 3.0 else (5, -14)
        ax.annotate(f"×{pout:g}", xy=(pmd, thd), xytext=off,
                    textcoords="offset points", color=VERM, fontsize=9)
    if FIX:
        pout, cc, rz, thd, pmd, iq = FIX
        ax.plot([pmd], [thd], marker="*", ms=19, color=GREEN, zorder=6,
                markeredgecolor="white", markeredgewidth=0.8,
                label=f"co-designed fix: ×{pout:g}, Cc {cc:g}p / Rz {rz:g}k")
        ax.annotate(f"fix\n{thd:.2f}%, {pmd:.0f}°\n{iq:.0f} µA",
                    xy=(pmd, thd), xytext=(-6, 20),
                    textcoords="offset points", color=GREEN, fontsize=9,
                    fontweight="bold", ha="center",
                    arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.2))
    ax.set_xlim(36, 88)
    ax.set_ylim(0.08, 2)
    ax.set_xlabel("phase margin  (deg)   →  more stable")
    ax.set_ylabel("THD  (%)   ↓ lower is better")
    ax.set_title("The fix: co-design output current + compensation")
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.95,
              edgecolor="#E6E8EB")


def main():
    style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.2, 4.5))
    panel_knee(a)
    panel_fix(b)
    fig.suptitle("Audio buffer THD: the 1 Vpp shortfall, and the co-designed fix",
                 fontsize=12.5, fontweight="bold", y=1.02)
    fig.tight_layout()
    OUTPNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPNG, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUTPNG}")


if __name__ == "__main__":
    main()
