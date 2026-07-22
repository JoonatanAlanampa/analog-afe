# PLAN — analog front-end (`analog-afe`)

The classic-EE leg of the full-stack goal: own analog blocks designed
from device physics up, validated on a TinyTapeout analog slot, then
integrated into the console so the finale is mixed-signal.

Chain: **op-amp → comparator → SAR ADC**, plus the ring-oscillator clock
that comes over from the vertical-slice test structures.

Console roles (why each block exists):
- op-amp + DAC → audio output, replacing the sigma-delta bitstream and
  the cartridge Pmod's external RC/amp
- comparator + SAR ADC → paddle-controller input, period-authentic
  analog pots
- own ring-osc → on-chip clock

## Phase 0 — kickoff (DONE)

- [x] Repo scaffold, `PLAN.md`, spec traced to the console (`docs/spec.md`)
- [x] ngspice + sky130 harness cribbed verbatim from
      `stdcells/flow/common.py` (incl. the Windows 8.3 short-path fix)
- [x] Two candidate topologies as hand-written netlists:
      `spice/ota_5t.sp`, `spice/miller_ota.sp` — plus a current-matched
      third variant so the comparison is about topology, not bias
- [x] Four benches: DC operating point (per-device saturation margin),
      open-loop gain / UGF / phase margin / gain margin, PSRR, step
      response — over four console-derived load corners
- [x] Results table (`docs/results.md`), compensation sweep
      (`docs/compensation.md`), findings (`docs/design-notes.md`)
- [x] Reviewer's one-pager (`docs/review-brief.md`)
- [x] **Topology review — DONE 2026-07-22** (`docs/topology-review.md`):
      two-stage Miller; accept 56.8 dB → rewrite row 5 as THD; Cc 2p /
      Rz 20k; line-level only (TT 4 mA pad rules out class-AB); O1 closed
      (3.3 V VAPWR available, not taken); series coupling cap mandatory.
      Also fixed harness bugs H1/H2 (untagged benches) it found.

## Phase 1 — close the op-amp (after the review) — DONE 2026-07-22

- [x] **Input-referred noise** (`tb/noise.py` -> `docs/noise.md`) — done
      out of order, because it was the unknown most likely to change the
      topology call. It did not: all candidates ~23-24 µV rms, ~4× under
      spec, and the NMOS-pair flicker caveat is REFUTED (`design-notes.md`
      §6). Noise does not discriminate the topologies.
- [x] **THD** (`tb/thd.py` -> `docs/thd.md`) — and it found a real gap:
      at the 1 V pp spec swing THD is **1.44 %**, over both spec row 12
      (< 1 %) and the review's proposed 0.1 %. The buffer is a clean line
      source (< 0.1 %) only up to ~0.75 V pp — the class-A output sink
      (61.5 µA, the §5 slew-asymmetry device) runs out of pull at the
      required swing. The `drive` sweep sizes the fix: scaling the output
      stage drops THD hard (0.22 % by ×2) but the ×1 compensation loses
      phase margin (< 60° by ×2), so the fix is a **joint output-current +
      Cc/Rz retune**, not a knob (`design-notes.md` §11).
- [x] **THD fix applied + corner-verified** (`design-notes.md` §12,
      `corners.md`, figure `docs/img/thd.png`): co-design lands on **×2.5
      output, Cc 4 pF / Rz 10 kΩ → 0.167 % THD** (8.6× better than shipped),
      worst-corner PM 75.6°, UGF ≥ 8.73 MHz, I_q ≤ 174 µA — meets spec with
      margin and *more* PM headroom than the shipped design. `Rz 20k→10k` is
      the phase-margin lever (cuts the §7 feedforward), `pout` the THD lever.
- [x] **CMRR + ICMR** (`tb/cmrr.py` -> `docs/cmrr.md`, design-notes §13).
      CMRR **68.7 dB** (flat, a first-stage property — PASS). ICMR sweep
      settled the 0.1 % question and **corrected the class-AB guess above**:
      the fix's 0.167 % residual is the INPUT pair leaving its common-mode
      range on the high half of the swing (xm2 triodes at 1.40 V = the 1 V pp
      peak), NOT the output stage. Confirmed by THD-vs-swing at the fix
      (0.0045 % at 0.4 V pp, 37× cleaner). So ≤ 0.1 % at full 1 V pp needs a
      **wider-ICMR input** (rail-to-rail / complementary pair) or a smaller
      swing — more output current cannot reach it.
- [x] **Corners: ss/ff/sf/fs × −40/25/85 °C ± 10 % supply, and Monte
      Carlo offset** (`tb/corners.py` -> `docs/corners.md`). Settled the
      compensation call: the Rz = 20 k lead point is the MOST corner-
      stable (PM 67.4-68.5° across the box), the textbook Rz ≈ 1/gm2
      point fails 60° everywhere — the kickoff's caution had the
      mechanism backwards (`design-notes.md` §7). Offset σ = 4.24 mV,
      3σ ≈ ±12.7 mV: negligible for this buffer, first-order for the
      comparator/SAR (§8).
