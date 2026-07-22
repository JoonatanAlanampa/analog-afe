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
| `layout/verify.py` | one-command regression: build → DRC all → LVS all (the `tb/run.py` of the layout side) |
| `layout/plot.py` | renders a cell to a layer-coloured PNG for these docs |

```sh
python layout/verify.py         # build + DRC-all + LVS-all -> "REGRESSION CLEAN"
python layout/plot.py           # -> docs/img/
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
| `tail_bias` (NMOS mirror: tail source + bias diode) | **CLEAN** | **MATCH** |
| `met2_test` (met1↔met2 via + met2-over-met1 crossing) | **CLEAN** | — (layer check) |
| `ota5t_core` (whole 5T OTA: 6 devices, 3 strips, routed) | **CLEAN** | **MATCH** |
| `out_stage` (miller stage 2: PMOS CS + NMOS sink, class-A) | **CLEAN** | **MATCH** |

**All three sub-blocks of the 5T OTA — the NMOS input pair, the PMOS mirror
load, and the NMOS tail/bias — are laid out and verified as the right circuit,
and now so is the whole amplifier assembled from them.** Lessons banked:
mirroring the proven `stdcells` dimensions gets a device clean first try; a
li-connected tap ring beats stacking mcon on licon (74 `ct.2`); and once the net
*topology* is right (S/D and gates routed to layers/levels that can't collide)
LVS matches first try — every routed cell's only DRC fixes were sub-0.2 µm
connectivity near-misses, never topology.

## The 5T core, assembled and LVS-matched

![The whole 5T OTA laid out: three common-centroid strips stacked — PMOS mirror on top, NMOS input pair in the middle, NMOS tail/bias at the bottom — with n1 and tail routed on met1 verticals, vout on a central li riser, and the input gates taken out on li to the sides. DRC-clean and LVS-matched to all six transistors.](img/layout_ota5t_core.png)

`ota5t_core` places the three sub-blocks as **stacked common-centroid strips**
(mirror over input pair over tail) and routes the amplifier between them — the
piece the whole layout leg was building toward. It extracts to **exactly the six
transistors of `ota_5t.sp`** (bias diode, tail, input pair, mirror load) with
the internal nodes `n1` and `tail` and bulk ports `vnb`/`vnw` — **DRC-clean +
LVS MATCH**. The scaled W = 10 devices match the sub-block refs; the value here
is that the *assembly routing* is proven, not the devices (those were done).

The routing is where the congestion lives — the core has more distinct nets than
any sub-block. Three ideas keep every crossing on a different layer:

- **`n1` and `vout` never meet.** `n1` (the input A-drains and the whole mirror
  diode node) rides met1 up the **outer** columns; `vout` rides li up the
  **centre** column. Different x *and* different layer.
- **The input gates escape downward on li**, at two heights (vinp wide, vinn
  narrow), crossing the `tail` net — which is put on **met1** exactly where they
  cross — a layer below. This keeps the whole upper gap free for `n1`/`vout`.
- **Every source/drain leaves on met1 through a via that lands on a real licon
  stud *inside* the strip.** The device li stops ~0.27 µm short of the nominal
  strip edge, so a via at the edge floats — the first assembly attempt extracted
  with VDD, VOUT and the tail column disconnected for exactly this reason. The
  stacked source-contact (diff → licon → li → mcon → met1, on the stud) is the
  standard fix and is guaranteed to land on device li.

Lesson worth keeping: **a sub-block that is DRC+LVS-clean standalone does not
compose for free.** Each sub-block routed all its S/D one way (e.g. all down)
because it had a free side; stacked into the core, the same nets have to exit
*toward the neighbour they connect to*, so the input pair's routing had to be
redrawn (drains up, gates down) rather than instanced. The centroid *geometry*
carried over; the *routing* did not.

## The second stage — the class-A output

![The miller_ota second stage: a PMOS common-source (xm5) above an NMOS current sink (xm6), their drains shared as VOUT on a central met1 riser; the PMOS gate N2 exits right on li, the NMOS gate VB left. DRC-clean and LVS-matched.](img/layout_out_stage.png)

`out_stage` is the amplifier's **second stage** — `xm5`, a PMOS common-source
driven by the stage-1 output `n2`, over `xm6`, an NMOS current sink biased by
`vb`; their drains are tied as `VOUT`. It is the same shape as a CMOS inverter
(a p-device over an n-device sharing a drain), which is exactly what a class-A
output stage *is*. It extracts to the two transistors of `miller_ota.sp`'s stage
2 — **DRC-clean + LVS MATCH, first run** — because the two hard-won 5T-core
lessons carried straight over: sources leave on met1 through a via on a real
licon stud inside the strip, and the gates escape to the *sides* on li while the
drains meet on met1 up the centre, so nothing collides. Scaled W = 10 stands in
for the shipped W = 60 drive device; the topology and routing are what's proven.

## What's next

Both active pieces of the two-stage Miller amplifier are now laid out and
LVS-clean — the 5T core (stage 1) and this output stage (stage 2). What remains
of the amplifier layout:

- **The Miller passives** — the compensation cap `Cc` (a ~4 pF MIM or MOS cap, a
  large new device layer) and the nulling resistor `Rz` (a sky130 `xhigh_po`
  poly resistor). These are the first *passive* devices the leg draws.
- **Full-amp assembly** — stitch stage 1 + stage 2 + `Cc`/`Rz` into one
  `miller_ota` cell (the stage-1 output `n2` to the `xm5` gate, `vb` shared).
- **Post-extraction re-simulation** — run the benches again on the parasitic-
  extracted netlist, the number that actually decides whether the silicon works.
- **Rail-tie guard rings** (substrate → VSS, nwell → VDD) replace the bulk
  *ports* with real body ties.
