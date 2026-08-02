# Phase 4 — the 8-bit SAR ADC

The paddle's converter: `spice/cdac8.sp` (charge-redistribution array),
whichever comparator phase 3 chose (`docs/comparator.md`), and SAR sequencing
built from ngspice's XSPICE digital primitives so the *analog* result is not
rescued or spoiled by a logic implementation. Bench: `tb/sar.py`.

A whole conversion — sample, eight bit trials, code read-out — runs in **one
transient**. That is what makes a 256-point transfer curve and an FFT record
affordable at all, and it is only possible because this ngspice build carries
the XSPICE code models (`d_dff`, `d_and`, `d_or`, `adc_bridge`, `dac_bridge`).

## It converts

`python tb/sar.py conv 0.9 comparator` — mid-scale input, ideal code 128:

    Vin 0.9000 V -> code 128 (ideal 128, err 0 LSB)
      trial 0 (bit 7): top = +0.8997 V (   -0.31 mV from vcm)
      trial 1 (bit 6): top = +1.3201 V ( +420.05 mV from vcm)
      trial 2 (bit 5): top = +1.1088 V ( +208.77 mV from vcm)
      trial 3 (bit 4): top = +1.0028 V ( +102.80 mV from vcm)
      trial 4 (bit 3): top = +0.9507 V (  +50.69 mV from vcm)
      trial 5 (bit 2): top = +0.9250 V (  +25.04 mV from vcm)
      trial 6 (bit 1): top = +0.9123 V (  +12.34 mV from vcm)
      trial 7 (bit 0): top = +0.9060 V (   +6.01 mV from vcm)

The residue halves every trial and lands inside one LSB (7.03 mV) — a binary
search doing exactly what it should. The same run with the **bare latch**
returns code 139 and a residue stuck near +70 mV; that is phase 3's kickback
number (49.3 fC on 1.26 pF = 39 mV per trial) arriving from the other direction.

## Result: every code, exactly

256-point transfer curve, one input per code centre, comparator = the phase-3
winner, `tt`:

| | |
|---|---|
| codes measured | 256 |
| **codes returned exactly** | **256 / 256** |
| failed conversions | 0 |
| gain error | **0.00 %** |
| offset | −0.50 codes (half an LSB — the code-centre sampling, not the circuit) |
| INL over the sampled curve | **0.00 LSB** |
| **SNDR / ENOB** (64-point coherent sine) | **50.26 dB → 8.06 bits** |
| largest spur | −58.1 dBc |

**Read the ENOB as "no distortion measurable above quantization", not as 8.06
bits of precision.** A 64-point record is short: coherent sampling makes the
quantization error deterministic and concentrated rather than white, which is
why the figure lands slightly above the 49.9 dB ideal instead of slightly below
it (the test sine is 0.85 V amplitude, a little under full scale). The claim the
transfer curve supports without qualification is the stronger one anyway —
*every code is right*.

And this is the third measurement of the same thing, which is the point: the
static DAC sweep, the converter's transfer curve, and the FFT are not
interchangeable, and the first one is the one that looks worst.

## The array

256 unit cells of `sky130_fd_pr__cap_mim_m3_1`, drawn 1.42 µm square, weighted
128/64/32/16/8/4/2/1 plus a terminating unit so the total is exactly 256 units
and one LSB is V<sub>ref</sub>/256 rather than V<sub>ref</sub>/255.

- **Unit cap: 4.9298 fF** (measured, not computed from the drawn area — the
  model biases each edge by `sw_cap_mim_dw` = 0.15 µm, so 1.42 µm drawn is
  1.57 µm effective).
- **Array total: 1.262 pF.**

### Two PDK model sets disagree about matching by 6×

sky130 ships the MIM capacitor twice, and the two definitions do not agree:

| | `libs.tech/combined` (**loaded here**) | `libs.tech/ngspice` → `libs.ref` |
|---|---|---|
| multiplicity parameter | `mult` | `mf` |
| matching coefficient | `sw_mm_cmim` = 4.7e-3 → **0.47 %·µm** | `0.01*2.8` → **2.8 %·µm** |
| perimeter term | none | `cpmimc` |

The repo's harness loads `libs.tech/combined` (inherited from
`stdcells/flow/common.py`), so every number here is the combined model's — and
because a 6× disagreement about matching is not a rounding difference in a
converter, `tb/sar.py match` re-runs the linearity against the pessimistic
coefficient too.

