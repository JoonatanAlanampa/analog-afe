# Topology review — the four calls

Reviewed 2026-07-21 (the retry of the pass that died on a model usage
limit). Inputs: [`review-brief.md`](review-brief.md), [`results.md`](results.md),
[`corners.md`](corners.md), [`noise.md`](noise.md), the benches in `tb/`,
and `../research/sky130-analog.md` — a cited deep-research report produced
after the kickoff, whose TinyTapeout platform facts were re-verified
directly against tinytapeout.com/specs/analog/ and which **settles open
question O1 and closes call 4**.

---

## Call 1 — Topology: **two-stage Miller**. Decided.

Not close. At the primary load the single stage is beaten on every axis
that matters and is not rescued by current:

- loaded gain 56.8 dB vs 6.8 dB (20 µA) / 18.3 dB (100 µA, current-matched)
- unity-gain step error −0.115 % vs −33.2 % / −11.7 %
- PSRR 73.5 dB vs 42.4 / 38.4 dB
- slew, worse edge, 1.11 V/µs vs 0.13 / 0.59
- at **less** supply current than the current-matched single stage
  (81 µA vs 91 µA)

The brief's diagnosis is correct and is the reason this is not a bias
question: **a single stage's output resistance is its gain**, so a 10 kΩ
load collapses it by construction. `ota_5t_x5` was the right experiment to
run and it settles the matter — 5× the current buys 11 dB and still leaves
double-digit gain error.

**The 5T OTA is kept, not discarded.** Its shape is right for
high-impedance work: the comparator pre-amp and the SAR ADC's internal
buffer both drive capacitive, not resistive, loads. That work is banked.

## Call 2 — Spec row 5 (≥ 60 dB): **accept 56.8 dB, and rewrite the row**

The brief offers "restate as a gain-error target". I would go further,
because the row is measuring the wrong thing for this application.

For a unity-gain buffer, loop gain sets closed-loop gain error:
56.8 dB → 1/693 = **0.144 %** (measured 0.115 %), against 60 dB → 0.100 %.
The difference is −57 dB vs −60 dB of static gain error on an **AC-coupled
line output**. That is inaudible, and it is not what row 5 was written to
protect — a generic op-amp spec was inherited without asking what the
audio path actually cares about.

What it cares about is **distortion**, which is still unmeasured. Recommend:

- accept 56.8 dB with this reasoning recorded;
- restate row 5 as a **THD target** (a defensible line-level starting point
  is ≤ 0.1 % at 1 kHz into the primary load, 1 V pp);
- **measure THD** — it is now the highest-value unmeasured quantity, ahead
  of CMRR and ICMR, because it is the row that actually guards audio
  quality and no candidate has been tested for it.

## Call 3 — Compensation: **aggressive, Cc 2 pF / Rz 20 kΩ**. Decided.

The corner run is unambiguous and overturns the earlier caution:

| | PM across all corners | UGF | verdict |
|---|---|---|---|
| Cc 2 p / Rz 20 k | **67.4–68.5°** | 7.66–12.5 MHz | meets both targets everywhere |
| Cc 8 p / Rz 2 k | 50.7–54.3° | 2.33–3.11 MHz | **fails 60° at every corner** |

Phase margin varies by under 1.5° across five processes, −40…+85 °C and
±10 % supply. The concern that the lead zero would track gm2 and drift is
empirically answered: it does not, over the box that matters. The
"conservative" alternative is conservative in name only — it fails
nominally and everywhere else.

**One caveat before this is signed off** — see harness finding H1: one row
of the aggressive table (ff/+85 °C) reports an invalid operating point.
That is a bench artifact, not a circuit failure, but the table should be
regenerated with H1 fixed before it is quoted as signoff evidence.

## Call 4 — Scope: **line-level only. Class-AB is ruled out by the platform, not by the design.**

This is the call the new research settles outright.

**A TinyTapeout analog pad is specified at 4 mA maximum** (with < 500 Ω
series, < 5 pF), verified directly against TT's spec page. Driving 32 Ω:

| target | current needed | vs 4 mA pad limit |
|---|---|---|
| 1 V pp (0.5 V peak) into 32 Ω | 15.6 mA | **3.9× over** |
| even 0.3 V peak into 32 Ω | 9.4 mA | 2.3× over |

**No amplifier design fixes this** — the limit is the pad, not the output
stage. Headphone drive is off the table for any TT analog project, so a
class-AB output stage would be effort spent on a capability the platform
cannot deliver. Stop measuring the 32 Ω corner as a pass/fail case; keep it
only as a documented out-of-scope note.

The chip is a **line-level source**; the Pmod's amplifier provides power.
That was already the architecture — it is now justified rather than assumed.

### The coupling capacitor is mandatory, and it solves two problems at once

The brief's finding 5 (the board's ~353 Ω DC path is incompatible with a
mid-rail output; the amp holds 0.69 V there only by drawing 2.03 mA) is
confirmed and sharpened: **2.03 mA is already half the pad's entire
budget** for a DC condition that carries no signal.

