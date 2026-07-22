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


if __name__ == "__main__":
    build()