- [x] **Bias generator** (`tb/biasgen.py` -> `docs/biasgen.md`, design-notes
      §14): constant-gm beta-multiplier + 3-transistor start-up replacing the
      ideal `ib`. I_ref ≈ 19.3 µA; gm·R holds ~1.5 % over PVT while the current
      moves ±18 % (constant-gm), supply-independent; start-up wakes it in
      ~3.8 µs and is proven necessary (dead without it); drives the real OTA to
      the identical operating point. Open: swap the ideal R for a real xhigh_po
      poly resistor (the true PVT floor); the ~55 µA draw is shared overhead.
- [x] **O1 resolved** (by the topology review): 3.3 V VAPWR available but not
      taken; no separate analog domain; the pad + ESD *model* is a phase-2 item.

## Phase 2 — layout (KICKOFF DONE 2026-07-22)

- [x] **Flow stood up** (`layout/`, `docs/layout.md`): gdstk device
      primitives (`device.py`) → GDS → KLayout DRC (`run_drc.py`,
      `sky130A_mr.drc`, reusing the `stdcells` KLayout + deck) → layer-coloured
      PNG (`plot.py`). Layer map + spacings mirrored from the DRC-clean
      `stdcells` cells, so devices are clean by construction.
- [x] **First devices DRC-clean:** `nfet_test` (W 5 / L 0.5 / 2-finger) and
      **`cc_pair` — the common-centroid input pair** (D A B B A D, A/B centroids
      coincident, dummies + p-tap guard ring). Both pass the deck. Lesson: the
      guard ring's mcon-on-licon stack drew 74 `ct.2`; a li-connected tap ring
      is cleaner and sufficient.
- [x] **LVS flow proven** (`layout/run_lvs.py`, KLayout `sky130.lvs` patched for
      device-class case): `nfet_lvs` — a single finger with a gate contact
      (poly→npc→licon→li) + S/G/D labels, bulk as a port — extracts to exactly
      `M0 D G S B nfet_01v8 L=0.5u W=5u`, **LVS MATCH**. DRC proves geometry;
      this proves the circuit.
- [x] **Common-centroid pair ROUTED + LVS-clean** (`cc_diff`, figure
      `docs/img/layout_cc_diff.png`): four fingers A B B A → two **W=10** NMOS
      with a common source; five nets routed on li+met1 without shorts (S/D
      down, gates up; TAIL/OA and VA/VB cross only on different layers).
      DRC-clean, **LVS MATCH** — the input pair verified as the right circuit.
- [x] **PMOS capability + the mirror load** (`pfet_lvs`, `pmos_mirror`): a PMOS
      in nwell tied by an n-tap guard ring (`pfet_lvs` **LVS MATCH**), then the
      OTA's common-centroid current-mirror load (xm3 diode + xm4) — DRC-clean +
      **LVS MATCH** to two W=10 PMOS (figure `docs/img/layout_pmos_mirror.png`).
      Both of the OTA's matching pairs are now laid out AND circuit-verified.
- [x] **Tail/bias current source** (`tail_bias`): the OTA's xm0/xmb as an NMOS
      current mirror — DRC-clean + **LVS MATCH** (reused the mirror pattern, all
      first try). All three 5T sub-blocks now done both ways; `layout/verify.py`
      runs the whole build→DRC→LVS regression green (7 cells, 5 LVS-matched).
