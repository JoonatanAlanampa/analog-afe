# Design notes — measured facts and dead ends

Kept in the repo because the dead ends are the expensive part. Every
number here came out of `ngspice` with the sky130 `tt` models; the raw
logs land in `out/` (gitignored, regenerate with `python tb/run.py`).

## 1. The PMOS input pair does not work at mid-rail on 1.8 V

The first version of both candidates used a PMOS input pair — the
textbook choice, because the sky130 pfet has the quieter flicker corner
and audio is a flicker-noise band.

It failed, and the operating point said exactly why:

| device | role | I_D | V_ds | V_dsat | verdict |
|---|---|---|---|---|---|
| `xmb` | bias diode | 20.00 µA | 1.160 V | 0.164 V | saturated |
| `xm0` | **tail source** | **3.87 µA** | **0.019 V** | 0.164 V | **triode** |
| `xm1/xm2` | input pair | 1.9 µA | 1.2 / 0.89 V | 0.053 V | saturated |

The tail was asked for 20 µA and delivered 3.87 µA, because it only had
19 mV across it. The arithmetic is not subtle:

    V_tail = V_CM + |V_gs| = 0.9 + 0.88 = 1.78 V,  V_dd − V_tail = 0.02 V

A unity-gain buffer forces its input common mode to equal its output,
and an audio output sits at mid-rail — so V_CM = 0.9 V is not a choice
that can be traded away. A PMOS pair's input common-mode range tops out
around V_dd − |V_th| − V_dsat ≈ 0.7 V, and mid-rail is outside it.

**Root cause, and it generalises:** sky130's thresholds are ~0.63 V
(nfet) and ~0.9 V (pfet) against a 1.8 V rail — 35 % and 50 % of the
supply. Headroom, not gain and not noise, is the first-order constraint
of every analog block on this process. Any topology argument that starts
from a 5 V-era textbook figure is wrong here before it starts.

**Fix:** NMOS input pair, PMOS mirror load. V_tail = V_CM − V_gs =
0.9 − 0.64 = 0.26 V, and the tail sink has 0.26 V against a 0.09 V
V_dsat — 0.17 V of margin. Confirmed: tail now delivers 18.99 µA of 20,
all devices saturated.

**Cost, stated honestly:** the NMOS is the noisier device in the flicker
band, which is precisely the band this block works in. Input-referred
noise is therefore a phase-2 bench, not an afterthought — and if it
fails, the escape routes are a larger input pair area (1/f goes as
1/WL), chopping, or O1 in `spec.md` (a 3.3 V rail would put the PMOS
pair back on the table).

## 2. A resistive load must be modelled with its coupling capacitor

The first load model was 10 kΩ DC-coupled to ground. It pulled the
output to 0.196 V and made the amplifier look broken.

0.196 V = 20 µA × 10 kΩ. The bench was asking a 20 µA amplifier to hold
mid-rail across a resistor to ground, which is a DC operating-point
question, not an amplifier question — no audio circuit is wired that
way. The board's 47 µF coupling cap is what makes the resistance an AC
load only, and putting it in the model moved the output to 0.898 V.

The lesson is the same class as the one in `devphys` (scoring two models
on windows defined by their own parameters): **a testbench that omits
part of the real circuit does not measure a worse version of it, it
measures a different circuit.**

## 3. What the `pmodrc` corner is actually for

`pmodrc` is the cartridge Pmod's network exactly as built and DC-coupled,
because the digital buffer it would replace drives it that way — through
120 Ω + 33 Ω into a 200 Ω trim, i.e. ~353 Ω to ground.

It is included expecting failure, and the failure is quantitative:

- `ota_5t` (20 µA) collapses to **6.7 mV** — it has no DC drive at all.
- `ota_5t_x5` (100 µA) reaches **31 mV**.
- `miller_ota` holds **0.69 V** by pulling **2.03 mA** — an order of
  magnitude over the 200 µA quiescent budget in `spec.md`, and only
  because its class-A output stage is being asked to source DC forever.

So: reusing the existing board network with a mid-rail analog output
requires a coupling capacitor at the op-amp output, or a board respin.
That is a conclusion about the *board*, obtained from a transistor-level
simulation of the chip — which is the sort of thing this whole leg exists
to be able to do.

