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
- [x] **Whole-amp connectivity verified by extraction** (`run_amp_extract.py`,
      wired into `verify.py`): the wired amp extracts to **exactly the 10 devices
      of `miller_ota.sp`** (5 NMOS + 3 PMOS + Rz + Cc) with the right nets —
      KLayout merges labels per net, so `n2`=`N2|P|VOUT|n2`, `vout`=`P2|VOUT`,
      `nz`=`M|P1|nz`, `vb`=`VB|vb`. (The earlier "extractor error" was a relative
      *path* bug, not a real failure.) Polarity note: layout reuses ota5t_core
      (`xm1` gate=`vinp`) so `vinp`/`vinn` are swapped vs miller_ota.sp's inverting
      convention — a label choice, topology identical.
- [x] **Substrate body tie** (`miller_ota`): a p+ `tap` (device.py `tap()`, on the
      **tap layer 65/44** — plain diff is DRC-clean but electrically inert) wired
      to the VSS rail ties the whole NMOS bulk to VSS. Extraction confirms all 5
      NMOS **bulk = `VSS|vss_tap`** (was floating `sky130_gnd`); `run_amp_extract`
      asserts it. Deck: `ptap_conn = tap.and(psdm).not(nwell)`; `connect(sub,ptap_conn)`.
- [x] **nwell body ties** (`miller_ota`): an n+ `tap` in each of the two wells
      (stage-1 mirror + stage-2 PMOS), wells widened at the top level for room,
      wired to VDD. Extraction confirms **all 3 PMOS bulk = VDD** (were floating);
      `run_amp_extract` now asserts PMOS→VDD + NMOS→VSS. Deck: `ntap_conn =
      tap.and(nsdm).and(nwell)`; `connect(nwell, ntap_conn)`. **The amp is now
      fully body-tied.** Everything the flow can prove pre-redraw is done + green.
- [x] **Production full-W sizing + parasitic (RC) re-simulation + feedback-sign
      swap — DONE 2026-07-23** (one tapeout-prep redraw pass). Blocks redrawn to
      the taped-out (corner-verified THD-fix) sizing by scaling FINGER WIDTH and
      keeping the proven nf=4 common-centroid interleave for the matched pairs:
      input pair `W=40` (m8), mirror + tail/bias `W=20` (m4), class-A output
      `W=150` (m30, 10 fingers), `Cc = 4 pF` (44.7 µm MIM plate,
      extract-verified), `Rz = 10 kΩ`. The whole-amp extraction now reports
      exactly those widths on all ten devices. **Feedback sign** corrected to
      `miller_ota.sp`'s inverting convention (`VINN`→`n1`, `VINP`→`n2`) and made a
      `run_amp_extract` assertion. **Parasitic RC re-sim** (`tb/parasitics.py` →
      `docs/parasitics.md`): interconnect wire caps extracted from the GDS (planar
      area+fringe, sky130 magic coefficients) — **~14 fF total** (met2 Miller
      trunk + met4 across the cap) vs the **4 pF** Cc, so phase margin moves
      **−0.13°** (81.0°→80.9°, spec 60°/target 65°) and THD is unchanged, even at
      2× pessimistic. `layout/verify.py` green throughout.
      - Still on the shelf: a wider-ICMR input (rail-to-rail / complementary pair)
        for THD < 0.1 % at full 1 Vpp; real poly-R Monte-Carlo signoff.