With a series output capacitor:
- the DC path disappears (no quiescent pad current);
- AC current into 353 Ω at 0.5 V peak is **1.42 mA — inside the 4 mA
  budget** with margin;
- the measured 3σ input offset of ±12.7 mV lands on the cap, not the jack.

So the cartridge-Pmod consequence is **"add a series capacitor"**, not
"respin the board" — worth confirming against the fabricated board's
actual net (the boards are ordered; a series cap may be addable at the
connector rather than in copper).

## O1 resolved — 3.3 V **is** available, and we should **not** take it

TT offers `VAPWR`, a **3.3 V analog supply rail**, via a different template
(`tt_analog_1x2_3v3.def`, `uses_3v3: true`) alongside `VDPWR` 1.8 V and
`VGND`. The brief flagged this as worth resolving before committing — it is
now resolved, and the answer does not change the design:

1. **The reason to want it is gone.** 3.3 V would restore headroom for a
   PMOS input pair, but the noise bench already refuted the premise: the
   PMOS-input version measures **worse** (28.7 vs 23–24 µV), because
   sky130's NMOS carries ~75 % of the noise whichever way the pair is
   arranged.
2. **The cost is a different design.** A 3.3 V rail requires the 5 V-rated
   device flavors — sky130's 1.8 V FETs are not rated across it — which
   means different minimum lengths, different gm/Id, larger devices, and a
   re-sizing pass. (Verify exact ratings in the PDK device docs; that
   material is flagged as unresearched in the research report.)
3. **It does not help the binding constraint.** Output drive is limited by
   the 4 mA pad, not by supply voltage.

Recommend recording O1 as **closed: 1.8 V VDPWR, single supply**, with the
3.3 V option noted as available-but-rejected and the reasoning above.

Note also from the same source: TT documents **no separate analog supply
domain, isolated ground, or guard-ring provision** — and ~20 mA of draw
produces ~0.1 V of PDN drop. With 81 µA quiescent we are far from that, but
it means **PSRR is doing real work here**, which is another mark in the
two-stage amp's favour (73.5 vs 42.4 dB).

---

## Harness audit (the part the dead review never reached)

**H1 — `bench_op` has no per-run tag; all 34 corner operating points
collide.** In `tb/benches.py`, `bench_op` builds `tag = f"op_{topo}_{load}"`
with no `tag_extra` parameter, while `bench_ac` and `bench_tran` both take
one. `tb/corners.py` calls it 34 times (17 corners × 2 compensation
settings) with identical arguments, so every run reads and writes the same
artifacts.

The symptom is visible in `corners.md`: the **ff/+85 °C row of the
aggressive table reports `--` for V_out and I_supply with all eight devices
flagged out of saturation, while the same corner in the conservative table
reports a clean 0.900 V / 80.9 µA.** Compensation components cannot change
a DC operating point — Cc and Rz carry no DC current — so the two rows must
be identical, and they are not. One of them is a stale or failed artifact.

*Fix*: give `bench_op` a `tag_extra` and pass the corner tag; regenerate
`corners.md`. Until then the operating-point column of that table is not
evidence, and — worse — a genuine saturation failure at some corner could
be masked by a stale good file from the previous run.

**H2 — `bench_psrr` has the same untagged pattern** (`psrr_{topo}_{load}`).
It has not bitten yet because PSRR is only run at nominal, but it will the
first time PSRR is swept over corners or compensation. Fix both together.

**Pattern worth naming**: both this and the step-bench bug the first review
found are the same failure — *a bench reports a number without the run that
produced it being uniquely identified, or without exercising the case that
matters*. Suggested standing rule for this repo: **every bench takes a tag
that includes every parameter that can change its result, and every
asymmetric circuit is measured in both directions.**

## What remains unmeasured

Ranked by how much it could still change a decision:

1. **THD** — now the top item (see call 2); no candidate has been tested.
2. **Input common-mode range / CMRR** — the unity-gain buffer pins V_CM at
   mid-rail, so ICMR is the assumption the whole topology choice rests on;
   it should be measured rather than inferred from the headroom argument.
3. **Monte Carlo across corners** — offset was run at `tt_mm` only
   (σ = 4.24 mV, 3σ ≈ ±12.7 mV, acceptable behind a coupling cap).
4. Layout-dependent effects, parasitics, and the actual TT pad model —
   none of which exist until there is a layout.

## Summary of decisions

| call | decision |
|---|---|
| topology | **two-stage Miller** for the audio buffer; 5T OTA retained for high-Z blocks |
| spec row 5 | **accept 56.8 dB**; rewrite the row as a THD target and measure THD |
| compensation | **Cc 2 pF / Rz 20 kΩ**, after regenerating corners with H1 fixed |
| scope | **line-level only**; class-AB ruled out by the 4 mA pad limit; series coupling cap mandatory |
| O1 (3.3 V) | **closed** — available via `VAPWR`, deliberately not taken |
