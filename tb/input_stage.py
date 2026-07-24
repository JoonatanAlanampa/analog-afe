"""Input-stage candidate bench -- the path to THD < 0.1 % at the full 1 Vpp.

The THD residual (0.167 % at 1 Vpp, `docs/thd.md` / `docs/cmrr.md`) is NOT the
output stage: the ICMR bench proved it is the HIGH-SIDE INPUT wall -- miller_ota's
NMOS input pair triodes at V_CM = 1.40 V because its drains are PINNED at ~0.9 V
by the PMOS diode mirror (confirmed by a V_CM sweep: xm2 saturation margin crosses
zero exactly at 1.40 V = the 1 Vpp peak). More output current cannot reach it.

This benches candidate INPUT topologies that widen the high-side ICMR, at the SAME
fix operating-point context miller_ota uses (drive into the `line` load, output =
common mode in unity gain). Every candidate carries the miller_ota interface
(vinp vinn vout vb vdd vss) + the pout/Cc/Rz knobs, so the SAME benches measure it.

  miller_ota -- baseline (the wall at 1.40 V).
  miller_fc  -- folded-cascode NMOS input: routes each input drain to a fold node
                fed by a PMOS current source, so it sits ~VDD-|Vdsat| ~ 1.6 V
                instead of 0.9 V -> the input device keeps saturation with its
                gate near VDD. Single pair (no gm-doubling / double-offset), keeps
                the good low side. The primary candidate.
  miller_rr  -- complementary rail-to-rail input (the textbook comparison the
                topology review named), for the cost check.

What it measures per candidate (all tagged with every result-changing param, and
the ICMR asymmetry reported both directions -- the repo's standing rules):
  op    -- Iq + every device's saturation margin at V_CM = 0.9 V.
  icmr  -- V_CM sweep: open-loop gain + input-pair saturation; the high/low walls
           and the functional (within-3 dB) range. THE decision metric: does the
           high wall clear the 1.40 V peak with margin?
  thd   -- THD vs output swing 0.4..1.4 Vpp AND vs frequency at 1 Vpp. The 1 Vpp
           number is the target (< 0.1 %); the swing sweep confirms the mechanism.
  ac    -- open-loop gain / UGF / phase margin (compensation still valid?).

    python tb/input_stage.py op   miller_fc
    python tb/input_stage.py icmr miller_fc
    python tb/input_stage.py thd  miller_fc
    python tb/input_stage.py ac   miller_fc
    python tb/input_stage.py all  miller_fc      # -> docs/input-stage.md section
"""
import math
import re
import sys
from pathlib import Path

from common import (VDD, OUT, ROOT, ENV, header, ib_of, load_net, run_ngspice,
                    parse_meas, read_wrdata, SPICE)
from benches import bench_ac, bench_op, bench_cmrr, devices

FANAL = re.compile(r"THD:\s*([0-9.]+)\s*%")
HROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9.eE+-]+)\s+[0-9.eE+-]+\s+"
                  r"([0-9.eE+-]+)", re.M)
LOAD = "line"

# Per-candidate: chosen operating point + which devices form the input pair(s).
# tail/in devices are reported for saturation over the ICMR sweep; a complementary
# candidate lists BOTH an n-pair and a p-pair (asymmetric-both-directions).
N = "sky130_fd_pr__nfet_01v8"
P = "sky130_fd_pr__pfet_01v8"
CAND = {
    "miller_ota": dict(comp="pcc=4e-12 prz=10000", pout=2.5,
                       watch={"tail": ("m0", N), "in- (xm1)": ("m1", N),
                              "in+ (xm2)": ("m2", N)}),
    "miller_fc":  dict(comp="pcc=4e-12 prz=10000", pout=2.5,
                       watch={"n-tail": ("m0", N), "n-in- (xm1)": ("m1", N),
                              "n-in+ (xm2)": ("m2", N),
                              "p-src (xm9)": ("m9", P)}),
    "miller_rr":  dict(comp="pcc=8e-12 prz=10000", pout=2.5,
                       watch={"n-tail": ("m0", N), "n-in+ (xm2)": ("m2", N),
                              "p-tail": ("mp0", P), "p-in+ (xmp2)": ("mp2", P)}),
    "miller_rrf": dict(comp="pcc=8e-12 prz=10000", pout=2.5,
                       watch={"n-tail": ("m0", N), "n-in+ (xm2)": ("m2", N),
                              "p-tail": ("mp0", P), "p-in+ (xmp2)": ("mp2", P),
                              "p-src (xm9)": ("m9", P)}),
    "miller_rrf2":dict(comp="pcc=9e-12 prz=10000", pout=2.5,
                       watch={"n-tail": ("m0", N), "n-in+ (xm2)": ("m2", N),
                              "p-in+ (xmp2)": ("mp2", P), "casc (xm16)": ("m16", N),
                              "mir (xm14)": ("m14", N)}),
}

