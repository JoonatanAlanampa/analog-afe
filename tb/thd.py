"""Total harmonic distortion -- the quantity spec row 5 should have been.

The topology review's call 2 concluded the 60 dB gain row was guarding
the wrong thing for an AC-coupled line output, and that the row should be
restated as a THD target with THD actually measured. This is that
measurement.

Method: unity-gain buffer, a pure sine into the primary (`line`) load,
ngspice `fourier` on the output. `fourier` analyses the LAST period of
the transient, so the sim runs many periods to settle first; the DC
operating point is solved before t=0, so there is no coupling-cap
startup ramp to wait out (the sine starts at the mid-rail bias, and
sin(0)=0). THD was checked convergent to 1.439 % at 1 kHz / 1 Vpp across
timesteps 2 µs -> 0.1 µs, so the numbers below are circuit, not grid.

What it sweeps:
  * LEVEL at 1 kHz -- distortion rises with output swing, and the knee
    near the rails is where the class-A output stage runs out of pull.
  * FREQUENCY at 1 Vpp -- loop gain falls with frequency (56 dB at DC,
    53 dB at 20 kHz), and distortion is suppressed by loop gain, so the
    top of the audio band is the worst case.
  * TOPOLOGY at 1 kHz / 1 Vpp -- the decided two-stage Miller vs the 5T
    OTA, to confirm the review's call on distortion grounds too.

The harmonic split is reported because it names the mechanism: 2nd
harmonic (even) comes from up/down ASYMMETRY -- exactly the class-A
output stage whose 61.5 µA sink limits the pull-down (design-notes.md
§5). 3rd harmonic (odd) is symmetric compression near the rails.

A fourth sweep, `drive`, is the resolution rather than the measurement:
the as-shipped output stage is sink-limited at the 1 Vpp spec swing (its
61.5 µA class-A sink against a ~50 µA peak demand), so 1 kHz/1 Vpp THD is
1.44 % -- over both spec row 12 (< 1 %) and the topology review's proposed
0.1 % target. `drive` scales that stage (the `pout` param on miller_ota)
and reports THD, phase margin, UGF and quiescent current together. The
distortion win is real (0.22 % by pout=2) but so is its price: phase margin
falls under the 60 deg spec by pout=2, because Cc/Rz were tuned at pout=1.
So the fix is a joint output-current + compensation retune, not a knob --
which is exactly what measuring PM alongside THD is there to reveal.

    python tb/thd.py             # everything -> docs/thd.md
    python tb/thd.py level       # THD vs output swing (maps the knee)
    python tb/thd.py freq        # THD vs frequency at 1 Vpp
    python tb/thd.py topo        # two-stage Miller vs 5T OTA
    python tb/thd.py drive       # THD vs output-stage current (the fix)
"""
import re
import sys
from pathlib import Path

from common import (VDD, ENV, OUT, ROOT, header, ib_of, load_net,
                    run_ngspice, SPICE)
from benches import bench_ac, bench_op

# decided compensation (docs/topology-review.md call 3)
COMP = "pcc=2e-12 prz=20000"
FANAL = re.compile(r"THD:\s*([0-9.]+)\s*%")
HROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9.eE+-]+)\s+[0-9.eE+-]+\s+"
                  r"([0-9.eE+-]+)", re.M)


def run_thd(topo, freq, vpp, load="line", comp=COMP, pout=1):
    """One transient + Fourier. Returns THD % and normalised harmonics.

    pout scales the miller_ota output stage (spice/miller_ota.sp); it is
    ignored for ota_5t, which has no such param. The tag carries load, pout
    AND comp as well as topo/freq/vpp because every one of them changes the
    result -- the repo's standing rule after H1/H2 (topology-review.md). comp
    goes into the tag because the `fix` search sweeps it; without it every
    (Cc, Rz) point at one pout would overwrite the same file.
    """
    amp = vpp / 2.0
    nper = 20
    tstop = nper / freq
    tstep = 1.0 / (freq * 500)
    ctag = re.sub(r"\W+", "", comp) if topo == "miller_ota" else "na"
    tag = f"thd_{topo}_{int(freq)}_{int(vpp*1000)}_{load}_p{pout}_{ctag}"
    sub = (SPICE / f"{topo}.sp").read_text()
    params = f"{comp} pout={pout}" if topo == "miller_ota" else ""
    net = f"""* {topo} THD, {freq} Hz, {vpp} Vpp, load={load}, pout={pout}
{header()}
{sub}
vdd vdd 0 dc {VDD}
vss vss 0 0
ib 0 vb dc {ib_of_stem(topo)}
xdut vin vout vout vb vdd vss {topo} {params}
{load_net(load)}
vin vin 0 dc {VDD/2} sin({VDD/2} {amp} {freq})
.tran {tstep:.6g} {tstop:.6g}
.control
run
fourier {freq} v(vout)
.endc
.end
"""
    out = run_ngspice(net, tag)
    m = FANAL.search(out)
    thd = float(m.group(1)) if m else None
    harm = {}
    for row in HROW.finditer(out):
        n = int(row.group(1))
        harm[n] = float(row.group(4))       # normalised magnitude
    return dict(thd_pct=thd, h2=harm.get(2), h3=harm.get(3),
                h4=harm.get(4), h5=harm.get(5))