Adding the `libs.ref` file "to be safe" is worse than useless: ngspice keeps the
**first** definition and prints only `redefinition ... ignored`, so the netlist
silently runs against whichever model the corner lib already supplied while the
netlist appears to say otherwise.

### Unit cells, not scaled capacitors — worth 9.5 % on the MSB

`m=` replicates the subckt (verified: `m=4` gives exactly the capacitance of
four explicit instances) and `mult=` tells the mismatch term how many unit cells
it is averaging over. Drawing the 128C capacitor as **one** capacitor of 128×
the area instead would be wrong by **9.5 %**, because the 0.15 µm edge bias does
not scale with the drawing:

    128 unit cells        128 x 4.9298 fF = 631.0 fF
    one 128x-long cap     1.57 x 181.91 um x 2 fF/um^2 = 571.2 fF

Nine percent on the MSB is roughly 24 LSB of DNL. This is the whole reason real
arrays are built from identical unit cells, and here it is a number rather than
a principle.

## Static linearity — and which measurement answers which question

Two different measurements get confused constantly, so both are here:

- **`dac`** walks the code with the input fixed. The top plate therefore visits
  the entire rail, and any voltage-dependent load on it shows up in full. This
  is the right measurement for a **stand-alone DAC**.
- **`xfer`** runs real conversions. A binary search drives the top plate *back
  to* V<sub>cm</sub> whatever the input was, so **every conversion ends at the
  same potential** and a nonlinear parasitic's charge at that potential is the
  same constant every time. A full-rail bow in the DAC sweep therefore does not
  have to appear as converter INL.

Capacitor **mismatch** is the opposite case: it corrupts the binary *weights*,
so it carries into the converter in full. That is why `match` measures mismatch
with a *linear* top-plate load — otherwise the one contribution that transfers
is buried under the one that does not.

### The comparator's input capacitance is a nonlinear load

Static DAC sweep, identical in every respect except what hangs on the top plate:

| top-plate load | attenuation | DNL | INL |
|---|---|---|---|
| `strongarm` input pair | 3.12 % | −0.008 … +0.009 LSB | **−0.446 … 0 LSB** |
| linear cap, same value (41 fF) | 3.34 % | −0.001 … +0.001 LSB | **0 … +0.011 LSB** |
| `comparator` (pre-amp) input pair | 10.16 % | −0.104 … +0.071 LSB | **0 … +4.447 LSB** |

Same attenuation, forty times the INL: the bow is **entirely** the input pair's
voltage-dependent gate and junction capacitance, and the linear control proves
it. The pre-amp is three times worse because its input devices are twice as wide
(W = 40 µm vs 20 µm) — *the same sizing that won phase 3 on kickback*.

**And none of it reaches the converter.** With that same pre-amp on the top
plate, the 256-point transfer curve is exact at every code. That is the
charge-conservation argument holding in practice: the search always ends with
the top plate at V<sub>cm</sub>, so the parasitic's charge at the end equals its
charge at sampling and drops out of the balance. **+4.45 LSB of DAC INL, 0.00
LSB of converter INL.** Anyone quoting the first number as the converter's would
be wrong by the whole result — which is exactly why both measurements are here
with their scopes written down.

## The bug worth the whole phase: a 200 ps race costing 21 LSB

The first 256-point transfer curve was **bit-exact for codes 0–220** and then
fell apart: a one-sided negative error appearing abruptly at code 221 and
growing to **−10 LSB** at full scale. Nothing static predicted it.

Finding it took four measurements, and the order matters because three of them
ruled things *out*:

1. **Where does it start?** The residue trace showed the search converging
   normally — final residue 0.25 LSB — while landing on a code 8 LSB wrong. A
   converged search on a wrong code means the *sampled charge* was wrong, not
   the decisions.
2. **Is it leakage?** Conversion period 50 → 400 ns, an 8× change: the error
   moved from +122.4 mV to +123.5 mV. Time-independent ⇒ **capacitive, not
   leakage.**
3. **Is it the comparator's input capacitance?** Replace the comparator with an
   ideal B-source sign test — no input capacitance, no kickback, no offset. The
   error got **worse** (−21 LSB). Not the comparator; in fact its capacitance
   was *diluting* the real culprit.
