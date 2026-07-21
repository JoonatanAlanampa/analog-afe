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

## 4. Bench construction choices worth not re-deriving

- **Open-loop AC with the DC loop closed.** The feedback path is a 1 GH
  inductor (short at DC, open at AC) and the stimulus arrives through a
  1 GF capacitor. Breaking the loop with a voltage source instead would
  bias the amplifier at an operating point it never sees in use.
- **Phase margin is computed in Python from `wrdata` output**, not by
  `meas ac`. The measured response is inverting, so its low-frequency
  phase is 180°; the phase is unwrapped and referenced there, and PM is
  simply the phase remaining at the 0 dB crossing.
- **`print @m.xdut.xNAME.mMODEL[param]`** reaches operating-point
  parameters through the sky130 model subckts (`gm`, `gds`, `vth`,
  `vdsat`, `vgs`, `vds`, `id`). Verified before it was relied on. This
  is how every device in `docs/results.md` gets a saturation margin
  instead of an assumption.
- **The ngspice + PDK setup is cribbed verbatim from
  `stdcells/flow/common.py`**, including the Windows 8.3 short-path
  conversion — this machine's home directory has a space in it and
  ngspice's `.lib` parser splits on spaces.
