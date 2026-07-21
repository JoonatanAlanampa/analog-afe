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

## 7. Bench construction choices worth not re-deriving

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