4. **Is it the sampling switch?** Shrinking it 3 µm → 0.5 µm reduced the error
   (−21 → −13 LSB) but did not remove it. A contributor, not the cause. (At
   0.15 µm the conversion fails outright — the switch can no longer acquire.)

The cause is a **race in the sequencing**, and it is 200 ps long. The pointer
flop's `clk_delay` (0.1 ns) plus the `dac_bridge` rise time (0.1 ns) put the MSB
control ~0.2 ns behind the clock edge. The bottom plates were released from
`vin` on that *same* edge — so for 200 ps the array sat at **code 0**, and at
code 0 the top plate sits at V<sub>cm</sub> − V<sub>in</sub>, which for any
input above mid-rail is **negative** (−0.84 V at full scale). That
forward-biases the sampling switch's junction to the substrate and dumps
sampled charge on the floor. It does not come back.

Everything the symptom did is explained by that: one-sided (only inputs above
mid-rail go negative), growing toward full scale (further negative, more
conduction), time-independent (a switching event, not a leak), and worse without
the comparator (less capacitance on the node, so the same charge moves it
further).

**The fix is to release the bottom plates *after* the code is established**, and
it is complete:

| bottoms released after the code by | 0 ns | 2 ns | 5 ns | 10 ns |
|---|---|---|---|---|
| code error at V<sub>in</sub> = 1.294 / 1.519 / 1.744 V | 0 / −5 / −21 | **0 / 0 / 0** | **0 / 0 / 0** | **0 / 0 / 0** |

`tb/sar.py` now releases them at 3.05 T. The general form of the lesson: in a
charge-redistribution converter the array must **never** be allowed to sit at a
code that drives the top plate outside the rails, not even for one gate delay,
because the node is floating and the rails are diodes.

## Capacitor matching — and the 6× model disagreement does not change the design

Measured with a *linear* top-plate load, six mismatch draws each:

| | worst \|DNL\| | worst \|INL\| |
|---|---|---|
| no mismatch (`tt`) — the systematic floor | 0.0025 LSB | 0.0127 LSB |
| **combined model, 0.47 %·µm** (what this repo loads) | **0.091 LSB** | **0.066 LSB** |
| ngspice/`libs.ref` model, 2.8 %·µm (pessimistic) | **0.546 LSB** | **0.356 LSB** |

The useful part is the last line. Even under the **6× pessimistic** model the
array stays inside ±1 LSB DNL, so it is monotonic with no missing codes, and the
model disagreement — alarming when it was found — **does not change any design
decision**. A 4.93 fF unit cell has enough area either way. Had it not, the
right response would have been to size the unit cap from the pessimistic model
rather than to pick the model that gave the nicer answer.

### A number that flips sign with a solver setting is not a measurement

The unloaded sweep first reported ±0.1195 LSB of DNL sitting exactly at the MSB
transition. Changing only the maximum timestep moved it to ∓0.0705 — **and
changed its sign**. ngspice's default maximum step is `tstop/50` (~100 ns here)
and `meas ... find` *interpolates* between solver points, so a short dwell had
the measurement reading the code transition rather than the settled level.

At the converged settings (100 ns dwell, 1 ns max step) the loaded INL is stable
to ~1 % across a 10× range of dwell — −0.4454 LSB at 100 ns, −0.4526 at 200 ns —
so that one is real. Both settings are now defaults in `tb/sar.py`, with the
convergence study recorded next to them.

## The SAR logic, in the user's own standard cells

The measurements above use ideal XSPICE digital for the sequencing, deliberately
— that is what makes INL, DNL and ENOB properties of the array and the
comparator rather than of a logic implementation. `spice/sar_logic.sp` closes
PLAN phase 4's last item by replacing it with the real library.

**89 cells, 682 transistors, no foundry cells anywhere in it:**

| | INV_X1 | NAND2_X1 | NOR2_X1 | DFF_X1 | total |
|---|---|---|---|---|---|
| instances | 27 | 8 | 35 | 19 | **89** |
| transistors | 54 | 32 | 140 | 456 | **682** |

`spice/own_cells.sp` is the library, vendored with commit provenance from
`stdcells` (regenerated from `flow/cells.py`, **not** copied from
`stdcells/out/own.spice` — that build artifact is stale there and carries only
8 of the 9 cells).

