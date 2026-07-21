"""PVT corners and Monte Carlo offset -- the largest remaining unknown.

Everything else in this repo is one nominal `tt` 25 C 1.8 V run. Two
questions need more than that, and both are decision-grade:

1. **Does the compensation choice survive corners?** `compensation.md`
   found several (Cc, Rz) points that clear phase margin and UGF, but
   the highest-UGF one sits at Rz = 16x the measured 1/gm2 -- a lead
   compensator relying on a zero that TRACKS gm2. gm2 is exactly what
   moves over process and temperature, so the nominal ranking may not
   be the real one. This bench re-runs both candidate compensation
   points across PVT and reports the WORST corner, which is the only
   number a compensation choice can honestly be made on.

2. **How big is the input offset?** Mismatch is the thing a digital
   flow never makes you think about. In a unity-gain buffer the offset
   lands directly on the output as a DC shift into the coupling cap.
   sky130 ships `*_mm` corners (MC_MM_SWITCH=1) whose device parameters
   are drawn from gaussians at parse time, so Monte Carlo here is N runs
   with N different `.option seed` values -- not one run with a loop.

The benches themselves are NOT re-implemented: `common.ENV` is mutated
and `benches.bench_op` / `bench_ac` are called unchanged. A corner sweep
with its own private AC extraction would be comparing two benches
instead of two corners.

    python tb/corners.py pvt      # process x temperature x supply
    python tb/corners.py mc [N]   # Monte Carlo offset, default 30 draws
    python tb/corners.py          # both

Writes docs/corners.md.
"""
import json
import math
import statistics
import sys
from pathlib import Path

import common
from common import ENV, OUT, ROOT, VDD
from benches import bench_op, bench_ac

PROCESS = ["tt", "ss", "ff", "sf", "fs"]
TEMPS = [-40, 25, 85]
SUPPLIES = [1.62, 1.98]          # +/-10 %, swept at tt/25 C only
LOAD = "line"

# The two compensation points the review has to choose between
# (docs/compensation.md). Named, so the table says which is which.
#
# Rz = 1/gm2 measures 1248 ohm (xm5, docs/results.md), so these are
# roughly 16x, 1.6x and 4x that. The 8p/2k row is included even though
# it FAILS the phase-margin target nominally (51.7 deg): review-brief.md
# offered it as a "conservative alternative" on a misread of the sweep
# table -- 71.7 deg belongs to 8p/5k, not 8p/2k. Keeping it in the sweep
# is the correction, in data.
COMP = {
    "aggressive (Cc 2p, Rz 20k)": "pcc=2e-12 prz=20000",
    "conservative (Cc 8p, Rz 2k)": "pcc=8e-12 prz=2000",
    "moderate (Cc 8p, Rz 5k)": "pcc=8e-12 prz=5000",
}
PM_TARGET, UGF_TARGET = 60.0, 2e6
MC_DRAWS = 30


def at(corner, temp, vdd_v, seed=None):
    ENV.update(corner=corner, temp=temp, vdd=vdd_v, seed=seed)


def reset():
    at("tt", 25, VDD)


def pvt_points():
    pts = [(p, t, VDD) for p in PROCESS for t in TEMPS]
    pts += [("tt", 25, v) for v in SUPPLIES]
    return pts


def run_pvt():
    rows = []
    for name, params in COMP.items():
        for (p, t, v) in pvt_points():
            at(p, t, v)
            tag = f"_{p}_{t}_{v}".replace(".", "p")
            ac = bench_ac("miller_ota", LOAD, params=params, tag_extra=tag)
            op = bench_op("miller_ota", LOAD, tag_extra=tag)
            if not op.get("converged", True):
                bad = ["RUN FAILED (no op-point) — rerun this corner"]
            else:
                bad = [i for i, d in op["devices"].items()
                       if not (d["sat_margin"] > 0)]
            rows.append(dict(comp=name, process=p, temp=t, vdd=v,
                             a_lf_db=ac.get("a_lf_db"),
                             ugf_hz=ac.get("ugf_hz"),
                             pm_deg=ac.get("pm_deg"),
                             vout=op.get("vout"),
                             isupply=op.get("isupply"),
                             out_of_sat=bad))
            print(f"  {name[:12]:12s} {p:2s} {t:+4d}C {v:.2f}V  "
                  f"A={ac.get('a_lf_db') or float('nan'):5.1f}dB  "
                  f"UGF={(ac.get('ugf_hz') or 0)/1e6:6.2f}MHz  "
                  f"PM={ac.get('pm_deg') or float('nan'):6.1f}deg  "
                  f"Vout={op.get('vout') or float('nan'):.3f}  "
                  f"{'SAT-FAIL:' + ','.join(bad) if bad else ''}",
                  flush=True)
    reset()
    return rows


def run_mc(n=MC_DRAWS):
    """Input offset from mismatch, unity-gain buffer, tt_mm.

    Offset is read as vout - vcm with the loop closed: in unity gain the
    output sits at the input plus the input-referred offset (plus a gain
    error that is 0.1 % here, per docs/results.md).
    """
    rows = []
    for i in range(n):
        at("tt_mm", 25, VDD, seed=1000 + i)
        op = bench_op("miller_ota", LOAD)
        vout = op.get("vout")
        if vout is None or vout != vout:
            continue
        rows.append(dict(seed=1000 + i, vout=vout,
                         vos_mv=(vout - VDD / 2.0) * 1e3))
        print(f"  draw {i+1:2d}/{n}  Vout={vout:.5f}  "
              f"Vos={(vout - VDD/2)*1e3:+7.3f} mV", flush=True)
    reset()
    return rows