## 4. The two-stage candidate had to be tuned before it could be judged

The first `miller_ota` run (Cc = 2 pF, Rz = 2 k, arrived at from
Rz ≈ 1/gm2 with a guessed gm2) came back with **26° of phase margin and
32 % overshoot** into the primary load. Reporting that against a
single-stage amp would have been comparing a topology against a strawman
— an untuned two-stage amplifier is a tuning result, not a topology
result.

`tb/sweep_comp.py` sweeps Cc × Rz (compensation is a `.subckt`
parameter, so no netlist is edited) and the answer is in
[`compensation.md`](compensation.md): the candidate comfortably clears
both the UGF and phase-margin rows of the spec — several points do.

**Two traps in that table, both recorded there:**

- `Rz = 0` returned −137 dB of gain. ngspice clamps a zero-value
  resistor to 1e−12 Ω, and the resulting 1e12 S matrix entry destroys
  the conditioning. A numerical failure wearing the costume of a circuit
  result; the sweep now starts at 100 Ω.
- Sorting by UGF picks Rz = 20 k, which is **16 × the measured
  1/gm2 = 1248 Ω**. That is not pole-zero cancellation, it is a lead
  compensator — and the whole Rz = 20 k column lands on ~9.3 MHz
  regardless of Cc, the signature of the compensation branch feeding
  *forward* around the second stage. It works in this one nominal
  simulation and depends on a zero that tracks gm2, so it is precisely
  what PVT and mismatch break. The conservative points near Rz ≈ 1/gm2
  (8 pF / 2 k, 4 pF / 5 k) are flagged for the review instead of
  quietly chosen.

## 5. The step bench only measured the easy direction

Found by the review pass, and it changed a spec verdict.

The transient bench stepped 0.9 → 1.0 V and stopped. But these are
class-A output stages: the two directions are driven by *different
devices*. `miller_ota` sources through `xm5`, a PMOS common-source that
can pull hard, and sinks through `xm6`, a current sink pinned at
61.5 µA. Slewing down into a load is therefore the limited direction,
and a rising-only step never touched it.

Measured after stepping both ways (`slew_v_per_us` is now the worse
edge, with both reported):

| candidate | load | rise | fall | asymmetry |
|---|---|---|---|---|
| `ota_5t` | line | 0.132 V/µs | 0.150 V/µs | 1.1× |
| `ota_5t_x5` | line | 0.589 V/µs | 0.601 V/µs | 1.0× |
| `miller_ota` | line | 2.85 V/µs | **1.11 V/µs** | **2.6×** |
| `miller_ota` | phone | 0.457 V/µs | **0.0978 V/µs** | **4.7×** |

Two consequences:

- The two-stage candidate's slew advantage at the primary load was
  **overstated by 2.6×**. It still passes the spec row comfortably.
- At the headphone corner it now **fails** row 9 (0.098 vs 0.1 V/µs).
  It was previously recorded as passing at 0.471 V/µs — a PASS that
  existed only because the bench never asked the amplifier to pull
  down. This strengthens the class-AB argument in
  [`review-brief.md`](review-brief.md) with evidence rather than
  intuition.
- The single-stage OTAs are symmetric, as expected: their output node is
  driven by a differential pair against a mirror, and both directions
  are bounded by the same tail current.

**The general form:** when a circuit's two directions are driven by
different devices, a one-directional stimulus measures the better one.
The same trap is waiting in the comparator (rising vs falling
propagation delay) and the SAR ADC (charge vs discharge settling).

## 6. The flicker-noise caveat was wrong, and measuring it says so

§1 ends with a promise: the NMOS pair was forced by headroom, it is the
noisier device in the flicker band, so noise is an explicit bench rather
than a shrug. That bench now exists (`tb/noise.py`,
[`noise.md`](noise.md)) and it **refutes the caveat**.