- [x] **`miller_rrf2` LAID OUT FROM SCRATCH — DONE 2026-07-25** (`layout/
      build_rrf2.py`, `layout/run_rrf2_extract.py`, figure
      `docs/img/layout_miller_rrf2.png`). Closes the design/layout desync: the
      amplifier that actually meets the spec (folded rail-to-rail input +
      self-biased cascoded summing node, robust < 0.1 % THD @1 kHz over full PVT)
      had no geometry, while the drawn `miller_ota` was the superseded circuit.
      **25 transistors + Rz + Cc, 177 × 96 µm (17 070 µm² vs miller_ota's 4 044).**
      Five new blocks — `rrf2_nin`, `rrf2_fold`, `rrf2_cmir`, `rrf2_plow`,
      `rrf2_bias_n`/`_p` — each **DRC-clean + LVS MATCH** against a reference taken
      off `spice/miller_rrf2.sp`; `out_stage` (W=150, same pout=2.5) and `res_rz`
      (10 kΩ) **reused verbatim**; only `cap_cc9` is new (9 pF, 67.08 µm plate,
      extract-verified 8.999 pF). Top level routed as a **two-layer channel** (one
      met3 track per net, one met2 riser per pin, blocks on disjoint x-windows →
      short-free by construction; `_check_risers()` asserts the spacing in Python
      before drawing). Whole-amp **extraction-verified**: 27 devices, **all 14 nets
      proved connected pin-by-pin** via unique per-riser tags (five blocks all call
      the summing node `CB`, so a merged-name check would prove nothing), 4 nwell
      ties + substrate tie, and polarity on **both** input pairs. `miller_ota` and
      its layout are UNTOUCHED; `layout/verify.py` runs both amplifiers green.
      - Deliberately NOT reopened: the 20 kHz band-top (0.11–0.23 % over corners,
        never robust in any version — beyond this topology on 1.8 V; spec point is
        1 kHz).
- [x] **PARASITIC RC RE-SIM OF THE rrf2 LAYOUT — DONE 2026-07-25**
      (`tb/parasitics_rrf2.py` -> `docs/parasitics-rrf2.md`). **It found a real
      spec failure, which is the point of running it.** Extracted **296.6 fF**
      of interconnect from `miller_rrf2.gds` (21x miller_ota's 14 fF; seeds
      GENERATED from `build_rrf2.TAPS`/`.TRACK` so no wire can be missed, zero
      misses). Nominal PM 73.3 -> 70.1 deg. But over the full PVT grid the
      **worst-corner PM falls to 59.7 deg at tt/+25 C/1.98 V — UNDER the 60 deg
      spec of row 8**, which `tb/run.py` asserts: rrf2 was signed off with 2.8
      deg of margin at that corner while its own layout costs 3.1 deg. THD is
      untouched (0.057 % nominal, 0.092 % at ff/+85 C, both with parasitics).
      - **The failing corner is HIGH SUPPLY (+10 %), not a temperature extreme**
        (more supply -> more gm -> higher UGF -> less margin). THD is bounded by
        the temperature corners. Two different corners bound this amplifier.
      - **PREDICTION REFUTED BY MEASUREMENT** (per-net sensitivity): I expected
        `cb` to be nearly free behind the 9 pF Cc and the damage to be on the
        fold nodes. Measured, **`cb` is 62 % of the loss** (-1.95 deg of -3.13).
        Cause: `Rz` is in SERIES with `Cc`, so above 1/(2*pi*Rz*Cc) = 1.8 MHz the
        Miller branch sits at its resistive 10 k floor and does NOT shunt `cb` at
        the 18 MHz UGF. The same property that made Rz the PM lever (design-notes
        7) is what exposes the node here.
      - **Cost tracks SIGNAL PATH, not capacitance**: 103 fF on cb/ca/fa/fb costs
        -3.15 deg; **193 fF on the eight bias/input nets costs 0.00 deg** (`vb`
        carries 42.5 fF for nothing). Loading superposes linearly.
      - **Cc is a WEAK lever**: 9->13 pF buys only 1.0 deg at the worst corner and
        costs 3.1 dB of 20 kHz loop gain; 10 pF "clears" at 60.1 deg = 0.1 deg on a
        planar estimate, i.e. a rounding error. The real lever is the LAYOUT —
        cb/ca/fa/fb connect ADJACENT blocks and never needed the channel at all.
      - Also quantified: routed length 3 030 um splits 2 470 um of risers vs 561 um
        of track, and riser length is set by the TALLEST BLOCK (rrf2_plow, 74 um),
        so one tall block taxes all 37 pins.
      - NOTHING APPLIED: both fixes (bigger Cc / re-route four nets) are design
        decisions that move a corner-verified operating point or need a layout
        re-verify. Measured and priced, left to the user.
      - `--report` re-renders the doc from `out/parasitics_rrf2.json` without
        re-simulating (same convention as `tb/sweep_comp.py`).
- [x] **THE PM FAILURE IS FIXED — IN THE LAYOUT, NOT THE NETLIST (2026-07-25).**
      The sensitivity said cb/ca/fa/fb carry 100 % of the cost and connect
      ADJACENT blocks, so their met3 tracks were dropped DOWN among those blocks
      (`build_rrf2.TRACK`: CA 16.0, FA 31.5, CB 33.0, FB 34.5) while the eight
      nets that cost 0.00 deg stay in the high channel. Signal-path wire
      **750 -> 192 um**, signal-path C **103.5 -> 39.5 fF**.
      **Worst-corner PM 59.7 -> 61.6 deg = PASSES row 8, and 60.5 deg at 2x
      pessimistic** (which the first routing failed even at Cc = 13 pF).
      Loop gain, THD, area, Iq and the operating point are ALL unchanged —
      the fix cost nothing. `layout/verify.py` + the 14-net extraction check
      stay green; DRC clean first try.
      - **ROOT CAUSE was a habit, not a constraint**: the channel floor had been
        put above the TALLEST block (rrf2_plow, 74 um) because that is what a
        channel looks like — but the blocks use only li/met1, so **met3 is free
        over every one of them** and a track never had to clear anything. All 37
        pins were climbing ~67 um for a clearance that does not exist.
      - **Bigger Cc was the obvious alternative and is REJECTED ON THE DATA**:
        10 pF clears by 0.1 deg on a planar estimate, still FAILS at 2x, and costs
        0.9 dB of 20 kHz loop gain; 13 pF reaches only 60.7 deg (57.8 at 2x) while
        spending down to 42.9 dB against the 40 dB floor of row 6.
      - Two bugs the change would have introduced, caught: riser labels were
        placed at a fixed offset BELOW the track, which lands on nothing once a
        pin sits above its track (the silent-hole trap again) -> now at the riser
        midpoint; and `wire_lengths()` summed a SIGNED delta, so downward risers
        cancelled upward ones and under-reported by 64 um -> now abs().
      - docs/parasitics-rrf2.md keeps the failure, the fix and the rejected
        alternative side by side (`FIRST` constants pin the pre-fix numbers to
        commit 788b5d6); spec.md row 8 now reads PASSES for rrf2.

## Phase 3 — comparator — DONE 2026-08-02

Spec first (`docs/spec-comparator.md` — `docs/spec.md` was entirely the audio
buffer), then both candidates benched: `spice/strongarm.sp` (bare latch) and
`spice/comparator.sp` (a pre-amp in front of *that same latch file*). Results
and method in `docs/comparator.md`; bench `tb/comparator.py`.

- [x] **The pre-amp earns its current — on KICKBACK, not on offset.** The bare
      latch pushes **49.3 fC** into the 1 pF top plate and keeps it (peak and
      residual are the same number, because a charge-holding node has nowhere
      to put it) against a **3.5 fC** budget — over by 14×. The pre-amp, with
      the same latch behind it, gives **1.04 fC peak and ~0 residual**, a 47×
      reduction, because it is continuously biased and so presents no
      evaluation transient to its input at all.
      ⚠ **THAT PAIR OF NUMBERS IS MEASURED AT THRESHOLD, WHERE KICKBACK IS
      SMALLEST.** Phase 4 sent the measurement back and the sweep changed the
      margin: over the full input range the bare latch reaches **−136.7 fC**
      (39× over) and the pre-amp **−8.48 fC** (2.4× over, one-sided — it stays
      at ~0 for positive overdrive). The pre-amp still wins by 16× at each
      candidate's worst point, but **neither holds the budget everywhere**, and
      "comfortably inside 3.5 fC" was an artefact of the operating point chosen.
      MECHANISM, and it is the same decision twice: the input pair is long and
      wide *because* offset is mismatch and mismatch scales as 1/√(WL) — and
      that same large gate is what couples the transient in. **The sizing that
      buys matching buys kickback.**
- [x] **Offset**, by decision probability rather than by threshold search: each
      instance in a netlist draws its own mismatch, so K copies in one run are K
      devices, and sweeping the overdrive across runs measures P(decide +),
      whose probit fit *is* the offset distribution. 504 device samples per
      candidate instead of the ~20 a bisection loop would have afforded.
      RESULT, and it contradicts the reason usually given for a pre-amp:
      σ = **3.07 mV** bare vs **6.86 mV** with the pre-amp. It divides the
      latch's offset by a gain of only a few and then adds its own pair *and*
      its small diode loads. Against the 1 LSB (7.03 mV) budget that leaves
      2 % of margin — **the clearest open item this phase leaves.**
- [x] **Metastability is a non-issue by ~10³.** Delay grows logarithmically as
      it must; the slowest decision measured is **2.6 ns at 1 µV** of overdrive
      against a 2 µs trial. Quoted over the clean decades only — below ~0.1 mV
      the curve flattens because the solver's tolerance, not the latch, breaks
      the tie there.
- [x] **Both directions**, per design-notes §5 — and the 1.46× asymmetry the
      bare latch shows is *the SAR's*, not the latch's: only one comparator
      input moves in a charge-redistribution SAR, so ±100 mV is also two
      different common modes and the tail is stronger at the higher one.
- [x] **Common-mode range (spec row 11) passes over the whole rail**: sweeping
      the top plate 0.05 → 1.70 V against the fixed reference, both candidates
      decided correctly at 34/34 points. The classic scheme survives on 1.8 V
      because the extreme common modes coincide with the largest differentials
      — the uncomfortable trial is the one asking for the least resolution.
- [x] A correction to `topology-review.md` that the drafting turned up and the
      bench then relied on: the banked 5T OTA **cannot** be the pre-amp. It is
      single-ended by construction and a StrongARM needs a differential drive;
      the pre-amp uses diode-connected PMOS loads instead. What was really
      banked was the input pair, not the OTA.

## Phase 4 — SAR ADC — DONE 2026-08-02

`spice/cdac8.sp` + the phase-3 comparator + SAR sequencing in XSPICE digital
primitives, so a whole conversion (sample, eight trials, read-out) is ONE
transient. Results in `docs/sar.md`; bench `tb/sar.py`.

- [x] **It converts — and after the race below was fixed, it converts
      EXACTLY: all 256 codes correct, 0 failed conversions, gain error 0.00 %,
      INL 0.00 LSB over the sampled curve, SNDR 50.26 dB → ENOB 8.06 bits.**
      (Read the ENOB as "no distortion measurable above quantization" — a
      64-point coherent record makes quantization error deterministic rather
      than white, which is why it lands just above the 49.9 dB ideal. The
      transfer curve is the stronger claim.)
- [x] **Phase 3's verdict reproduced from the other side**: same array, same
      sequencing, comparator swapped — the bare latch returns code 139 for a
      mid-scale input with the residue stuck at +70 mV (49.3 fC on 1.26 pF is
      39 mV per trial), the pre-amp returns 128 with zero error.
- [x] **Charge-redistribution DAC** from 256 unit cells of the PDK's own MIM
      capacitor, so matching is a PDK number rather than an assumption.
      Unit 4.9298 fF, array 1.262 pF.
- [x] **Static (INL/DNL) and dynamic (SNDR/ENOB) benches** — plus the
      distinction that makes them mean different things: a DAC sweep walks the
      code and lets the top plate visit the whole rail, while a *conversion*
      always ends at V<sub>cm</sub>, so a nonlinear-parasitic bow largely
      cancels in the converter and capacitor mismatch does not.
- [ ] **SAR logic in our own standard cells** — deliberately NOT done here.
      Modelling the logic as ideal digital is what makes INL/DNL/ENOB depend on
      the array and the comparator alone; mapping the same sequencing onto
      `stdcells` is a separate, checkable step and the timing it must meet is
      printed by the bench.

### Three findings from phase 4 that outlive it

- **A 200 ps race cost 21 LSB, and only an end-to-end simulation could see it.**
  The pointer flop's clk_delay plus the bridge's rise time put the MSB control
  ~0.2 ns behind the clock edge, so releasing the bottom plates on that same
  edge left the array at **code 0** for 200 ps — and at code 0 the top plate
  sits at V<sub>cm</sub> − V<sub>in</sub>, which is **negative** for any input
  above mid-rail. That forward-biases the sampling switch's junction to the
  substrate and dumps sampled charge, permanently. Symptom: codes 0-220 exact,
  then a one-sided error growing to −10 LSB. Fix: release the bottom plates
  *after* the code is established. General form — in a charge-redistribution
  converter the array must never sit at a code that drives the top plate outside
  the rails, not even for one gate delay, because the node is floating and the
  rails are diodes.

- **sky130 ships the MIM capacitor twice and the two disagree about matching by
  6×** (0.47 %·µm in `libs.tech/combined`, which this repo loads, vs 2.8 %·µm
  via `libs.tech/ngspice`), about the multiplicity parameter's name, and about
  whether there is a perimeter term. Worse, `.include`-ing the other definition
  is silently *ignored* — ngspice keeps the first and prints only a warning, so
  the netlist can appear to say one thing and simulate another.
- **A binary array must be built from identical unit cells, and it is worth
  9.5 % on the MSB.** The model biases each edge by 0.15 µm, which does not
  scale with the drawing: 128 unit cells = 631.0 fF, one 128×-long capacitor =
  571.2 fF. That is ~24 LSB of DNL, from a choice that looks like bookkeeping.

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