def g(v, fmt=".1f", unit=""):
    if v is None or v != v:
        return "--"
    return f"{v:{fmt}}{(' ' + unit) if unit else ''}"


def write(pvt, mc):
    L = ["# PVT corners and Monte Carlo offset\n",
         "Generated by `python tb/corners.py`. The benches are the same "
         "`bench_op` / `bench_ac` used everywhere else — only "
         "`common.ENV` changes — so these numbers are comparable to "
         "`results.md` line for line.\n"]

    if pvt:
        L.append("## Compensation across PVT\n")
        L.append(f"Process x temperature at {VDD} V, plus ±10 % supply at "
                 f"tt/25 °C. Targets: PM ≥ {PM_TARGET:.0f}°, "
                 f"UGF ≥ {UGF_TARGET/1e6:.0f} MHz.\n")
        for name in COMP:
            sub = [r for r in pvt if r["comp"] == name]
            if not sub:
                continue
            pms = [r["pm_deg"] for r in sub if r["pm_deg"] is not None]
            ugfs = [r["ugf_hz"] for r in sub if r["ugf_hz"] is not None]
            worst_pm = min(pms) if pms else None
            worst_ugf = min(ugfs) if ugfs else None
            wr = min((r for r in sub if r["pm_deg"] is not None),
                     key=lambda r: r["pm_deg"], default=None)
            ok = (worst_pm is not None and worst_pm >= PM_TARGET and
                  worst_ugf is not None and worst_ugf >= UGF_TARGET)
            where = (f" ({wr['process']}/{wr['temp']:+d} °C/{wr['vdd']} V)"
                     if wr else "")
            verdict = ("**meets both targets at every corner**" if ok
                       else "**FAILS at some corner**")
            L.append(f"### {name}\n")
            L.append(f"**Worst-corner PM {g(worst_pm)}°**{where}, "
                     f"worst UGF {g(worst_ugf and worst_ugf/1e6, '.2f')} MHz "
                     f"— {verdict}.\n")
            L.append("| process | temp | Vdd | gain @1 Hz | UGF | PM | "
                     "V_out | I_supply | devices out of saturation |")
            L.append("|---|---|---|---|---|---|---|---|---|")
            for r in sub:
                flag = "" if (r["pm_deg"] or 0) >= PM_TARGET else " ⚠"
                L.append(
                    f"| {r['process']} | {r['temp']:+d} °C | {r['vdd']} V "
                    f"| {g(r['a_lf_db'])} dB "
                    f"| {g(r['ugf_hz'] and r['ugf_hz']/1e6, '.2f')} MHz "
                    f"| {g(r['pm_deg'])}°{flag} "
                    f"| {g(r['vout'], '.3f')} V "
                    f"| {g(r['isupply'] and r['isupply']*1e6, '.1f')} µA "
                    f"| {', '.join(r['out_of_sat']) or '—'} |")
            L.append("")

    if mc:
        vos = [r["vos_mv"] for r in mc]
        mean = statistics.mean(vos)
        sd = statistics.pstdev(vos) if len(vos) > 1 else 0.0
        L.append("## Monte Carlo input offset (mismatch)\n")
        L.append(f"`tt_mm` corner, {len(vos)} draws, unity-gain buffer, "
                 "one `.option seed` per draw.\n")
        L.append(f"- mean **{mean:+.3f} mV**, sigma **{sd:.3f} mV**")
        L.append(f"- range {min(vos):+.3f} .. {max(vos):+.3f} mV")
        L.append(f"- 3-sigma estimate **±{3*sd:.2f} mV** "
                 f"(worst |offset| seen: {max(abs(v) for v in vos):.3f} mV)")
        swing_pct = 3 * sd / (1000 * 0.5) * 100    # vs 1 V pp half-swing
        L.append(f"- that 3σ is {swing_pct:.2f} % of the 0.5 V peak "
                 "output swing, and it sits behind the 47 µF coupling "
                 "capacitor, so it costs headroom rather than appearing "
                 "at the jack\n")
        L.append("| seed | V_out | offset |")
        L.append("|---|---|---|")
        for r in mc:
            L.append(f"| {r['seed']} | {r['vout']:.5f} V "
                     f"| {r['vos_mv']:+.3f} mV |")
        L.append("")

    p = Path(ROOT / "docs" / "corners.md")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {p}")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "both"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else MC_DRAWS
    cache = OUT / "corners.json"
    data = {}
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
        except ValueError:
            data = {}
    if what in ("pvt", "both"):
        print("=== PVT ===", flush=True)
        data["pvt"] = run_pvt()
        cache.write_text(json.dumps(data, indent=1))
    if what in ("mc", "both"):
        print("=== Monte Carlo offset ===", flush=True)
        data["mc"] = run_mc(n)
        cache.write_text(json.dumps(data, indent=1))
    write(data.get("pvt"), data.get("mc"))


if __name__ == "__main__":
    main()