| candidate | V_CM | input-referred, 20 Hz–20 kHz | SNR vs 1 V pp |
|---|---|---|---|
| `ota_5t` (NMOS pair) | 0.9 V | 24.4 µV rms | ~83 dB |
| `ota_5t_x5` (NMOS, 5× bias) | 0.9 V | 22.8 µV rms | ~84 dB |
| `miller_ota` (NMOS pair) | 0.9 V | 24.3 µV rms | ~83 dB |
| `ota_5t_pmos` (PMOS pair) | 0.5 V | **28.7 µV rms** | ~82 dB |

Four things fall out, all measured:

1. **The PMOS-input version is not quieter — it is worse** (28.7 vs
   24.4 µV). The reason is in the per-device table, not in an argument:
   swapping the input pair also swaps which device is the *load*. In the
   NMOS-input design the pair dominates (xm1+xm2 = 76 % of output noise
   power); in the PMOS-input design the dominant contributors are
   xm3/xm4, the **NMOS mirror loads**, at 73 %, while the PMOS pair
   contributes only 26 %. Either way sky130's NMOS flicker noise carries
   ~75 % of the total — the only question is whether it enters through
   the pair or through the mirror, and through the mirror it is worse
   here. **The headroom decision cost nothing in noise.**

2. **Noise does not discriminate the topologies.** 24.4 µV single-stage
   vs 24.3 µV two-stage; the entire second stage contributes 0.4 %. One
   argument fewer for the topology review to weigh — the decision rests
   on drive, as [`review-brief.md`](review-brief.md) says.

3. **Current does not buy quiet.** 5× the bias moves 24.4 → 22.8 µV.
   Flicker noise is set by device *area* (∝ 1/WL), not by bias, so the
   lever is a bigger input pair, not a bigger tail. Worth knowing before
   anyone spends current trying to fix noise.

4. **The whole audio band is flicker-dominated.** The 1/f corner is
   above 20 kHz for every candidate — at the top of the band 1/f noise
   is still 3.7–7.4× the thermal floor. So the noise is coloured across
   the entire band, not just its bottom octaves.

**But the totals pass with ~4× margin** (spec row 13 is 100 µV), and
~83 dB SNR against a 1 V pp signal is roughly 35 dB more than 8-bit-era
console audio can use. Noise is not a risk for this application.

Three honest limits on that conclusion: the figure is **unweighted**
(A-weighting would flatter it); it rests on the PDK's flicker
parameters, which are the least trustworthy part of any model set and
are exactly what silicon will contradict; and **input offset from
mismatch is a different question entirely** and still unmeasured — in a
unity-gain buffer it lands straight on the output as a DC shift into the
coupling cap.

## 7. The compensation caution was aimed at the wrong point

The kickoff flagged the highest-UGF compensation point (Rz = 20 kΩ,
16× the measured 1/gm2) as suspect: it is a lead compensator whose zero
tracks gm2, and gm2 moves over PVT, so the nominal ranking "might not be
the real one." The corner run ([`corners.md`](corners.md)) tested that,
and it was wrong — in the reassuring direction.

Three compensation points, `miller_ota`, across five process corners ×
{−40, 25, 85} °C × ±10 % supply (33 corners each):

| point | Rz vs 1/gm2 | nominal PM | **worst-corner PM** | verdict |
|---|---|---|---|---|
| Rz 20 k ("aggressive") | 16× | 68.3° | **67.4°** (fs/−40 °C) | ✅ every corner |
| Rz 5 k ("moderate") | 4× | 71.7° | **68.6°** (ss/+85 °C) | ✅ every corner |
| Rz 2 k ("conservative") | 1.6× | 51.7° | **50.7°** (ss/+85 °C) | ❌ fails 60° everywhere |

What this actually shows:

- **The 20 kΩ lead compensator is the most corner-STABLE of the three.**
  Its phase margin moves less than 1.5° across the entire box
  (67.4–68.5°). The feared gm2-tracking-zero fragility did not appear —
  because Rz ≫ 1/gm2 makes the compensation a lead network whose
  corner frequency is set by Rz·Cc (both passives, which track far
  better than gm2), not by a delicate pole-zero cancellation. The
  caution had the mechanism backwards.