- [x] **met2 routing layer added + validated** (`device.py`: met2/via layers +
      `via2()` stack; `met2_test` — two met1 pads joined by a met2 strap through
      a via at each end, that strap crossing a met1 wire of another net —
      **DRC-clean**). The second metal the assembled core needs (each sub-block
      fits on li+met1, but the core's ~7 nets exit in every direction).
- [x] **5T core assembled + LVS-matched** (`ota5t_core`, figure
      `docs/img/layout_ota5t_core.png`): the three sub-blocks placed as stacked
      common-centroid strips (mirror over input over tail) and routed into the
      whole amplifier — extracts to **exactly the six transistors of `ota_5t.sp`**
      (n1/tail internal, vnb/vnw bulk ports), **DRC-clean + LVS MATCH**. n1 on
      the outer met1 columns, vout on a central li riser (never meet), input
      gates out on li at two heights crossing the met1 tail a layer below.
      LESSON: a standalone-clean sub-block does NOT compose for free — the input
      pair's routing had to be redrawn (drains up, gates down) to face the
      neighbours it connects to; and every S/D must leave on a via landing on a
      real licon stud *inside* the strip (device li stops ~0.27 µm short of the
      nominal edge → an edge via floats; the first attempt lost VDD/VOUT/tail to
      exactly that). `layout/verify.py` green: 9 cells DRC-clean, 6 LVS-matched.
- [x] **Second-stage output cell** (`out_stage`, figure
      `docs/img/layout_out_stage.png`): `xm5` PMOS common-source over `xm6` NMOS
      current sink, drains shared as `VOUT` — the class-A output stage (same
      shape as a CMOS inverter). Extracts to `miller_ota.sp` stage 2 —
      **DRC-clean + LVS MATCH first run** (the 5T-core lessons carried over:
      via-on-stud-inside-strip, gates out the sides / drains up the centre).
      Both active stages of the two-stage Miller amp are now laid out + LVS-clean.
- [x] **Nulling resistor Rz** (`res_rz`, figure `docs/img/layout_res_rz.png`):
      the leg's first passive + first PDK special-marker device — an `xhigh_po`
      precision poly resistor, poly body under `poly_res`(66/13)+`urpm`(79/20)+
      `psdm`, W=0.69 L=3.45 (5 squares). **DRC-clean + extraction-verified at
      R=10000 Ω** (`run_res_extract.py`, wired into `verify.py`). NOT in the LVS
      compare set: the deck extracts the PR resistor as 3-terminal
      `resistor_with_bulk` but its SPICE reader reads `R` as 2-terminal (no
      bulk-resistor reader delegate, unlike the C-VPP path) — so a hand-written
      reference can't pair; extraction (device + value) is the real check.
- [x] **Compensation cap Cc** (`cap_cc`, figure `docs/img/layout_cap_cc.png`):
      a sky130 **MIM** cap (`cap_mim` on met3) — bottom plate met3 (P1), top
      plate `capm` (89/44, P2) contacted up `via3`→met4. New layers met3/via3/
      met4/capm. 10×10 µm plate → **~200 fF** (scaled; full 4 pF Cc ~20× area).
      **DRC-clean + extraction-verified `cap_mim` C=2e-13 F**. Like Rz, it is
      extraction-verified not LVS-compared (the reader delegate only names VPP
      caps; a MIM cap reads back as a generic `C` with a forced default value).
      `run_passive_extract.py` (Rz+Cc) wired into `verify.py`. **Every device of
      the miller_ota now exists in layout.**
- [x] **Full-amp floorplan assembled** (`miller_ota`, figure
      `docs/img/layout_miller_ota.png`): the four verified blocks (5T core +
      class-A output + Rz + Cc) placed as one cell with the **VDD/VSS rails tied**
      across the two active stages on met1 — **DRC-clean**. Each block is
      individually LVS/extract-verified; this assembles them. HONEST: a floorplan,
      not yet a whole-amp LVS — the sub-blocks' pins aren't on abutment edges (VB/
      VOUT/N2 sit mid-cell), so inter-block signal routing is the next step (the
      "doesn't compose for free" lesson at amplifier scale). Added to the README.
- [x] **Inter-stage signal routing** (`miller_ota`): `n2` (stage-1 output →
      `xm5` gate → `Rz.P`) and the shared `vb` (tail diode → sink gate) routed
      **over the cells on met2** (via-stack tap up / cross / drop down — the
      answer to the "doesn't compose for free" lesson at amplifier scale), plus
      the VDD/VSS rails tied. **DRC-clean.** device.py += `via_li_met2` tap.
- [x] **Rz/Cc compensation branch closed** — the amp is now **fully wired**:
      `nz` (`Rz.M`) drops onto the `Cc` met3 bottom plate via a met2→met3 (via2);
      `vout` climbs an isolated met2→met3→met4 stack (left of the plate so it
      never lands on the bottom plate) and crosses on met4 to the `Cc` top plate.
      Every net of `miller_ota` routed, **DRC-clean**. device.py += `via_met2_met3`
      / `via_met3_met4`. Lesson: an isolated upper-metal via island needs a
      min-area met3 patch (m3.6).
- [ ] **Whole-amp post-extraction re-simulation** (decides the silicon; gated on
      the KLayout deep-mode extractor erroring on the big flat cell — try
      hierarchical/per-block) → rail-tie guard rings → production (full-W) sizing.

## Phase 3 — comparator

- [ ] Pre-amp + latch, offset and kickback benches, metastability window

## Phase 4 — SAR ADC

- [ ] Charge-redistribution DAC (capacitor matching is the whole game),
      SAR logic in our own standard cells, ~8–10 bit at audio rates
- [ ] Static (INL/DNL) and dynamic (SNDR/ENOB) benches

## Phase 5 — TT analog slot

- [ ] Standalone validation chip, the way the cartridge Pmod rehearsed
      the memory system before any silicon depended on it
- [ ] Bring-up script, in the shape proven by `tt-cordic/bringup/`

## Phase 6 — console integration

- [ ] Audio path: chiptune voices → DAC → buffer → jack
- [ ] Paddle path: pot → comparator/SAR → CPU register
- [ ] Mixed-signal budget: +2–4 analog pins (~€100–200 over the digital
      tiles)

## Rules for this repo

- `stdcells`, `devphys`, `pmod-cartridge` and `console` are **read-only
  reference** here. Copies with commit provenance, never edits.
- Every quoted number is simulated or measured, with the netlist that
  produced it in the repo. Guesses are labelled as guesses (see the
  "Where it comes from" column in `docs/spec.md`).
- Dead ends get written down in `docs/design-notes.md`, with the data
  that killed them.