### Two library properties shaped the design, and neither is a modelling choice

- **DFF_X1 has no set and no reset.** It is the `dfxtp_1` topology, D/CLK → Q,
  nothing else. So every register is cleared *synchronously*, by forcing its D
  input low while `rst` is high and letting a clock edge land — which means
  **`rst` must still be high AT a clock edge.** A reset pulse that ends before
  the first edge clears nothing, and the converter starts from whatever the DC
  solution picked. That costs one clock period: the own-cell path samples a
  period later than the XSPICE path, which is why the schedule is derived from
  `samp0()` rather than hardcoded.
- **NAND3/NOR3 are not in the library** (dropped in v1 on measured PPA), so
  every function is composed from two-input gates. `q(next) = (q OR (s AND
  dec)) AND NOT rst` becomes NAND2 → INV → NOR2 → NOR2, and the bit's DAC
  control `s OR q` becomes NOR2 → INV.

One design decision came out of the timing rather than the gate list. The code
registers are clocked by the master clock, whose edge lands at the *end* of a
trial — by which time the comparator has been reset and **both** its outputs are
high again, so sampling it there would latch "keep" every time. A single shared
`dec` flop, clocked by the capture strobe while the decision is still valid,
fixes it for the whole converter: one extra DFF instead of a gated clock per bit.

### It converts, on the real cells

| Vin | ideal code | own-cell code | |
|---|---|---|---|
| 0.9000 V | 128 | **128** | mid-scale |
| 0.2250 / 0.6750 / 1.1250 / 1.5750 V | 32 / 96 / 160 / 224 | **32 / 96 / 160 / 224** | across the range |
| 0.0316 / 0.8965 / 1.7473 / 1.7895 V | 4 / 127 / 248 / 254 | **4 / 127 / 248 / 254** | the extremes |

Eight for eight. Codes 248 and 254 are worth pointing at: that is exactly the
band the 200 ps race used to corrupt by −7 and −10 LSB, so it is also a
regression test for the fix, run on different logic.

The residue trace is indistinguishable from the ideal-logic run (420.04 mV vs
420.05 mV at trial 1, 6.00 mV vs 6.01 mV at trial 7) — the sequencing is doing
the same thing, in silicon-able gates.

**Scope, stated plainly:** this is a spot check, not the 256-point curve. Each
copy costs 682 extra transistors, an 8-copy run needs ~10 GB and a 4-copy run
takes ten minutes, so a full own-cell sweep would run for hours. The 256-code
result above stands on the XSPICE-logic runs; what the own-cell runs establish
is that the real library reproduces them.

*(Bench note: ngspice stores every vector at every timepoint by default, which
is what asked for 10.7 GB. `save` fixes it — but only with **bare node names**;
`save v(node)` parsed without complaint and saved everything anyway.)*

## What is open

- **Offset spread, from phase 3.** σ = 6.86 mV against a 1 LSB (7.03 mV) budget
  is 2 % of margin. Widening the pre-amp's diode loads is the obvious lever, and
  it trades against the input capacitance this phase has to live with.
- **Kickback is over budget somewhere for both candidates** (`docs/comparator.md`)
  — the pre-amp reaches −8.48 fC at negative overdrive against a 3.5 fC budget.
  It does not cost a code today, because the converter has 1.26 pF of array to
  absorb it, but it is not the margin the single-point number suggested.
- **The SAR logic in `stdcells` cells**, per PLAN phase 4. Deliberately not done
  here — ideal digital is what makes these numbers properties of the array and
  the comparator. The timing it has to meet is in `sources()`, including the
  release ordering that the 200 ps race made non-negotiable.
- **The real 500 kHz decision rate.** Everything above runs at 10 MHz, 20×
  faster than spec row 5, which is a stress condition for settling and a
  *relief* for leakage. Leakage was shown not to matter across 50 → 400 ns
  (the error moved 1.1 mV over an 8× change), but a 2 µs trial is another 5×
  beyond that and has not been simulated.
- **Mismatch and PVT on the converter.** The transfer curve is `tt` nominal.
  The array's own matching was swept separately (worst |DNL| 0.091 LSB, and
  0.546 LSB under the 6×-pessimistic model), but a full conversion has not been
  run over corners or with the comparator's offset drawn from its distribution.
