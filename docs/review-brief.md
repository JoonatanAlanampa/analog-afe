# Topology review brief

Everything needed to decide, in one page. Numbers from
[`results.md`](results.md) and [`compensation.md`](compensation.md); no
decision is made here.

## Review status: INCOMPLETE

A first adversarial review pass ran and **terminated early on a model
usage limit**, before delivering any of the four calls below. It got far
enough to find one real bench bug, which has been fixed and is recorded
as §5 of [`design-notes.md`](design-notes.md):

> The step bench only measured the rising edge. These are class-A output
> stages, so the two directions are driven by different devices —
> `miller_ota` sinks through a 61.5 µA current source, making the
> falling edge the limited one. Its slew advantage at the primary load
> was overstated **2.6×** (2.85 → 1.11 V/µs), and at the headphone
> corner it **flips from PASS to FAIL** on spec row 9 (0.098 vs
> 0.1 V/µs) — a PASS that existed only because the bench never asked the
> amplifier to pull down.

Everything below has been updated for that. **The four calls remain
unmade, and the harness audit is unfinished** — one bug was found by a
review that did not get to finish looking, which is not evidence that it
was the last one.

## The question

Which topology should become the console's audio output buffer:
a single-stage 5T OTA, or a two-stage Miller op-amp? And at what bias?

## The comparison, at the primary (`line`) load

| | `ota_5t` (20 µA) | `ota_5t_x5` (100 µA) | `miller_ota` (80 µA) | spec |
|---|---|---|---|---|
| intrinsic gain (`open`) | 40.1 dB | 40.3 dB | **75.6 dB** | ≥ 60 dB |
| gain into the load | 6.8 dB | 18.3 dB | **56.8 dB** | ≥ 60 dB |
| UGF | 589 kHz | 2.65 MHz | **5.9–9.6 MHz** | ≥ 2 MHz |
| phase margin | 119° | 97° | 26° untuned, **68–92° tuned** | ≥ 60° |
| PSRR @ 1 kHz | 42.4 dB | 38.4 dB | **73.5 dB** | ≥ 40 dB |
| slew (worse edge) | 0.13 V/µs | 0.59 V/µs | **1.11 V/µs** | ≥ 0.1 V/µs |
| unity-gain step error | −33.2 % | −11.7 % | **−0.115 %** | — |
| supply current | 19 µA | 91 µA | 81 µA | ≤ 200 µA |

## What the data actually says

1. **The single-stage OTA is not gain-limited, it is drive-limited.**
   Its intrinsic gain is a respectable 40 dB, but a 10 kΩ AC load
   collapses it to 6.8 dB, because a single stage's output resistance
   *is* its gain. Current-matching it at 100 µA (`ota_5t_x5`) buys 11 dB
   and still leaves a −11.7 % gain error in a unity-gain buffer. **This
   is a topology limit, not a bias limit** — that is what the
   current-matched variant was run to establish.

2. **The two-stage amp meets every spec row at the primary load except
   one, and that one is arguable.** Loaded gain is 56.8 dB against a
   60 dB target — but row 5 of `spec.md` exists to bound gain error, and
   the measured closed-loop step error is 0.115 %, better than the
   0.1 %-class accuracy the row was written to guarantee. Either the row
   should be restated as a gain-error target, or 56.8 dB should be
   accepted with that reasoning recorded. **Reviewer's call.**

3. **The compensation point is not settled.** Several (Cc, Rz) pairs
   clear both PM and UGF. The highest-UGF one sits at Rz = 16 × 1/gm2,
   which is a lead compensator relying on a gm2-tracking zero — exactly
   what PVT and mismatch break. The conservative points near
   Rz ≈ 1/gm2 = 1248 Ω (8 pF / 2 k → 71.7°, 2.9 MHz; 4 pF / 5 k →
   53.1°, 4.3 MHz) trade UGF for robustness. **Reviewer's call**, and it
   should probably wait for phase-1 corner runs.

4. **Nobody drives 32 Ω, and nobody should be expected to.** Every
   candidate's gain error at the headphone corner is −67 % or worse, and
   with both edges measured the two-stage amp also misses the slew row
   there (0.098 V/µs, limited by its 61.5 µA output sink). The
   real question this raises is a scoping one: is the chip's output
   line-level (leaving power to the Pmod's amplifier), or does it need
   a class-AB output stage — a different design, not a tuning change?

5. **The board's existing RC network is incompatible with a mid-rail
   analog output.** It presents ~353 Ω at DC; the two-stage amp only
   holds 0.69 V there by drawing 2.03 mA, 10× the quiescent budget.
   Needs an output coupling capacitor or a board respin. This is a
   conclusion about the *cartridge Pmod*, reached from a transistor-level
   simulation of the chip.

## What is NOT yet known (and would change the answer)

- ~~**Noise.**~~ **MEASURED — and it removes an argument.** See
  [`noise.md`](noise.md) and `design-notes.md` §6. All candidates land
  at 23–24 µV rms input-referred (20 Hz–20 kHz), ~4× under spec row 13
  and ~83 dB SNR against a 1 V pp signal. Three consequences for this
  decision: (a) the flicker caveat that hung over the NMOS pair is
  **refuted** — the PMOS-input version is *worse* (28.7 µV), because
  swapping the pair swaps the load and sky130's NMOS carries ~75 % of
  the noise either way; (b) noise does **not** discriminate the two
  topologies (24.4 vs 24.3 µV; the whole second stage adds 0.4 %), so
  the call rests on drive; (c) bias current is not the lever — 5× the
  current buys 1.6 µV, because flicker scales with device *area*.
- **Distortion (THD), CMRR, input common-mode range.** Unmeasured.
- **PVT corners and Monte Carlo mismatch.** Everything above is one
  nominal `tt` 25 °C run. Offset in particular is unmeasured, and a
  unity-gain audio buffer's offset lands straight on the output as a DC
  shift into the coupling cap. This is now the **largest** remaining
  unknown, and it also decides open call 3 — whether the high-Rz
  compensation point survives corners, or whether the conservative
  Rz ≈ 1/gm2 points are the only defensible ones.
- **O1 in [`spec.md`](spec.md): the TT analog slot's supply domain.**
  If 3.3 V is available, the headroom constraint that shaped both
  candidates relaxes and a PMOS input pair (quieter) returns to the
  table. This is worth resolving *before* committing to a topology.

## If a decision is wanted now

The data supports the two-stage amp for the audio buffer on drive and
PSRR, at comparable current to a current-matched single stage. The 5T
OTA remains the right shape for a *high-impedance* job — which is what
the comparator's pre-amp and the SAR ADC's internal buffer will be, so
it is not wasted work.