SWINGS = [0.4, 0.6, 0.8, 1.0, 1.2, 1.4]     # Vpp; 1.0 = spec row-3 min
FREQS = [20, 100, 1000, 10000, 20000]
FREQ_LABEL = {20: "20 Hz", 100: "100 Hz", 1000: "1 kHz",
              10000: "10 kHz", 20000: "20 kHz"}


def sub(topo):
    return (SPICE / f"{topo}.sp").read_text()


def params_of(topo):
    c = CAND[topo]
    return f"{c['comp']} pout={c['pout']}"


# ------------------------------------------------------------------ op ----
def run_op(topo):
    """Iq + saturation margin of every device at V_CM = 0.9 V. Reuses bench_op,
    which auto-discovers the device list, so it works for any candidate."""
    r = bench_op(topo, LOAD, tag_extra="_is", params=params_of(topo))
    triode = [(i, d["sat_margin"]) for i, d in r["devices"].items()
              if d["sat_margin"] < 0]
    return dict(isupply=r["isupply"], vout=r["vout"], converged=r["converged"],
                ndev=len(r["devices"]), triode=triode, devices=r["devices"])


# ---------------------------------------------------------------- icmr ----
def icmr_point(topo, vc):
    """Open-loop DC gain + input-device saturation at one input common mode.

    The 1 GH inductor closes the loop at DC so vinp=vinn=vout=vc (the CM is the
    signal in unity gain); the differential AC reads the open-loop gain there."""
    watch = CAND[topo]["watch"]
    tag = f"is_icmr_{topo}_{int(round(vc*1000))}"
    prints = []
    for _lbl, (inst, mod) in watch.items():
        prints.append(f"print @m.xdut.x{inst}.m{mod}[vds]")
        prints.append(f"print @m.xdut.x{inst}.m{mod}[vdsat]")
    net = f"""* {topo} ICMR, Vcm={vc}, load={LOAD}
{header()}
{sub(topo)}
vdd vdd 0 dc {VDD}
vss vss 0 0
ib 0 vb dc {ib_of(topo)}
xdut vinp vinn vout vb vdd vss {topo} {params_of(topo)}
{load_net(LOAD)}
vcm vinp 0 dc {vc}
lfb vout vinn 1e9
vac vac 0 dc 0 ac 1
cinj vac vinn 1e9
.control
op
{chr(10).join(prints)}
print v(vout)
ac dec 10 1 1e6
wrdata {tag}.txt v(vout)
.endc
.end
"""
    out = run_ngspice(net, tag)
    vals = parse_meas(out)
    rows = read_wrdata(OUT / f"{tag}.txt", 3)
    a_lf = None
    if rows:
        m0 = math.hypot(rows[0][1], rows[0][2])
        a_lf = 20 * math.log10(m0) if m0 > 0 else -300.0
    devs = {}
    for lbl, (inst, mod) in watch.items():
        vds = vals.get(f"@m.xdut.x{inst}.m{mod}[vds]".lower(), float("nan"))
        vdsat = vals.get(f"@m.xdut.x{inst}.m{mod}[vdsat]".lower(), float("nan"))
        devs[lbl] = abs(vds) - abs(vdsat)
    return dict(vcm=vc, vout=vals.get("v(vout)", float("nan")),
                a_lf_db=a_lf, marg=devs)


def run_icmr(topo):
    rows = [icmr_point(topo, round(0.20 + 0.05 * i, 2)) for i in range(29)]
    for r in rows:
        m = "  ".join(f"{k} {v:+.2f}" for k, v in r["marg"].items())
        print(f"  Vcm {r['vcm']:.2f}  A_dc {r['a_lf_db'] or float('nan'):6.1f} dB"
              f"  Vout {r['vout']:+.3f} | {m}", flush=True)
    return rows


def icmr_walls(rows, drop_db=3.0):
    """Functional CM range (within drop_db of peak gain) + the V_CM where the
    signal input pair leaves saturation on each side. Reported both directions
    because the range is asymmetric and that asymmetry is the whole THD story."""
    good = [r for r in rows if r["a_lf_db"] is not None]
    peak = max(r["a_lf_db"] for r in good)
    ok = [r for r in good if r["a_lf_db"] >= peak - drop_db]
    lo, hi = min(r["vcm"] for r in ok), max(r["vcm"] for r in ok)
    return dict(peak=peak, lo=lo, hi=hi)


