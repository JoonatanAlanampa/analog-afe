# Spec — the paddle SAR's comparator

`docs/spec.md` is entirely the audio buffer. This is the second block's spec,
written the same way: every number traced to the job, and the guesses labelled
as guesses.

## Where it sits

The console's controller path is digital (the Gamepad Pmod — see
`memory/gamepad-pmod-receiver-spec.md` in the project vault). A **paddle** is
the period-authentic *analog* input that path cannot carry: a potentiometer
across the rail, read as a voltage.

    pot wiper --> S/H --> charge-redistribution DAC --> THIS COMPARATOR --> SAR logic --> CPU register

So the comparator is not "a comparator". It is the decision element of an 8-bit
SAR, and that fixes almost every number below — most importantly that its input
is the DAC's **top plate**, a node that holds charge rather than a node driven
by a source.

> **Status note (2026-08-02).** The tapeout policy of the same date makes the
> console an FPGA target and leaves `vertical-slice` as the only remaining ASIC
> tapeout, so this block — like the audio buffer — has no silicon destination
> today. The paddle job is still what *defines* the numbers, and they are quoted
> here unchanged; what has gone away is the shuttle at the end, not the
> engineering that sets the targets. See `PLAN.md` phases 5-6.

## Electrical targets

| # | Parameter | Target | Where it comes from |
|---|---|---|---|
| 1 | Supply | 1.8 V, sky130 core devices | the process; same as the buffer |
| 2 | Resolution | 8 bit over 0–1.8 V ⇒ **1 LSB = 7.03 mV** | a pot across the rail; 256 positions ≈ 0.4 % of travel, already finer than a hand on a knob |
| 3 | Decision resolution | resolve **< 0.5 LSB = 3.52 mV** | a comparator that cannot split half an LSB sets the converter's resolution instead of the DAC's matching |
| 4 | Conversion rate | ≥ 1 kSps; phase 4 designs for 50 kSps | a paddle is read once per video frame (60 Hz). 50 kSps is the *audio-rate reach* the leg keeps open, not a paddle requirement — labelled a stretch, not a derivation |
| 5 | Decision rate | 500 kHz ⇒ **~2 µs per bit trial** | 50 kSps × (8 trials + sample + settle) ≈ 10 clocks |
| 6 | Decision delay | ≪ 2 µs, **measured both directions** | design-notes §5: a one-directional stimulus measures the better direction, and a latch's two outputs are pulled by different devices |
| 7 | Systematic offset | **not budgeted** | in a SAR a static offset is a full-scale *shift* of the paddle map — the game centres the paddle anyway. Budgeting it would spend current on the one error this job does not care about |
| 8 | Offset spread σ | **≤ 1 LSB (7.03 mV), 1σ** | so an uncalibrated part stays within ±3 LSB of the 256-code map at 3σ. This is the offset number that matters, and it is a *mismatch* number — Monte Carlo, not one draw |
| 9 | Hysteresis | **< 0.5 LSB = 3.52 mV** | a SAR's successive decisions are *correlated* — a binary search walks toward the answer — so any memory of the previous decision biases the next one and does **not** average out |
| 10 | Kickback into a 1 pF top plate | **< 3.5 fC** (= 0.5 LSB × 1 pF) | the DAC top plate holds the sampled charge; what the comparator pushes back is a conversion error, not a settling nuisance. 1 pF is the phase-4 array's assumed total — a guess until phase 4 sizes it |
| 11 | Input common-mode range | cover the top-plate excursion of phase 4's switching scheme | **coupled to phase 4, deliberately**: classic bottom-plate sampling swings the top plate the full rail on the first trial, V<sub>cm</sub>-based switching a quarter of it. Measured here over the whole rail so phase 4 can choose on data |
| 12 | Metastability | P(unresolved within a 2 µs trial) negligible | not a separate design knob — it falls out of the regeneration time constant τ, which the delay-vs-overdrive sweep measures directly |
| 13 | Average supply current | ≤ 50 µA at the 500 kHz decision rate | a quarter of the buffer's 200 µA budget. Budget, not a derivation |

## What is deliberately *not* here

- **A noise row.** Decision noise matters (it is what makes a comparator
  probabilistic near threshold), but ngspice's transient analysis carries only
  *user-injected* noise sources — device noise is absent from `.tran`. A
  transient "noise" measurement here would therefore report the noise this
  bench injected, not the comparator's. `docs/comparator.md` says what can and
  cannot be claimed instead of quoting a number the tool cannot produce.
- **A slew or bandwidth row.** The pre-amp candidate has both; the bare latch
  has neither, and the comparison is about the decision, not the waveform.

## The constraint carried over from the buffer

sky130's thresholds (~0.63 V NMOS, ~0.9 V PMOS on a 1.8 V rail) are what killed
the PMOS input pair in `docs/design-notes.md` §1. The same arithmetic applies to
row 11: an NMOS-input latch needs its input common mode above roughly
V<sub>th</sub> + V<sub>dsat</sub>, so a switching scheme that drags the top
plate to ground is not merely inaccurate — it is *inoperative*. This is why
row 11 is measured over the full rail before phase 4 commits.