def run_drive(pout):
    """THD at the spec swing vs output-stage current, WITH the stability and
    quiescent-current cost measured at the SAME bias.

    A lower-THD point that has lost its phase margin, or blown the 200 uA
    budget, is a different circuit and not a better one -- so THD, PM, UGF
    and Iq are all read at each pout. And the measurement earns its keep:
    the naive expectation was that raising gm2 only pushes the output pole
    gm2/CL out (helping PM), but the compensation was tuned at pout=1 and
    does NOT hold -- PM falls from 68.3 deg to 54.6 deg by pout=2, under the
    60 deg spec. So output current is not a free knob: it must be co-designed
    with Cc/Rz, and this table is the reason to say so rather than ship the
    lowest-THD point and discover the ringing in silicon."""
    thd = run_thd("miller_ota", 1000, 1.0, pout=pout)
    ac = bench_ac("miller_ota", "line", params=f"{COMP} pout={pout}",
                  tag_extra=f"_drive_p{pout}")
    op = bench_op("miller_ota", "line", tag_extra=f"_drive_p{pout}",
                  params=f"pout={pout}")
    return dict(pout=pout, thd_pct=thd["thd_pct"], h2=thd["h2"], h3=thd["h3"],
                pm_deg=ac.get("pm_deg"), ugf_hz=ac.get("ugf_hz"),
                a_lf_db=ac.get("a_lf_db"), isupply=op.get("isupply"),
                converged=op.get("converged"))


def run_point(pout, cc, rz):
    """One retuned (pout, Cc, Rz) operating point: THD, PM, UGF and Iq at the
    same bias. The `fix` search uses this to CO-DESIGN output current and
    compensation, because §11 showed raising pout alone busts phase margin
    (the Rz = 20 kΩ lead network pushes the UGF up as gm2 rises)."""
    comp = f"pcc={cc:g} prz={rz:g}"
    tag = f"_fix_p{pout}_cc{cc:g}_rz{rz:g}"
    thd = run_thd("miller_ota", 1000, 1.0, comp=comp, pout=pout)
    ac = bench_ac("miller_ota", "line", params=f"{comp} pout={pout}",
                  tag_extra=tag)
    op = bench_op("miller_ota", "line", tag_extra=tag, params=f"pout={pout}")
    return dict(pout=pout, cc=cc, rz=rz, thd_pct=thd["thd_pct"],
                pm_deg=ac.get("pm_deg"), ugf_hz=ac.get("ugf_hz"),
                isupply=op.get("isupply"))


# The `fix` search grid. §11's `drive` sweep showed more output current cuts
# THD but the ×1 compensation (Cc 2p / Rz 20k) loses phase margin as the UGF
# rises. This co-designs the two: at each pout, more Cc and/or less Rz pulls
# the UGF back down to buy the margin back, without dropping the dominant pole
# into the audio band (which would starve the 1 kHz loop gain and re-raise
# THD). Goal: THD ≤ 0.1 %, PM ≥ 65° nominal (for corner margin), Iq ≤ 200 µA.
FIX_GRID = [
    (2.0, 2e-12, 20000),     # the drive ×2 point (0.22 %, 54.6°) — baseline
    (2.0, 3e-12, 20000),
    (2.0, 4e-12, 20000),
    (2.0, 3e-12, 10000),
    (2.0, 4e-12, 10000),
    (2.5, 3e-12, 20000),
    (2.5, 4e-12, 20000),
    (2.5, 6e-12, 20000),
    (2.5, 4e-12, 10000),
]


def ib_of_stem(stem):
    # ota_5t / ota_5t_x5 share a file but differ in bias; here THD is
    # quoted for the shipped variants, so map by name.
    return {"ota_5t": 20e-6, "miller_ota": 20e-6}.get(stem, 20e-6)


# 0.6-0.9 map the distortion KNEE: THD is 0.013 % at 0.5 Vpp and 1.44 % at
# 1.0 Vpp, and the interesting question -- where does the buffer stop being a
# clean line source? -- lives in that gap.
LEVELS = [0.1, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.5]   # Vpp; 1.0 = row-3 min
FREQS = [20, 100, 1000, 10000, 20000]
FREQ_LABEL = {20: "20 Hz", 100: "100 Hz", 1000: "1 kHz",
              10000: "10 kHz", 20000: "20 kHz"}
