# Phase 2 — layout (kickoff)

Phase 1 characterised the amplifier at the schematic level; phase 2 draws it,
and post-layout is where analog designs go to die (matching, parasitics, wells,
substrate). This is the kickoff: the flow is stood up and the two hardest-to-
get-right pieces — a real multi-finger device and a **common-centroid** matched
pair — are drawn and **DRC-clean** against the sky130 deck.

![Common-centroid NMOS input pair: six poly gate fingers labelled D A B B A D over a shared diffusion, each source/drain column contacted with licon up to li, wrapped in a p-tap guard ring. DRC-clean.](img/layout_cc_pair.png)

## The flow

All gdstk (Python) → GDS → KLayout DRC, no GUI:

| file | does |
|---|---|
| `layout/device.py` | sky130 device primitives: `fet(W, L, nf, kind)` and `guard_ring(...)` |
| `layout/build.py` | draws the cells to `layout/out/*.gds` |
| `layout/run_drc.py` | KLayout batch DRC (`sky130A_mr.drc`, feol+beol+offgrid), parses the `.lyrdb` |
| `layout/plot.py` | renders a cell to a layer-coloured PNG for these docs |

```sh
python layout/build.py && python layout/run_drc.py     # -> "CLEAN"
python layout/plot.py                                  # -> docs/img/
```

The KLayout binary and the deck are the same ones the `stdcells` leg uses
(`~/AppData/Roaming/KLayout/klayout_app.exe`, the PDK's `sky130A_mr.drc`).

## The device primitive

`fet()` builds a multi-finger transistor: one diffusion strip crossed by `nf`
poly gates, every source/drain column stitched with a licon stack up to `li`,
the active wrapped in its implant (nsdm / psdm), and — for PMOS — an nwell. The
**layer map and every spacing are mirrored from the `stdcells` cells** (which
are DRC/LVS-clean on this PDK), so the device is clean *by construction*: the
`nfet_test` cell (W = 5, L = 0.5, 2 fingers) passed the deck on the first run.

## The common-centroid pair — the reason phase 2 exists

The input pair's offset (Monte-Carlo σ = 4.24 mV, `corners.md` §8) is a matching
problem, and matching is a *layout* property. `cc_pair` draws the two devices A
and B as six interleaved fingers **D A B B A D**: A sits at fingers 2 and 5, B at
3 and 4, so their centroids coincide at finger 3.5. A linear process/oxide/stress
gradient across the pair then adds equally to both and cancels to first order —
which a side-by-side layout cannot do. Dummy fingers (D) at the ends give the
outer real fingers the same poly-density neighbourhood as the inner ones, and a
**p-tap guard ring** collects substrate current and fixes the local body
potential. The whole structure is DRC-clean.

## Status and what's next

| cell | DRC (`sky130A_mr`) |
|---|---|
| `nfet_test` (W 5 / L 0.5 / 2 fingers) | **CLEAN** |
| `cc_pair` (D A B B A D + p-tap guard ring) | **CLEAN** |

Two lessons already banked: mirroring the proven `stdcells` dimensions gets a
device clean on the first try rather than by iteration; and the guard ring's
first cut stacked mcon on licon and drew 74 `ct.2` violations — a li-connected
tap ring (met1 stitching deferred to routing) is both cleaner and sufficient.

Next, in order: **gate straps + source/drain routing** so the pair is a
connected two-device network; **LVS** (extract → match the schematic, reusing
the `stdcells` netgen/KLayout setup) — DRC proves geometry, only LVS proves it
is the *right* circuit; then the rest of the OTA (5T core + second stage) and
the bias generator; and finally **post-extraction re-simulation**, the number
that actually decides whether the silicon works.
