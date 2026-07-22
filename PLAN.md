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

## Phase 1 — close the op-amp (after the review)

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
      Cc/Rz retune**, not a knob (`design-notes.md` §11). Not yet applied:
      picking a (pout, Cc, Rz) point and re-running `corners.py` on it.
- [ ] CMRR, input common-mode range (ICMR) sweep
- [x] **Corners: ss/ff/sf/fs × −40/25/85 °C ± 10 % supply, and Monte
      Carlo offset** (`tb/corners.py` -> `docs/corners.md`). Settled the
      compensation call: the Rz = 20 k lead point is the MOST corner-
      stable (PM 67.4-68.5° across the box), the textbook Rz ≈ 1/gm2
      point fails 60° everywhere — the kickoff's caution had the
      mechanism backwards (`design-notes.md` §7). Offset σ = 4.24 mV,
      3σ ≈ ±12.7 mV: negligible for this buffer, first-order for the
      comparator/SAR (§8).
- [ ] Bias generator (constant-gm / beta-multiplier) with a start-up
      circuit, replacing the ideal external current source (`spec.md` O2)
- [ ] Resolve O1: TT analog-slot supply domain, pad and ESD path

## Phase 2 — layout

- [ ] Reuse the `stdcells` toolchain (gdstk + official KLayout decks +
      magic views) for analog layout: common-centroid input pair,
      dummy devices, guard rings, matched routing
- [ ] DRC + LVS + post-extraction re-simulation. Post-layout is where
      analog designs go to die; budget for it accordingly.

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
