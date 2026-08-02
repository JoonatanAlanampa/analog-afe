# Phase 3 — the paddle SAR's comparator

Two candidates, one question: **does the pre-amp earn its current?**
`spice/strongarm.sp` is a bare StrongARM latch used as a complete comparator;
`spice/comparator.sp` puts a pre-amp in front of *that same latch file*, so the
comparison is genuinely about the pre-amp and not about two differently-tuned
latches. Bench: `tb/comparator.py`. Spec: `docs/spec-comparator.md`.

The answer is **yes, and not for the reason the netlist header expected**. The
pre-amp was justified there on two grounds — dividing the latch's offset, and
isolating kickback. Measured, the offset argument barely holds and the kickback
argument is decisive by a factor of forty-seven.

## Results

All at `tt`, 25 °C, 1.8 V, into a 10 fF logic load per output, unless stated.

| | `strongarm` | `comparator` | spec | |
|---|---|---|---|---|
| static current | **0.300 µA** | **19.04 µA** | — | |
| charge per decision (reset included) | **307 fC** | **1011 fC** | — | |
| average current at the 500 kHz decision rate | **0.45 µA** | **19.5 µA** | ≤ 50 µA | both PASS |
| delay, +100 mV overdrive (V<sub>cm</sub> 0.95 V) | 0.185 ns | 0.978 ns | ≪ 2 µs | PASS |
| delay, −100 mV overdrive (V<sub>cm</sub> 0.85 V) | 0.270 ns | 0.963 ns | ≪ 2 µs | PASS |
| direction asymmetry | **1.46×** | **1.02×** | — | |
| delay at 1 mV | 0.325 ns | 2.039 ns | | |
| slowest decision measured (1 µV overdrive) | 0.361 ns | 2.629 ns | 2 µs trial | ~10<sup>3</sup>× margin |
| kickback into a 1 pF top plate, peak — **at balance** | **49.34 fC** | **1.04 fC** | < 3.5 fC | FAIL / pass |
| kickback residual — **at balance** | **−49.34 fC** | **−0.005 fC** | < 3.5 fC | FAIL / pass |
| **kickback residual — worst over the input range** | — | **−8.48 fC** | < 3.5 fC | **FAIL** (see below) |
| decisions correct, top plate 0.05 → 1.70 V | 34/34 | 34/34 | row 11 | PASS |
| hysteresis at `tt` | < 0.5 µV (floor) | < 0.5 µV (floor) | < 3520 µV | PASS |

## The finding: kickback, not offset, decides it

The bare latch pushes **49.3 fC** back into the node it is measuring, and
**keeps it** — the peak and the residual are the same number, because a
charge-holding node has nowhere to put it. The budget is 3.5 fC (half an LSB on
1 pF). It is over by **14×**.

The mechanism is not incidental, and it is the same sizing decision twice:

> The input pair is deliberately **long and wide** (W = 20 µm, L = 1 µm) because
> a comparator's offset is mismatch, mismatch scales as 1/√(WL), and this job
> has nanoseconds of work to do in a 2 µs trial — so the entire speed surplus
> was spent on matching. That same large gate is what couples the evaluation
> transient into the input. **The sizing that buys matching buys kickback.**

The pre-amp breaks the link because it is *continuously biased*: its tail never
switches, so its input sees no evaluation transient at all, and the latch's kick
lands on the pre-amp's output instead of on the DAC. Measured, that is a **47×**
reduction in peak and essentially total in residual (−0.005 fC, i.e. below what
this bench can resolve).

### The single-point number was measured where kickback is smallest

Kickback is conventionally quoted at threshold, which is what `run_kick` did.
Phase 4 sent the measurement back, because a SAR spends most of its trials far
from balance by construction. Swept across the input range (`kicksweep`), the
residual charge per decision is:

| overdrive | −800 mV | −400 mV | −5 mV | +5 mV | +400 mV | +800 mV |
|---|---|---|---|---|---|---|
| `strongarm` | −3.1 fC | −13.0 fC | −48.5 fC | −49.3 fC | −91.4 fC | **−136.7 fC** |
| `comparator` | −8.4 fC | −8.4 fC | −0.006 fC | −0.005 fC | +0.000 fC | −0.020 fC |

Two things change:

1. **Neither candidate actually holds the 3.5 fC budget everywhere.** The bare
   latch is worse than its threshold figure — monotonically, up to **−136.7 fC**
   at +800 mV, 39× over. The pre-amp is **1413× worse than its own threshold
   figure** at negative overdrive (−8.48 fC, 2.4× over budget), while staying at
   essentially zero for positive overdrive.
2. **The verdict does not change, but the margin claim does.** The pre-amp is
   still 16× better at each candidate's worst point, and its error is one-sided
   and bounded rather than growing with signal. But "1.04 fC, comfortably inside
   a 3.5 fC budget" was an artefact of measuring at the one operating point
   where a comparator is quietest.

The general lesson is the one this repo keeps re-learning in different clothes:
**a single-point measurement of a nonlinear quantity is a measurement of the
point, not the quantity** — the same shape as the one-directional step in
`design-notes.md` §5 and the missing coupling capacitor in §2.

**Phase 4 reproduced this independently, without being asked to.** The first
end-to-end SAR conversion (`tb/sar.py conv 0.9`, same array, same sequencing,
comparator = `strongarm`) returned code **139** for a mid-scale input whose
ideal code is 128, and the residue plot showed it never converging — it settled
around +70 mV instead of within an LSB. 49.3 fC on the array's 1.26 pF is 39 mV
per trial, which is what that is. Swapping in the pre-amp candidate and changing
nothing else gave **code 128, error 0**, with the residue halving cleanly every
trial (420 → 209 → 103 → 51 → 25 → 12.3 → 6.0 mV).

## What the pre-amp does *not* buy — and offset is worse than "not"

`spice/comparator.sp`'s header gives two reasons for the pre-amp, and lists the
offset one **first**: "it divides the LATCH's offset by its gain, referred to
the input". Measured, that reason is not merely weak — it is **backwards**.

| | `strongarm` | `comparator` | spec row 8 |
|---|---|---|---|
| offset µ | −0.44 mV | −0.73 mV | — |
| **offset σ** | **3.07 mV** | **6.86 mV** | ≤ 7.03 mV (1 LSB) |
| 3σ | ±9.22 mV | ±20.6 mV | |
| device samples | 504 (7 usable points) | 504 (12 usable points) | |

Both pass, but the pre-amp **more than doubles** the spread and leaves only 2 %
of margin against the 1 LSB budget. It does divide the latch's offset by its
gain — the latch's own 3.07 mV arrives divided by a gain of only
g<sub>m,n</sub>/g<sub>m,p</sub>, a few — but it then adds its own input pair
*and its diode loads*, and the loads are small devices (W = 10 µm, L = 0.5 µm)
whose mismatch is referred to the input with gain. The sum is worse than what it
replaced.

σ = 6.86 mV against a 7.03 mV budget is not a margin anyone should ship. It is
the clearest **open item** this phase leaves: widening the pre-amp's diode loads
is the obvious lever, and it trades directly against the input capacitance that
phase 4 has to live with.

This is worth keeping because it is the argument everyone reaches for first, and
because it does not change the verdict: kickback decides, and offset spread is
the price.

- **Speed.** It is **5.6× slower** (2.04 ns vs 0.33 ns at 1 mV). Against a 2 µs
  trial this is free, which is exactly why the sizing argument in
  `spice/strongarm.sp` holds: there is nothing to buy with speed here, so speed
  is the right currency to spend.
- **Speed.** It is **5.6× slower** (2.04 ns vs 0.33 ns at 1 mV). Against a 2 µs
  trial this is free, which is exactly why the sizing argument in
  `spice/strongarm.sp` holds: there is nothing to buy with speed here, so speed
  is the right currency to spend.
- **Current.** 43× more, and that is real — but it is 39 % of the 50 µA budget
  (spec row 13), so the budget absorbs it.

**The verdict in one line:** the pre-amp costs 43× the current and 2× the offset
spread, and buys the 47× kickback reduction that is the difference between a
converter that works and one that does not.

## Metastability is a non-issue, by three orders of magnitude

Delay grows logarithmically with falling overdrive, as it must:

| overdrive | 100 mV | 10 mV | 1 mV | 0.1 mV | 1 µV |
|---|---|---|---|---|---|
| `strongarm` | 0.185 ns | 0.279 ns | 0.325 ns | 0.352 ns | 0.361 ns |
| `comparator` | 0.978 ns | 1.820 ns | 2.039 ns | 2.244 ns | 2.629 ns |

Even at **1 µV** of overdrive — a seventh of a millionth of full scale — the
slowest decision measured is 2.6 ns against a 2 µs trial:

| | regeneration τ | slowest decision | margin on a 2 µs trial |
|---|---|---|---|
| `strongarm` | 23.0 ps | 0.361 ns | **5540×** |
| `comparator` | 155.3 ps | 2.629 ns | **761×** |

Spec row 12 is met by roughly three orders of magnitude, and it is met because
the block is slow by design, not because the latch is fast.

**τ is fitted over the clean decades only (100 → 0.1 mV, 7 points).** Below
~0.1 mV the measured delay stops following the logarithm and flattens; at a
microvolt of differential on a 1.8 V circuit it is the solver's tolerance, not
the latch, that decides when the tie breaks. Fitting all eleven points anyway
gives 13.6 ps and 115.9 ps — roughly *half* — i.e. it would quote a latch
significantly faster than it is, and blame the circuit for the solver.

## The direction asymmetry is the SAR's fault, not the latch's

`strongarm` decides 1.46× faster for positive overdrive than negative. The
netlist is symmetric, so that looks wrong until you notice what the bench does —
and what it does is what the *converter* does: **only one input moves.** `vin`
is the fixed mid-rail reference and `vip` is the DAC top plate, so +100 mV and
−100 mV are also two different common modes (0.95 V and 0.85 V), and the tail
delivers more current at the higher one.

So the asymmetry is real and the converter will see it, but its cause is the
single-ended drive. This is the same class of mistake as `design-notes.md` §5,
where a one-directional step measured the easy edge — except here the fix is not
to symmetrise the bench, because the asymmetric case *is* the application.

## Common-mode range: row 11 passes over the whole rail

A charge-redistribution SAR's top plate does not sit at mid-rail. With the
classic scheme, the first trial puts it at V<sub>cm</sub> − V<sub>in</sub> +
V<sub>ref</sub>/2, which for inputs spanning the rail means the top plate spans
the rail too. Sweeping the top plate 0.05 → 1.70 V against the fixed 0.9 V
reference, **both candidates decided correctly at all 34 points.**

There is a useful accident in the geometry, and it is worth stating because it
is what makes the classic scheme viable at all on 1.8 V: **the extreme common
modes coincide with the largest differentials.** A top plate at 0.1 V is 0.8 V
away from the reference — so the trial that asks for the most common-mode range
asks for the least resolution. The comparator only needs to be *right*, not
sensitive, where it is most uncomfortable.

## What this bench got wrong first

Three measurement bugs, each of which produced a plausible number:

1. **Every current read `nan`.** `common.parse_meas` anchors on end-of-line,
   which is correct for `print` output but silently drops every `meas` result,
   because ngspice appends the measurement window (`istat = -7.7e-07 from=
   4.5e-08 to= 5.0e-08`). A parser that matches nothing looks exactly like a
   circuit that measured nothing.
2. **The delay bench measured the reset.** A StrongARM precharges *both* outputs
   to VDD, so evaluation does not raise the winner — it pulls the **loser down**.
   Triggering on "when does `outp` rise" therefore found the reset edge, returned
   −39 ns (a negative delay is the giveaway), and at large overdrive returned
   nothing at all. The four points that *did* produce a number were the small-
   overdrive cases where both outputs droop and one climbs back — the recovery,
   not the decision — and the τ fitted from them was meaningless.
3. **Kickback into an ideal source is always zero.** Driving the input from a
   voltage source would have reported 0 fC for both candidates and hidden the
   entire result. The input is modelled as a 1 pF capacitor behind a 1 GΩ path,
   so the DC operating point still solves while the node is effectively floating
   over a decision. Same class as the coupling-capacitor error in
   `design-notes.md` §2: a testbench missing part of the real circuit measures a
   different circuit, not a worse one.

## Method note — why the bench runs K comparators at once

A threshold measured by bisection needs ~20 *sequential* ngspice runs, and a run
here is dominated by loading the sky130 library rather than by solving the
circuit: the search was ~95 % startup, at 15 s a run. Since decisions at
different overdrives are independent, K copies of the DUT go into one netlist
instead, and three K-way scans replace twenty runs — 1 m 37 s against 10 m 15 s,
**validated against the bisection answer before being adopted** (both 0 µV at
`tt`).

Each copy carries its **own** bias source. Sharing one 20 µA reference across N
copies would have divided it, and the whole scan would have quietly measured a
starved comparator.
