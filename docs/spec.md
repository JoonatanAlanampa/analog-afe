# Spec — console audio output buffer

This block is not "an op-amp". It is the console's audio output buffer,
and every number below is traceable to that job. Where a number is a
guess rather than a derivation, it says so.

## Where it sits

Today the console makes sound the digital way: a sigma-delta bitstream on
`uio[7]` → the cartridge Pmod's 74LVCE1G126 buffer → a two-stage RC low
pass → volume trim → 47 µF → 3.5 mm jack. (See `pmod-cartridge/README.md`,
section "Audio chain".)

The mixed-signal console replaces the *bitstream and the external analog*
with silicon we designed:

    chiptune voices --> our DAC --> THIS BUFFER --> coupling cap --> jack

so the buffer's load is whatever the board presents past the coupling
cap, and its input is a DAC output — a high-impedance node it must not
disturb.

## Electrical targets

| # | Parameter | Target | Where it comes from |
|---|---|---|---|
| 1 | Supply | 1.8 V, sky130 core devices | the process; see open question O1 |
| 2 | Signal band | 20 Hz – 20 kHz | audio |
| 3 | Output swing | ≥ 1 V pp, centred mid-rail | line level is ~0.3–1 V rms; 1 V pp = 0.35 V rms |
| 4 | Closed-loop gain | 1 (unity buffer) | the DAC sets level; the buffer only drives |
| 5 | Open-loop gain A_DC | ≥ 60 dB | ≥ 0.1 % gain error unity-gain, and headroom for #6 |
| 6 | Loop gain at 20 kHz | ≥ 40 dB | distortion is suppressed by loop gain; sets #7 |
| 7 | UGF | ≥ 2 MHz | 40 dB of loop gain left at 20 kHz on a −20 dB/dec roll-off |
| 8 | Phase margin | ≥ 60° | no peaking into a capacitive cable load |
| 9 | Slew rate | ≥ 0.1 V/µs | 1 V pp at 20 kHz needs 2π·20k·0.5 = 0.063 V/µs; ~60 % margin |
| 10 | PSRR at 1 kHz | ≥ 40 dB | it shares a die with a CPU, a QSPI controller and video timing |
| 11 | Quiescent current | ≤ 200 µA | budget, not a derivation — revisit when the DAC's is known |
| 12 | THD | **≤ 0.2 %** at 1 V pp, 1 kHz (line-level; 0.1 % aspiration needs class-AB) | **0.167 % — MEETS** at the co-designed fix (×2.5 output, Cc 4p / Rz 10k), corner-verified PM ≥ 75.6°, I_q ≤ 174 µA; shipped ×1 was 1.44 % (`docs/thd.md`, `corners.md`, design-notes §12) |
| 13 | Input-referred noise | < 100 µV rms, 20 Hz–20 kHz | measured **24.3 µV — PASS** (~4× margin, ~83 dB SNR; `docs/noise.md`) |

Targets 1–11 are checked by `tb/run.py`; 5, 7, 8, 10 and 9 are asserted
in `SPEC` in `tb/run.py` and print PASS/FAIL in `docs/results.md`. Rows 12
(THD, `tb/thd.py`) and 13 (noise, `tb/noise.py`) have their own benches.

**Row 12 — found failing, now fixed.** The topology review's Call 2 asked to
stop using open-loop gain (row 5) as a distortion proxy and measure THD
directly. Measured, the as-built buffer was 1.44 % at the required 1 V pp
swing — the class-A output sink (61.5 µA) running out of pull, a clean line
source only to ~0.75 V pp. The fix (`docs/thd.md`, design-notes §12)
co-designs output current and compensation — **×2.5 output, Cc 4 pF /
Rz 10 kΩ → 0.167 % THD**, corner-verified to PM ≥ 75.6° and I_q ≤ 174 µA — an
8.6× improvement that clears the target with margin. The review's 0.1 %
aspiration is a class-A *budget* limit (0.1 % needs I_q > 200 µA) and would
take a class-AB output stage. Call 2's separate row-5 gain relaxation (accept
56.8 dB, still asserted ≥ 60 in `tb/run.py`) is a tracked follow-up — eased
anyway, since the fix's loaded gain is 62–65 dB.

## Load corners

Defined in `tb/common.py`, all three simulated:

- **line** (primary) — 10 kΩ ‖ 50 pF behind the board's 47 µF coupling
  cap. This is a line input, or the cartridge Pmod's own high-impedance
  buffer input.
- **pmodrc** — the cartridge Pmod's RC network exactly as the board is
  built, DC-coupled: 120 Ω + 33 Ω series, 147 nF / 100 nF shunts, 200 Ω
  volume trim to ground. An op-amp dropped into the digital buffer's
  position sees ~353 Ω to ground at DC. Expected to fail; the point is
  to quantify by how much.
- **phone** — 32 Ω headphone behind the 47 µF cap. Stretch corner. If
  both candidates fail it, that is the evidence for adding a class-AB
  output stage (or for declaring the output line-level only and leaving
  power to the Pmod's amplifier).

**Coupling is part of the load spec, not a detail.** The first version of
this bench modelled 10 kΩ DC-coupled and pulled the output down to
0.196 V — which is just 20 µA into 10 kΩ, a modelling error rather than
an amplifier result. Real audio outputs sit at mid-rail behind a series
capacitor; the resistance is an AC load only.

## Open questions (for the topology review)

- **O1 — supply and pads.** TinyTapeout analog slots bring pins straight
  out; the analog supply domain, the ESD structure in the path, and
  whether a 3.3 V rail is available have NOT been verified against the
  TT analog documentation. Everything here assumes a 1.8 V core supply.
  If 3.3 V is available the input-common-mode problem below largely
  disappears, which could change the topology choice.
- **O2 — where the buffer's bias comes from.** Simulated with an ideal
  external current source into `vb`. A constant-gm / beta-multiplier
  reference is its own design task and its own silent failure mode
  (start-up).
- **O3 — is a headphone drive in scope at all?** #3 assumes line level.
- **O4 — the DAC's output impedance and common mode** are unknown, so
  the input common mode is assumed to be mid-rail (which is what a
  unity-gain buffer forces anyway).

## The constraint that dominates everything

sky130's threshold voltages are ~0.63 V (NMOS) and ~0.9 V (PMOS) on a
1.8 V rail — a third to a half of the supply. This is measured, not
quoted: see `docs/design-notes.md`. It killed the PMOS input pair on the
first run and it is the reason the candidates below are not the textbook
shapes. Any topology decision that ignores V_th/V_dd here will be wrong.