# output-stage scale for the `drive` sweep. 1 = the shipped 60 uA sink;
# the finding is that at 1 = shipped the stage is sink-limited at 1 Vpp, so
# this asks what more output current buys and what it costs in Iq / stability.
DRIVE = [1, 1.5, 2, 3]


def pct(x):
    return "--" if x is None else f"{x*100:.3f} %" if x < 0.01 else f"{x:.3f} %"


def hp(x):
    return "--" if x is None else f"{x*100:.3f} %"


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"

    if what == "fix":
        # The co-design search (§11 follow-up). Prints the grid; the winner
        # is chosen by hand and documented, not auto-selected.
        print("pout   Cc     Rz     THD       PM      UGF       Iq", flush=True)
        for (p, cc, rz) in FIX_GRID:
            r = run_point(p, cc, rz)
            ok = (r["pm_deg"] and r["pm_deg"] >= 65 and r["thd_pct"] and
                  r["thd_pct"] <= 0.1 and r["isupply"] and
                  r["isupply"] <= 200e-6)
            print(f"×{r['pout']:<4} {r['cc']*1e12:>4.1f}p {r['rz']/1e3:>4.0f}k "
                  f"{r['thd_pct']:>7.3f}%  {r['pm_deg'] or 0:>5.1f}°  "
                  f"{(r['ugf_hz'] or 0)/1e6:>5.1f}MHz  "
                  f"{(r['isupply'] or 0)*1e6:>4.0f}µA"
                  f"{'   <== meets all' if ok else ''}", flush=True)
        return

    res = {}

    if what in ("level", "all"):
        res["level"] = []
        for vpp in LEVELS:
            r = run_thd("miller_ota", 1000, vpp)
            res["level"].append(dict(vpp=vpp, **r))
            print(f"level {vpp:.1f} Vpp @1kHz -> THD {r['thd_pct']}%  "
                  f"(h2 {hp(r['h2'])}, h3 {hp(r['h3'])})", flush=True)

    if what in ("freq", "all"):
        res["freq"] = []
        for f in FREQS:
            r = run_thd("miller_ota", f, 1.0)
            res["freq"].append(dict(freq=f, **r))
            print(f"freq {FREQ_LABEL[f]:>6} @1Vpp -> THD {r['thd_pct']}%  "
                  f"(h2 {hp(r['h2'])}, h3 {hp(r['h3'])})", flush=True)

    if what in ("topo", "all"):
        res["topo"] = []
        for t in ("miller_ota", "ota_5t"):
            r = run_thd(t, 1000, 1.0)
            res["topo"].append(dict(topo=t, **r))
            print(f"topo {t:11} @1kHz/1Vpp -> THD {r['thd_pct']}%",
                  flush=True)

    if what in ("drive", "all"):
        res["drive"] = []
        for p in DRIVE:
            r = run_drive(p)
            res["drive"].append(r)
            iq = r["isupply"] * 1e6 if r["isupply"] else float("nan")
            pm = r["pm_deg"] if r["pm_deg"] is not None else float("nan")
            print(f"drive pout={p:<4} -> THD {r['thd_pct']:.3f}%  "
                  f"PM {pm:.1f}deg  Iq {iq:.0f}uA", flush=True)

    write(res)