# ----------------------------------------------------------------- thd ----
def run_thd(topo, freq, vpp):
    c = CAND[topo]
    amp = vpp / 2.0
    tstop, tstep = 20.0 / freq, 1.0 / (freq * 500)
    ctag = re.sub(r"\W+", "", c["comp"])
    tag = f"is_thd_{topo}_{int(freq)}_{int(vpp*1000)}_{LOAD}_p{c['pout']}_{ctag}"
    net = f"""* {topo} THD {freq}Hz {vpp}Vpp p{c['pout']}
{header()}
{sub(topo)}
vdd vdd 0 dc {VDD}
vss vss 0 0
ib 0 vb dc {ib_of(topo)}
xdut vin vout vout vb vdd vss {topo} {params_of(topo)}
{load_net(LOAD)}
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
    harm = {int(r.group(1)): float(r.group(4)) for r in HROW.finditer(out)}
    return dict(thd_pct=thd, h2=harm.get(2), h3=harm.get(3))


def run_thd_swing(topo):
    rows = []
    for vpp in SWINGS:
        r = run_thd(topo, 1000, vpp)
        rows.append(dict(vpp=vpp, **r))
        lo, hi = VDD / 2 - vpp / 2, VDD / 2 + vpp / 2
        t = r["thd_pct"]
        print(f"  swing {vpp:.1f} Vpp (out {lo:.2f}-{hi:.2f}) -> "
              f"THD {t if t is None else f'{t:.4f}'}%  "
              f"(h2 {hp(r['h2'])} h3 {hp(r['h3'])})", flush=True)
    return rows


def run_thd_freq(topo):
    rows = []
    for f in FREQS:
        r = run_thd(topo, f, 1.0)
        rows.append(dict(freq=f, **r))
        t = r["thd_pct"]
        print(f"  freq {FREQ_LABEL[f]:>6} @1Vpp -> "
              f"THD {t if t is None else f'{t:.4f}'}%", flush=True)
    return rows


# ------------------------------------------------------------------ ac ----
def run_ac(topo):
    r = bench_ac(topo, LOAD, params=params_of(topo), tag_extra="_is")
    print(f"  A_lf {r.get('a_lf_db', float('nan')):.1f} dB  UGF "
          f"{(r.get('ugf_hz') or 0)/1e6:.2f} MHz  PM "
          f"{r.get('pm_deg') or float('nan'):.1f} deg  A@20k "
          f"{r.get('a_20k_db', float('nan')):.1f} dB", flush=True)
    return r


def hp(x):
    return "--" if x is None else f"{x*100:.4f}%"


# ---------------------------------------------------------------- pvt ----
PROCESS = ["tt", "ss", "ff", "sf", "fs"]
TEMPS = [-40, 25, 85]
SUPPLIES = [1.62, 1.98]


def run_pvt(topo):
    """PM / UGF / gain / Iq across process x temp x supply, using the SAME
    bench_ac/bench_op as nominal (common.ENV mutated) so numbers are
    comparable line-for-line. Reports the worst corner -- the only honest
    basis for a stability claim."""
    pts = [(p, t, VDD) for p in PROCESS for t in TEMPS]
    pts += [("tt", 25, v) for v in SUPPLIES]
    par = params_of(topo)
    pout_only = f"pout={CAND[topo]['pout']}"
    rows = []
    for (p, t, v) in pts:
        ENV.update(corner=p, temp=t, vdd=v, seed=None)
        tag = f"_is_{topo}_{p}_{t}_{v}".replace(".", "p")
        ac = bench_ac(topo, LOAD, params=par, tag_extra=tag)
        op = bench_op(topo, LOAD, tag_extra=tag, params=pout_only)
        bad = (["NO OP"] if not op.get("converged", True) else
               [i for i, d in op["devices"].items() if not (d["sat_margin"] > 0)])
        rows.append(dict(process=p, temp=t, vdd=v, a_lf_db=ac.get("a_lf_db"),
                         ugf_hz=ac.get("ugf_hz"), pm_deg=ac.get("pm_deg"),
                         isupply=op.get("isupply"), vout=op.get("vout"),
                         out_of_sat=bad))
        print(f"  {p:2s} {t:+4d}C {v:.2f}V  A={ac.get('a_lf_db') or 0:5.1f}dB  "
              f"UGF={(ac.get('ugf_hz') or 0)/1e6:6.2f}MHz  "
              f"PM={ac.get('pm_deg') or float('nan'):6.1f}deg  "
              f"Iq={(op.get('isupply') or 0)*1e6:5.0f}uA  "
              f"{'SAT-FAIL:'+','.join(bad) if bad else ''}", flush=True)
    ENV.update(corner="tt", temp=25, vdd=VDD, seed=None)
    pms = [r["pm_deg"] for r in rows if r["pm_deg"] is not None]
    ugfs = [r["ugf_hz"] for r in rows if r["ugf_hz"] is not None]
    iqs = [r["isupply"] for r in rows if r["isupply"] is not None]
    wr = min((r for r in rows if r["pm_deg"] is not None),
             key=lambda r: r["pm_deg"], default=None)
    print(f"PVT worst: PM {min(pms):.1f} deg @ "
          f"{wr['process']}/{wr['temp']:+d}C/{wr['vdd']}V, worst UGF "
          f"{min(ugfs)/1e6:.2f} MHz, worst Iq {max(iqs)*1e6:.0f} uA", flush=True)
    return rows


# ----------------------------------------------------------------- mc ----
def run_mc(topo, n=30):
    """Input offset from mismatch, unity-gain buffer, tt_mm, N seeds."""
    import statistics
    vos = []
    for i in range(n):
        ENV.update(corner="tt_mm", temp=25, vdd=VDD, seed=1000 + i)
        op = bench_op(topo, LOAD, tag_extra=f"_is_mc_{topo}",
                      params=f"pout={CAND[topo]['pout']}")
        vout = op.get("vout")
        if vout is None or vout != vout:
            continue
        vos.append((vout - VDD / 2.0) * 1e3)
        print(f"  draw {i+1:2d}/{n}  Vout={vout:.5f}  Vos={vos[-1]:+7.3f} mV",
              flush=True)
    ENV.update(corner="tt", temp=25, vdd=VDD, seed=None)
    if vos:
        sd = statistics.pstdev(vos) if len(vos) > 1 else 0.0
        print(f"MC offset: mean {statistics.mean(vos):+.3f} mV, sigma {sd:.3f} "
              f"mV, 3-sigma ±{3*sd:.2f} mV (N={len(vos)})", flush=True)
    return vos


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    topo = sys.argv[2] if len(sys.argv) > 2 else "miller_fc"
    print(f"=== {topo}  ({params_of(topo)}) ===", flush=True)
    if what in ("op", "all"):
        o = run_op(topo)
        print(f"op: Iq {o['isupply']*1e6:.1f} uA  Vout {o['vout']:+.3f}  "
              f"{o['ndev']} devices  triode={o['triode']}", flush=True)
    if what in ("ac", "all"):
        run_ac(topo)
    if what in ("icmr", "all"):
        rows = run_icmr(topo)
        w = icmr_walls(rows)
        print(f"ICMR: peak {w['peak']:.1f} dB, 3dB range "
              f"{w['lo']:.2f}..{w['hi']:.2f} V  (1Vpp needs 0.40..1.40)",
              flush=True)
    if what in ("thd", "all"):
        print("THD vs swing:", flush=True)
        run_thd_swing(topo)
        print("THD vs freq:", flush=True)
        run_thd_freq(topo)
    if what == "pvt":
        run_pvt(topo)
    if what == "mc":
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        run_mc(topo, n)
    if what == "thdc":
        # 1 Vpp / 1 kHz THD at the worst PVT corners (run_thd reads ENV via
        # header(), so mutating ENV sweeps the corner with the SAME bench).
        pts = [("tt", 25, VDD), ("ss", -40, VDD), ("ss", 85, VDD),
               ("ff", -40, VDD), ("ff", 85, VDD), ("fs", 25, VDD),
               ("tt", 25, 1.62), ("tt", 25, 1.98)]
        for (p, t, v) in pts:
            ENV.update(corner=p, temp=t, vdd=v, seed=None)
            t1k = run_thd(topo, 1000, 1.0)["thd_pct"]
            t20k = run_thd(topo, 20000, 1.0)["thd_pct"]
            s1 = "--" if t1k is None else f"{t1k:.4f}%"
            s2 = "--" if t20k is None else f"{t20k:.4f}%"
            flag = "" if (t1k or 1) < 0.1 else "  <== OVER 0.1%"
            print(f"  {p:2s} {t:+4d}C {v:.2f}V -> THD@1k {s1}  @20k {s2}{flag}",
                  flush=True)
        ENV.update(corner="tt", temp=25, vdd=VDD, seed=None)
    if what == "cmrr":
        r = bench_cmrr(topo, LOAD, params=params_of(topo), tag_extra="_is")
        print(f"CMRR: DC {r.get('cmrr_dc_db', float('nan')):.1f}  1k "
              f"{r.get('cmrr_1k_db', float('nan')):.1f}  20k "
              f"{r.get('cmrr_20k_db', float('nan')):.1f} dB "
              f"(A_dm/A_cm DC {r.get('adm_dc_db', float('nan')):.1f}/"
              f"{r.get('acm_dc_db', float('nan')):.1f})", flush=True)


if __name__ == "__main__":
    main()
