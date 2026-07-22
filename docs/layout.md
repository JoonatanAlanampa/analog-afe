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
| `layout/device.py` | sky130 primitives: `fet(W, L, nf, kind)`, `guard_ring`, `poly_contact` (gate terminal), `label`, `strap` |
| `layout/build.py` | draws the cells to `layout/out/*.gds` |
| `layout/run_drc.py` | KLayout batch DRC (`sky130A_mr.drc`, feol+beol+offgrid), parses the `.lyrdb` |
| `layout/run_lvs.py` | KLayout LVS (`sky130.lvs`, patched for device-class case) vs a reference netlist |
| `layout/plot.py` | renders a cell to a layer-coloured PNG for these docs |

```sh
python layout/build.py && python layout/run_drc.py     # geometry -> "CLEAN"
python layout/run_lvs.py                               # circuit  -> "MATCH"
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

## LVS — proving it is the *right* circuit

DRC only checks geometry; a layout can be DRC-clean and still be the wrong
netlist (the `stdcells` leg found a NAND2 power-to-output short that DRC merged
silently — only LVS caught it). `run_lvs.py` extracts a cell with the PDK's
`sky130.lvs` deck (patched so the SPICE reader's uppercase device-class names
equate to the lowercase extracted ones) and compares it to a reference netlist.

`nfet_lvs` is the first device wired for it: a single finger with a **gate
contact** (poly → npc → licon → li) and **S / G / D labels**, bulk as a port
(the extractor exports the untapped p-substrate as one net). It extracts to
exactly `M0 D G S B nfet_01v8 L=0.5u W=5u` — **LVS MATCH**.

## The input pair, routed and LVS-clean

`cc_diff` takes the common-centroid arrangement and *connects* it into the
differential pair the OTA actually uses — and it is the piece where the routing
earns its keep.

![Routed common-centroid input pair: four fingers A B B A with VA (li) tying the outer A gates, VB (met1) the inner B gates, TAIL (li) the common source, OA (met1) the A drains and OB the B drain — DRC-clean and LVS-matched to two W=10 NMOS.](img/layout_cc_diff.png)

The four fingers A B B A share one diffusion; alternating the source/drain
columns makes A = fingers 0,3 and B = fingers 1,2, each a **W = 10 µm** (2 × 5)
transistor with a **common source (tail)** — the input pair. Five nets have to
leave that strip without shorting, and there are only two routing layers, so
each net is placed where it can't collide: source/drain go **down**, gates go
**up**; the two nets that must span the middle — `TAIL` and `OA` — sit at
different heights (`TAIL` on li, `OA` on met1 one level below), so their risers
never cross; likewise `VA` runs on li and `VB` on met1, crossing only where
they are on different layers. It extracts to exactly two W=10 NMOS with a shared
source — **LVS MATCH**.

## The other matched pair — the PMOS mirror load

`pmos_mirror` is the input pair's counterpart (xm3/xm4), and it brings in
everything the NMOS work didn't touch: a **PMOS** device, its **nwell**, and an
**n-tap guard ring** to tie the well (proven first on the single `pfet_lvs`).
Same A B B A common-centroid, but a *mirror*: all four gates tie to `N1` and
xm3 is **diode-connected** (its gate = its drain = N1). That diode tie actually
makes the routing *tidier* than the differential pair — N1 (every gate plus the
A drains) all runs UP to one li strap, VDD (the sources) runs DOWN, VOUT stays
local — so nothing has to cross. It extracts to two W=10 PMOS, xm3 diode-tied —
**LVS MATCH**, DRC-clean on the first run.

## Status and what's next

| cell | DRC (`sky130A_mr`) | LVS (`sky130.lvs`) |
|---|---|---|
| `nfet_lvs` (1 finger, gate contact + S/G/D) | **CLEAN** | **MATCH** |
| `pfet_lvs` (PMOS in nwell + n-tap guard ring) | **CLEAN** | **MATCH** |
| `cc_pair` (D A B B A D + p-tap guard ring) | **CLEAN** | — (matching-structure demo) |
| `cc_diff` (A B B A routed NMOS input pair) | **CLEAN** | **MATCH** |
| `pmos_mirror` (A B B A routed PMOS mirror load) | **CLEAN** | **MATCH** |

Both of the OTA's matching-critical pairs — the NMOS input pair and the PMOS
mirror load — are now laid out **and** verified as the right circuit. Lessons
banked: mirroring the proven `stdcells` dimensions gets a device clean first
try; a li-connected tap ring beats stacking mcon on licon (74 `ct.2`); and once
the net *topology* is right (S/D and gates routed to layers/levels that can't
collide) LVS matches first try — every routed cell's only DRC fixes were
sub-0.2 µm connectivity near-misses, never topology.

Next: **the 5T core** — place the input pair and the mirror together, add the
tail current source and the bias diode, and route the internal nodes (n1, tail,
vout); then the second stage and the bias generator; and finally
**post-extraction re-simulation**, the number that actually decides whether the
silicon works.