def write(res):
    L = ["# Total harmonic distortion\n",
         "Generated by `python tb/thd.py`. sky130 `tt` models, "
         f"{VDD} V, 25 °C, two-stage Miller (Cc 2 pF / Rz 20 kΩ) unless "
         "noted, unity-gain buffer into the `line` load, ngspice "
         "`fourier` on the settled output. Convergent to 1.439 % at "
         "1 kHz / 1 Vpp across timesteps 2 µs → 0.1 µs.\n",
         "The **2nd harmonic** (even) is the up/down asymmetry of the "
         "class-A output stage — its 61.5 µA sink limits the pull-down "
         "(`design-notes.md` §5); the **3rd** (odd) is symmetric "
         "compression near the rails.\n"]

    lv = res.get("level")
    if lv:
        L.append("## vs output level, 1 kHz\n")
        L.append("1 Vpp is the spec-row-3 minimum swing; the headline "
                 "number is quoted there. The buffer holds under the review's "
                 "0.1 % line-level target only up to ~0.75 Vpp (the 0.6–0.9 "
                 "rows map the knee), then rises steeply as the class-A output "
                 "sink runs out of pull.\n")
        L.append("| output | THD | 2nd | 3rd | 4th | 5th |")
        L.append("|---|---|---|---|---|---|")
        for r in lv:
            mark = " ⟵ spec swing" if abs(r["vpp"] - 1.0) < 1e-9 else ""
            L.append(f"| {r['vpp']:.1f} Vpp{mark} "
                     f"| **{r['thd_pct']:.3f} %** | {hp(r['h2'])} "
                     f"| {hp(r['h3'])} | {hp(r['h4'])} | {hp(r['h5'])} |")
        L.append("")

    fr = res.get("freq")
    if fr:
        L.append("## vs frequency, 1 Vpp\n")
        L.append("Loop gain falls with frequency (56 dB DC → 53 dB at "
                 "20 kHz) and distortion is suppressed by loop gain, so "
                 "the band top is the worst case.\n")
        L.append("| frequency | THD | 2nd | 3rd |")
        L.append("|---|---|---|---|")
        for r in fr:
            L.append(f"| {FREQ_LABEL[r['freq']]} "
                     f"| **{r['thd_pct']:.3f} %** | {hp(r['h2'])} "
                     f"| {hp(r['h3'])} |")
        L.append("")

    tp = res.get("topo")
    if tp:
        L.append("## by topology, 1 kHz / 1 Vpp\n")
        L.append("The 5T OTA is single-stage and drive-limited into 10 kΩ, so "
                 "it distorts an order of magnitude harder — the same reason "
                 "the topology review chose the two-stage Miller.\n")
        L.append("| topology | THD |")
        L.append("|---|---|")
        for r in tp:
            L.append(f"| {r['topo']} | **{r['thd_pct']:.3f} %** |")
        L.append("")

    dr = res.get("drive")
    if dr:
        L.append("## output-stage drive vs distortion, 1 kHz / 1 Vpp\n")
        L.append("The 1.44 % above is a design shortfall, not just a number, "
                 "so this sweep is the resolution. `pout` scales the output "
                 "stage (xm5/xm6) and the distortion falls hard with it — "
                 "0.22 % by ×2. But the compensation was tuned at ×1, and it "
                 "does **not** come along for free: **phase margin falls "
                 "below the 60° spec (row 8) by ×2**, so the lowest-THD point "
                 "is not shippable as-is. The fix is therefore a joint "
                 "output-current **and** Cc/Rz retune, not a single knob — and "
                 "reading PM/UGF beside THD at the same bias is what makes "
                 "that visible instead of a silicon surprise. I_q is the other "
                 "cost, against the 200 µA budget (spec row 11). The **×1.5** "
                 "row is the minimal change that meets the *existing* spec "
                 "(< 1 % + 60° PM, in budget) with no recompensation; the "
                 "0.1 % target needs ≈×2 plus the retune.\n")
        L.append("| output scale | ≈ sink | THD | 2nd | 3rd | PM | UGF | I_q |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in dr:
            iq = f"{r['isupply'] * 1e6:.0f} µA" if r.get("isupply") else "--"
            pm = f"{r['pm_deg']:.1f}°" if r.get("pm_deg") is not None else "--"
            ugf = f"{r['ugf_hz'] / 1e6:.1f} MHz" if r.get("ugf_hz") else "--"
            sink = f"≈{61.5 * r['pout']:.0f} µA"
            mark = " ⟵ shipped" if abs(r["pout"] - 1) < 1e-9 else ""
            L.append(f"| ×{r['pout']}{mark} | {sink} "
                     f"| **{r['thd_pct']:.3f} %** | {hp(r['h2'])} "
                     f"| {hp(r['h3'])} | {pm} | {ugf} | {iq} |")
        L.append("")
        L.append("**Applied** (`tb/thd.py fix`, then `tb/corners.py fix`): the "
                 "co-design lands on **×2.5 output, Cc 4 pF / Rz 10 kΩ → "
                 "0.167 % THD, 81° PM, 173 µA** — 8.6× better than shipped, "
                 "clearing the old < 1 % row by 6× and corner-verified to "
                 "PM ≥ 75.6° across the §7 box (`corners.md`). The two levers "
                 "separate cleanly: **Rz 20k→10k is the phase-margin lever** "
                 "(it cuts the feedforward that pushes the UGF up — §7 — and "
                 "costs nothing in THD), **pout is the THD lever**. The "
                 "review's 0.1 % is *not* reachable by more output current at "
                 "all: the ICMR bench (`design-notes.md` §13) shows the "
                 "0.167 % residual is the input pair leaving its common-mode "
                 "range on the high swing (it triodes at the 1.40 V peak), so "
                 "≤ 0.1 % needs a wider-ICMR input or a smaller swing.\n")

    p = Path(ROOT / "docs" / "thd.md")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