- **The point near the textbook Rz = 1/gm2 (2 kΩ) does not meet phase
  margin at all** — 50.7–51.7° everywhere. On this process, at this
  bias, pole-splitting compensation is simply not available: gm2 is too
  low relative to the load pole to place the second pole beyond the UGF.
  Buying it back needs more output-stage current, which is a design
  change, not a component value.

- **This corrects a real error in `review-brief.md`.** An earlier
  version offered "8 pF / 2 k → 71.7°" as a conservative alternative;
  71.7° is `8 pF / 5 k`, and 8 pF / 2 k is 51.7° — a misread of the
  sweep table that recommended a point which fails the spec. The
  correction is now in the brief, backed by this table.

**Bottom line for the review:** the compensation choice is between the
20 kΩ and 5 kΩ points, both corner-robust, and the tie-breaker is UGF
(20 kΩ gives 7.7–12.5 MHz, 5 kΩ gives 2.5–3.5 MHz — the 20 kΩ point has
far more loop gain left at 20 kHz, which is what suppresses audio
distortion, spec row 6).

## 8. Input offset from mismatch is small, and it costs headroom not audio

Monte Carlo, `tt_mm` corner, 30 draws, unity-gain buffer
([`corners.md`](corners.md)): input offset **σ = 4.24 mV, mean +0.90 mV,
3σ ≈ ±12.7 mV**, worst single draw 8.2 mV.

Why it is not a problem here, and where it would be:

- In this **unity-gain audio buffer** the offset is a DC shift on the
  output, and the output feeds the jack through the board's 47 µF
  coupling capacitor. So ±12.7 mV of 3σ offset does not reach the
  speaker — it costs 2.5 % of the 0.5 V peak output swing as headroom,
  which is negligible against the other margins.
- It would matter enormously in the **comparator and SAR ADC** this leg
  builds next: 12.7 mV of offset is ~0.6 LSB at 8 bit over a 1.8 V range
  and > 2 LSB at 10 bit. Those blocks will need offset cancellation
  (auto-zero / chopping), and this number is the reason to budget for it
  now rather than discover it in silicon.
- The 30-draw σ is itself uncertain (σ on σ ≈ σ/√(2N) ≈ 13 %); it is a
  sizing signal, not a signoff number. A real offset signoff wants a few
  hundred draws and the layout's actual common-centroid matching, which
  is a phase-2 (post-layout) task.

## 9. H1/H2 — an untagged bench masked a failed run as a circuit result

Caught by the topology review's harness audit
([`topology-review.md`](topology-review.md)), and it is the same class of
bug as §5's one-directional step: **a bench reporting a number without
the run that produced it being uniquely identified.**

`bench_op` and `bench_psrr` built their artifact tag from `topo` and
`load` only — no `tag_extra` — while `bench_ac` and `bench_tran` both
took one. So every corner in a `corners.py` sweep wrote the same
`op_miller_ota_line.{sp,log}`, overwriting the previous corner's files.

The returned *numbers* were never corrupted (they are parsed from each
run's stdout, not from the file), and re-running with per-corner tags
reproduced the compensation verdicts **byte-identical** — the aggressive
point was never actually mis-measured. But two real problems remained:

1. **A failed run was silently rendered as a circuit result.** The first
   `corners.md` showed ff/+85 °C under aggressive compensation as
   `-- V / -- µA / all 8 devices out of saturation`. That row was not a
   marginal corner — it was an operating-point analysis that produced no
   readable output that one time, and the `sat_margin > 0` test turned
   its NaN `Vds` into a confident "every device is in the linear
   region". A DC failure wearing the costume of a saturation result,
   exactly the §2 / §5 pattern again.
2. **The evidence was unrecoverable.** The `.log` for that corner had
   already been overwritten by the next one, so the failure could not be
   debugged from the artifacts.

Fixes:
- `bench_op` and `bench_psrr` now take `tag_extra`; `corners.py` passes
  the corner tag, so every run has its own recoverable `.sp`/`.log`.
- `bench_op` returns a `converged` flag (true iff `v(vout)` parsed), and
  `corners.py` reports a non-converged run as **"RUN FAILED — rerun this
  corner"**, never as a saturation verdict.

Re-run confirms it: **all 51 corners converge, 0 failures, ff/+85 °C is
a clean 0.9005 V / 80.9 µA identical across all three compensation
points** (Cc/Rz carry no DC current, so they *must* be identical — that
identity is now a checked invariant, not a hope). The transient parse
failure that produced the original bad row did not recur.

**Standing rule for this repo, from the reviewer:** every bench takes a
tag that includes every parameter that can change its result, and every
asymmetric circuit is measured in both directions.

## 10. Bench construction choices worth not re-deriving

- **Open-loop AC with the DC loop closed.** The feedback path is a 1 GH
  inductor (short at DC, open at AC) and the stimulus arrives through a
  1 GF capacitor. Breaking the loop with a voltage source instead would
  bias the amplifier at an operating point it never sees in use.
- **Phase margin is computed in Python from `wrdata` output**, not by
  `meas ac`. The measured response is inverting, so its low-frequency
  phase is 180°; the phase is unwrapped and referenced there, and PM is
  simply the phase remaining at the 0 dB crossing.
- **The UGF is the LAST 0 dB crossing, not the first.** On the
  AC-coupled corners the 47 µF cap high-passes the response, so gain
  *rises* out of the low-frequency end and crosses 0 dB on the way up.
  Taking the first crossing reported the 32 Ω headphone corner with a
  "unity-gain frequency" of 2.85 Hz — the coupling pole, mislabelled.
  The gain-margin phase search starts at the UGF index for the same
  reason.
- **`print @m.xdut.xNAME.mMODEL[param]`** reaches operating-point
  parameters through the sky130 model subckts (`gm`, `gds`, `vth`,
  `vdsat`, `vgs`, `vds`, `id`). Verified before it was relied on. This
  is how every device in `docs/results.md` gets a saturation margin
  instead of an assumption.
- **The ngspice + PDK setup is cribbed verbatim from
  `stdcells/flow/common.py`**, including the Windows 8.3 short-path
  conversion — this machine's home directory has a space in it and
  ngspice's `.lib` parser splits on spaces.

## 11. THD — the output stage is sink-limited at the spec swing, and the fix is not a single knob

The topology review's Call 2 said the ≥ 60 dB gain row was guarding the
wrong thing for an AC-coupled line output and should be a THD target, with
THD actually measured. `tb/thd.py` ([`thd.md`](thd.md)) measures it, and it
is the first bench to **fail** the spec.

**At the 1 V pp spec swing (row 3 minimum), THD is 1.44 % at 1 kHz** — over
both spec row 12 (< 1 %) and the review's proposed 0.1 %. The buffer is a
clean line source only up to ~0.75 V pp; above that it knees hard:

| swing | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1.0 |
|---|---|---|---|---|---|---|
| THD | 0.013 % | 0.031 % | 0.059 % | 0.110 % | 0.376 % | **1.44 %** |

**Mechanism — the class-A output sink, the same device as §5.** `xm5` (PMOS
common-source) sources hard; `xm6` is a current sink pinned at 61.5 µA. At
1 V pp / 1 kHz the peak sink demand into the 10 kΩ AC load is
0.5 V / 10 kΩ = 50 µA against that 61.5 µA — 1.23× of margin — so the
pull-down half of the swing runs into the sink's gm nonlinearity. The
harmonic split names it: h2 (even, up/down asymmetry) dominates, exactly
the asymmetry that made the fall slew 2.6× worse than the rise (§5). By
1.5 V pp h3 (odd compression) takes over at 11.9 % as the devices leave
saturation near the rails. Distortion is worst at the top of the audio band
(1.70 % at 20 kHz) because the loop gain that suppresses it falls there
(56 → 53 dB). The single stage is far worse (5T OTA **18.0 %** at the same
point) — drive-limited into 10 kΩ, the reason the review chose the two-stage.

**The fix, and why it is not free.** `tb/thd.py drive` scales the output
stage (`pout`, a new `.subckt` param, default 1 = shipped) and reads THD,
phase margin, UGF and I_q at the *same* bias — because a lower-THD point
that has lost its phase margin is a different circuit, not a better one:

| scale | THD | PM | UGF | I_q | |
|---|---|---|---|---|---|
| ×1 shipped | 1.44 % | 68.3° | 9.6 MHz | 80 µA | fails THD |
| **×1.5** | **0.62 %** | **63.2°** | 13.4 MHz | **111 µA** | **meets row 12 + 60° PM, in budget** |
| ×2 | 0.22 % | 54.6° | 16.5 MHz | 142 µA | best THD, PM < 60° |
| ×3 | 0.30 % | 39.7° | 20.2 MHz | 203 µA | out on PM *and* I_q; THD regresses |

Two things the measurement caught that the textbook would not:

- **The naive prediction was wrong.** More output gm2 should push the output
  pole gm2/CL out and *improve* PM. It does the opposite — PM falls
  monotonically — because the UGF column shows the crossover *rising*
  (9.6 → 20.2 MHz), not sitting at gm1/Cc. That is the §7 finding biting
  back: Rz = 20 kΩ is a lead/feedforward network, not pole-splitting, so
  scaling gm2 pushes the feedforward crossover up and the higher UGF eats
  the phase margin. The property that made Rz = 20 kΩ so *corner-stable*
  (passive, gm2-independent) is the same one that couples it to this knob.
- **So the fix is a joint output-current + Cc/Rz retune, not a knob.** The
  minimal change meeting the *existing* spec (row 12, < 1 %) is **×1.5**:
  0.62 % THD, 63.2° PM, 111 µA — one parameter, nominally clearing both THD
  and phase margin inside the 200 µA budget (row 11). The review's tighter
  0.1 % needs ≈×2 for the THD (0.22 %), but ×2 drops PM to 54.6°, so it
  requires *re-compensating* at the higher gm2 to buy the margin back. ×3 is
  out of bounds twice over (39.7° PM, 203 µA > budget) and its THD even
  regresses — consistent with the loop peaking as the margin collapses.

**Caveats.** All nominal (tt / 25 °C / 1.8 V). A chosen `pout` is a sizing
signal, not a signoff number, until `tb/corners.py` runs on it the way it
did for the compensation point (§7) — ×1.5's 3° of margin over 60° is thin.
And THD is measured behind the `line` load's coupling cap; the series output
cap the review made mandatory (Call 4) is assumed present.

**A harness bug this sweep flushed out.** The first `drive` run reported I_q
flat at 80 µA for every `pout` while THD and PM both scaled — an
impossible-current tell. `bench_op` had gained a `params` argument but its
netlist still called `_preamble(topo, load)` without it, so the DC run
silently ignored `pout`. Same family as H1/§9: a bench returning a number
the run did not actually produce. Fixed; I_q now scales 80 → 203 µA.

**Bookkeeping.** Row 12 already tracks THD, so the review's "restate row 5
as a THD target" lands there (tightened to its 0.1 %), now measured. Row 5's
separate gain relaxation (accept 56.8 dB) is still only in the review, not
yet in `tb/run.py`'s asserted `a_lf_db ≥ 60` — a tracked follow-up, not part
of this bench.

## 12. The THD fix — co-designed and corner-verified

§11 sized the problem and said the fix had to be a joint output-current +
compensation retune. `tb/thd.py fix` runs that co-design search and
`tb/corners.py fix` verifies the winner over PVT. It works, and the two
levers separate cleanly:

- **Rz is the phase-margin lever, and it is free in THD.** Dropping
  Rz 20 kΩ → 10 kΩ at ×2 output lifts PM from 54.6° to 74.7° while THD holds
  at 0.22 %. The reason is §7: Rz sets the feedforward that was pushing the
  UGF up, so halving it pulls the crossover back down (16.5 → 9.6 MHz) and
  hands the margin back. The property that made Rz = 20 kΩ a *corner-stable*
  lead network is now a deliberate design knob.
- **pout is the THD lever, and compensation barely touches it.** 1 kHz THD
  is set by output-stage linearity; the loop gain at 1 kHz is ≈ the DC gain
  regardless of Cc, so recompensation moves THD by < 0.01 %. Only more output
  current cuts it: ×2 → 0.22 %, ×2.5 → 0.17 %, and it stops there (×3 is over
  the I_q budget and its collapsing PM re-raises THD, §11).

**The applied operating point: ×2.5 output, Cc 4 pF, Rz 10 kΩ.**

| metric | shipped (×1) | **fix (×2.5)** | spec |
|---|---|---|---|
| THD @ 1 kHz / 1 V pp | 1.44 % | **0.167 %** | (see below) |
| phase margin, worst corner | 67.4° | **75.6°** (ff/−40 °C) | ≥ 60° |
| UGF, worst corner | — | **8.73 MHz** | ≥ 2 MHz |
| I_q, worst corner | 80 µA | **174 µA** | ≤ 200 µA |
| loaded DC gain | 56.8 dB | **62.0–64.9 dB** | (row 5) |

So the shortfall is fixed: **8.6× better THD**, clearing the old < 1 % row by
6×, with *more* phase-margin headroom than the shipped design and a bonus
6–8 dB of loop gain — all inside the 200 µA budget. Full corner table in
[`corners.md`](corners.md); the two-panel figure is
[`img/thd.png`](img/thd.png).

**What it does not reach — and §13 corrects why.** The review's 0.1 % is out
of reach at the full 1 V pp swing, and the reason is **not** the output
stage. The CMRR/ICMR bench (§13) shows the residual 0.167 % is the INPUT pair
running out of common-mode range on the high half: xm2 triodes at 1.40 V —
exactly the swing peak — and THD at this same fix point collapses to
0.0045 % once the swing stays inside ICMR (0.4 V pp). More output current
cannot touch that floor, so the path to ≤ 0.1 % at 1 V pp is a wider-ICMR
*input* (rail-to-rail / complementary pair), or a smaller swing — **not** a
class-AB output. (An earlier version of this note guessed a class-AB output;
the ICMR measurement overturned it — the residual is input-side.) At 0.167 %
the buffer is already ~35 dB below the distortion 8-bit-era console source
material carries, so for this application the fix is comfortably sufficient.

## 13. Common-mode — CMRR is a first-stage property, and ICMR is what actually caps the swing

`tb/cmrr.py` measures the two common-mode characterisations, and both land
somewhere more interesting than a pass/fail — because in a unity-gain buffer
the input common mode **is** the signal (it swings with the output).

**CMRR = 68.7 dB, flat across the audio band, and identical at the shipped
and fix operating points.** That last part is the finding. CMRR = A_dm/A_cm,
and *both* ride the second stage, so scaling the output — which lifts A_dm
from 56.8 to 63.5 dB — lifts A_cm by exactly the same amount (−11.8 → −5.2 dB)
and the ratio does not move. CMRR is set by the **first** stage's rejection;
the output fix is invisible to it. 68.7 dB is comfortable for a line buffer.

**ICMR is asymmetric, and the asymmetry is the whole THD story.** Sweeping
the input common mode (= output, in unity gain) at the fix point: peak
open-loop gain 64.3 dB, and the gain holds within 3 dB over ~0.30–1.10 V. But
the two edges fail for different reasons:

- **low side:** the tail is already in triode below ~0.70 V, yet the gain
  holds down to ~0.30 V (the pair keeps working through a triode tail), so
  the 0.40 V output trough of a 1 V pp swing sits at PEAK gain;
- **high side:** the input pair itself (xm2) runs out of headroom as the tail
  node rises, and triodes at **1.40 V — exactly the peak of a 1 V pp swing.**

So the 0.40–1.40 V a 1 V pp output demands is covered on the low side and
hits the wall on the high side. That splits §11/§12's THD number into two
mechanisms on opposite half-cycles:

| | mechanism | device | fixed by |
|---|---|---|---|
| shipped 1.44 % | low-side output sink runs out of pull | xm6 (61.5 µA) | scaling the output stage (§12) |
| fix residual 0.167 % | high-side input pair leaves saturation | xm1/xm2 ICMR | **not** output current |

**Confirmed, not inferred.** THD at the fix point vs swing:

| swing | output range | THD |
|---|---|---|
| 0.4 V pp | 0.70–1.10 V (inside ICMR) | **0.0045 %** |
| 0.6 V pp | 0.60–1.20 V | 0.032 % |
| 0.8 V pp | 0.50–1.30 V | 0.082 % |
| 1.0 V pp | 0.40–**1.40 V** (peak at the triode) | 0.167 % |
| 1.2 V pp | 0.30–1.50 V (past ICMR) | 1.19 % |

At 0.4 V pp the buffer is **37× cleaner** than at 1 V pp. The residual floor
is a *swing* limit set by the input ICMR, not a current one — which is why
the drive sweep (§11) plateaued at ~0.17–0.22 % for pout ≥ 2 no matter how
much output current it was given. **The consequence for §12:** ≤ 0.1 % at the
full 1 V pp needs a wider-ICMR input (a rail-to-rail or complementary
NMOS+PMOS pair), or a spec that accepts a smaller swing — 0.8 V pp already
buys 0.082 %. It does *not* need, and would not get, a class-AB output.

The general lesson, again this repo's: a distortion number is a composite,
and it is worth splitting by *which device on which half-cycle* before
prescribing a fix. Here the two halves had different culprits, and the output
fix that cured one was blind to the other.

## 14. The bias generator — a constant-gm reference, and two ways its start-up can be wrong

Every number in §1–§13 assumed an ideal 20 µA source programming the tail.
`spice/biasgen.sp` is the beta-multiplier that replaces it, and
`docs/biasgen.md` verifies it (spec O2). Three results, and two bugs worth
keeping.

**Constant-gm works, cleanly.** Over the full PVT box the reference current
moves 15.8–22.8 µA (±18 %, temperature-driven) while **gm·R holds
0.913–0.927 — a 1.5 % spread.** That is the point of the topology: the loop
moves the current to hold the transconductance, so the OTA's gm (hence its
UGF and the compensation §12 tuned) rides on a resistor, not on the process.
It is supply-independent too — 1.62 V and 1.98 V give the same 19.3 µA.
**Caveat that is not a footnote:** R is ideal here, so this is the
*transistor-side* spread only. gm ≈ 1/R means R's own variation maps straight
onto gm; a real sky130 xhigh_po poly resistor (σ 2.5 % process + a tempco) is
the reference's true PVT floor, and swapping it in is the honest next step.

**It drives the real amplifier to the same point.** miller_ota at the fix
operating point, biased by the reference instead of the ideal source, lands
at V_out 0.9003 V either way (Δ 0.0 mV) — so every §1–§13 number survives the
replacement. The cost is the reference's own ~55 µA draw (173 → 226 µA
total), which busts the 200 µA per-buffer budget *if the reference is charged
to one buffer* — but it is a shared block (one reference biases the DAC
buffer, the comparator and the SAR), so the honest accounting is per-system,
and a lower-current core mirrored up to the output would trim it.

**Start-up is the reference's silent failure mode, and I hit both classic
ways of getting it wrong.** The beta-multiplier has a perfectly stable I = 0
state; a DC `.op` solver escapes it by gmin stepping and looks fine, but
silicon powering up has no gmin stepping. Ramping the supply from 0:

1. **First cut: the injector never engaged.** The start-up's weak pull-up
   PMOS had its gate tied to VDD — V_gs = 0, off — so the sense node never
   rose and the reference sat dead through the whole ramp. The `.op` point
   had hidden it entirely (gmin found the live state); only the *transient*
   caught it. Fix: gate to VSS (an always-on weak pull-up).
2. **Second cut: the injector never released.** With the pull-up fixed but
   too strong relative to the pull-down, the sense node stayed high after the
   reference woke, so the injector kept sourcing ~18 µA forever and inflated
   the reference to 49.8 µA. Fix: make the pull-up *very* weak (long L) and
   the pull-down strong, so it dominates the instant the core is alive.

With the ratio right the reference wakes to 19.4 µA in ~3.8 µs, and with the
injector disconnected (`rsu = 1e12`) it stays dead — that pair, run every
time, is the proof the start-up is load-bearing. **The lesson:** a bias
reference must be signed off in *transient from a cold supply*, never on the
DC operating point alone — the `.op` solver is precisely the tool that cannot
see a start-up failure.
