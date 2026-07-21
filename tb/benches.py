"""The four benches. Each builds a netlist, runs ngspice, returns metrics.

  op   -- DC operating point: every device's region, gm, gds, plus the
          quiescent supply current (audio blocks live inside a chip whose
          power budget is real).
  ac   -- open-loop gain / UGF / phase margin / gain margin. The loop is
          closed at DC through a 1 GH inductor and opened at AC; the
          stimulus is injected through a 1 GF cap. That keeps the DC
          operating point IDENTICAL to the closed-loop one -- breaking the
          loop with a voltage source instead would bias the amp at an
          operating point it never actually sees.
  psrr -- vdd-to-output rejection in the unity-gain configuration. Called
          out in the spec because this block sits on a die next to a CPU
          and a video timing generator.
  tran -- 100 mV step into the load, unity-gain buffer: slew rate and
          0.1 % settling time.
"""
import math
import re

from common import (LOADS, OUT, header, topo_include, ib_of, vdd, vcm,
                    subckt_of, load_net, run_ngspice, parse_meas,
                    read_wrdata)

DEV_RE = re.compile(
    r"^x(\w+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(sky130_fd_pr__\w+)",
    re.M | re.I)

OP_PARAMS = ["id", "gm", "gds", "vth", "vdsat", "vgs", "vds"]


def devices(topo):
    """(inst, drain, gate, source, model) for every transistor."""
    return [(m.group(1), m.group(2), m.group(3), m.group(4), m.group(6))
            for m in DEV_RE.finditer(topo_include(topo))]


def _preamble(topo, load, vinn="vinn", vinp="vinp", params=""):
    return f"""{header()}
{topo_include(topo)}
vdd vdd 0 dc {vdd()}
vss vss 0 0
* bias: source pushes IB INTO vb (diode-connected NMOS to vss)
ib 0 vb dc {ib_of(topo)}
xdut {vinp} {vinn} vout vb vdd vss {subckt_of(topo)} {params}
{load_net(load)}
"""


# ---------------------------------------------------------------- op ----
def bench_op(topo, load, tag_extra=""):
    # tag_extra is required for corner sweeps (H1): without it, every
    # corner's operating-point run writes op_<topo>_<load>.{sp,log},
    # overwriting the previous corner's artifacts. Even though the
    # returned numbers come from stdout (so the values are per-run
    # correct), a run that fails to converge leaves NO recoverable .log
    # to debug -- the next corner has already overwritten it -- and,
    # worse, a failed parse is silently rendered as "all devices out of
    # saturation" below. See the `converged` guard.
    tag = f"op_{topo}_{load}{tag_extra}"
    prints = []
    for inst, _d, _g, _s, model in devices(topo):
        for p in OP_PARAMS:
            prints.append(f"print @m.xdut.x{inst}.m{model}[{p}]")
    net = f"""* {topo} DC operating point, load={load}
{_preamble(topo, load)}
vcm vinp 0 dc {vcm()}
* unity-gain feedback so the output finds its own bias point
lfb vout vinn 1e9
.control
op
{chr(10).join(prints)}
let itot = abs(i(vdd))
echo isupply = $&itot
print v(vout)
.endc
.end
"""
    out = run_ngspice(net, tag)
    vals = parse_meas(out)
    # A missing v(vout) means the op-point analysis did not produce
    # readable results (non-convergence, or a corrupted run). Say so --
    # do NOT let the sat_margin logic below turn NaN Vds into a confident
    # "every device is in the linear region", which is how a failed run
    # masqueraded as a circuit result in the first corners.md.
    converged = "v(vout)" in vals
    devs = {}
    for inst, d, g, s, model in devices(topo):
        row = {}
        for p in OP_PARAMS:
            row[p] = vals.get(f"@m.xdut.x{inst}.m{model}[{p}]".lower(),
                              float("nan"))
        # saturation margin, polarity-independent
        row["sat_margin"] = abs(row["vds"]) - abs(row["vdsat"])
        row["model"] = model
        row["nodes"] = (d, g, s)
        devs[inst] = row
    return dict(isupply=vals.get("isupply", float("nan")),
                vout=vals.get("v(vout)", float("nan")),
                converged=converged, devices=devs)


# ---------------------------------------------------------------- ac ----
def bench_ac(topo, load, params="", tag_extra=""):
    tag = f"ac_{topo}_{load}{tag_extra}"
    net = f"""* {topo} open-loop AC, load={load} {params}
{_preamble(topo, load, params=params)}
vcm vinp 0 dc {vcm()}
* DC feedback, AC open
lfb vout vinn 1e9
vac vac 0 dc 0 ac 1
cinj vac vinn 1e9
.ac dec 40 1 1e9
.control
run
wrdata {tag}.txt v(vout)
.endc
.end
"""
    run_ngspice(net, tag)
    rows = read_wrdata(OUT / f"{tag}.txt", 3)
    if len(rows) < 10:
        return dict(error="no AC data")
    f = [r[0] for r in rows]
    mag = [math.hypot(r[1], r[2]) for r in rows]
    ph = [math.degrees(math.atan2(r[2], r[1])) for r in rows]
    # unwrap, then reference so the low-frequency (inverting) phase is +180
    for i in range(1, len(ph)):
        while ph[i] - ph[i - 1] > 180:
            ph[i] -= 360
        while ph[i] - ph[i - 1] < -180:
            ph[i] += 360
    if ph[0] < 0:
        ph = [p + 360 for p in ph]

    db = [20 * math.log10(m) if m > 0 else -300 for m in mag]
    res = dict(a_lf_db=db[0])

    def cross(ys, target, start=1, last=False):
        """Interpolated crossing of `target`. last=True scans backwards.

        UGF MUST be the LAST 0 dB crossing, not the first: on the
        AC-coupled corners the 47 uF cap high-passes the response, so
        the gain RISES out of the low-frequency end and crosses 0 dB on
        the way up. Taking the first crossing reported a 32 ohm
        headphone corner with a 2.85 Hz "unity-gain frequency" -- the
        coupling pole, mislabelled. Same trap in the phase search, so
        the gain-margin scan starts at the UGF index instead of at DC.
        """
        rng = range(len(ys) - 1, start, -1) if last else \
            range(start, len(ys))
        for i in rng:
            if (ys[i - 1] - target) * (ys[i] - target) <= 0 and \
                    ys[i] != ys[i - 1]:
                t = (target - ys[i - 1]) / (ys[i] - ys[i - 1])
                lf = math.log10(f[i - 1]) + t * (math.log10(f[i]) -
                                                 math.log10(f[i - 1]))
                return 10 ** lf, i - 1 + t
        return None, None

    ugf, idx = cross(db, 0.0, last=True)
    res["ugf_hz"] = ugf
    if idx is not None:
        i = int(idx)
        t = idx - i
        res["pm_deg"] = ph[i] + t * (ph[min(i + 1, len(ph) - 1)] - ph[i])
    else:
        res["pm_deg"] = None
    # gain margin: gain where the phase reaches 0 deg, searched from UGF up
    fgm, idxp = cross(ph, 0.0, start=max(1, int(idx or 1)))
    if idxp is not None:
        i = int(idxp)
        t = idxp - i
        res["gm_db"] = -(db[i] + t * (db[min(i + 1, len(db) - 1)] - db[i]))
        res["f_gm_hz"] = fgm
    else:
        res["gm_db"] = None
        res["f_gm_hz"] = None
    # closed-loop -3 dB point of the unity buffer ~ UGF; also report the
    # open-loop gain still available at 20 kHz (that sets audio distortion)
    for i, fi in enumerate(f):
        if fi >= 20e3:
            res["a_20k_db"] = db[i]
            break
    return res


# -------------------------------------------------------------- psrr ----
def bench_psrr(topo, load, tag_extra=""):
    # tag_extra for corner sweeps (H2): same untagged-artifact hazard as
    # bench_op, latent until PSRR is swept over corners.
    tag = f"psrr_{topo}_{load}{tag_extra}"
    net = f"""* {topo} PSRR (unity gain), load={load}
{header()}
{topo_include(topo)}
vdd vdd 0 dc {vdd()} ac 1
vss vss 0 0
* bias: source pushes IB INTO vb (diode-connected NMOS to vss)
ib 0 vb dc {ib_of(topo)}
vcm vinp 0 dc {vcm()}
xdut vinp vout vout vb vdd vss {subckt_of(topo)}
{load_net(load)}
.ac dec 20 1 1e9
.control
run
wrdata {tag}.txt v(vout)
.endc
.end
"""
    run_ngspice(net, tag)
    rows = read_wrdata(OUT / f"{tag}.txt", 3)
    if len(rows) < 10:
        return dict(error="no AC data")
    out = {}
    for label, freq in (("dc", 1.0), ("1k", 1e3), ("20k", 2e4)):
        best = min(rows, key=lambda r: abs(math.log10(max(r[0], 1e-12)) -
                                           math.log10(freq)))
        mag = math.hypot(best[1], best[2])
        out[f"psrr_{label}_db"] = (-20 * math.log10(mag) if mag > 0
                                   else float("inf"))
    return out


# -------------------------------------------------------------- tran ----
def bench_tran(topo, load, params="", tag_extra=""):
    """100 mV step UP and back DOWN, unity gain.

    BOTH edges, and that is the whole point. These are class-A output
    stages: the two directions are driven by different devices and are
    NOT symmetric. miller_ota sources through xm5 (a PMOS common-source
    that can pull hard) but sinks through xm6, a current sink pinned at
    61.5 uA -- so the FALLING edge is the limited one. A rising-only
    step measures the easy direction and flatters every candidate.
    `slew_v_per_us` is therefore the WORSE of the two edges; the
    individual rates are reported alongside it.
    """
    tag = f"tran_{topo}_{load}{tag_extra}"
    # the 147 nF Pmod corner is three orders of magnitude slower than the
    # others -- give it its own time base rather than under-resolving it
    tstop, tstep = (3e-3, 100e-9) if load == "pmodrc" else (60e-6, 2e-9)
    t_up, t_dn = 0.25 * tstop, 0.625 * tstop
    net = f"""* {topo} 100 mV step up and down, unity gain, load={load}
{header()}
{topo_include(topo)}
vdd vdd 0 dc {vdd()}
vss vss 0 0
* bias: source pushes IB INTO vb (diode-connected NMOS to vss)
ib 0 vb dc {ib_of(topo)}
xdut vin vout vout vb vdd vss {subckt_of(topo)} {params}
{load_net(load)}
vin vin 0 dc {vcm()} pulse({vcm()} {vcm() + 0.1} {t_up:.9g} 10n 10n {t_dn - t_up:.9g} {10 * tstop:.9g})
.tran {tstep:.9g} {tstop:.9g}
.control
run
wrdata {tag}.txt v(vout) v(vin)
.endc
.end
"""
    run_ngspice(net, tag)
    rows = read_wrdata(OUT / f"{tag}.txt", 3)
    if len(rows) < 10:
        return dict(error="no transient data")
    t = [r[0] for r in rows]
    v = [r[1] for r in rows]

    def level(t_lo, t_hi):
        seg = [v[i] for i in range(len(t)) if t_lo <= t[i] <= t_hi]
        return sum(seg) / len(seg) if seg else None

    # settled levels in the last 5 % of each plateau
    v0 = level(t_up - 0.05 * t_up, t_up)
    v1 = level(t_dn - 0.05 * (t_dn - t_up), t_dn)
    v2 = level(tstop - 0.05 * (tstop - t_dn), tstop)
    if v0 is None or v1 is None or v2 is None:
        return dict(error="step window empty")

    swing = v1 - v0
    res = dict(v0=v0, v1=v1, v2=v2, step_out_mv=swing * 1e3,
               gain_err_pct=(swing / 0.1 - 1) * 100)

    def edge(t_edge, t_end, a, b):
        """10-90 % rate and 0.1 % settling for one edge, a -> b."""
        d = b - a
        out = {}
        if abs(d) < 1e-4:
            return out
        lo, hi = a + 0.1 * d, a + 0.9 * d
        sgn = 1 if d > 0 else -1
        tl = th = None
        for i in range(len(t)):
            if t[i] < t_edge or t[i] > t_end:
                continue
            if tl is None and (v[i] - lo) * sgn >= 0:
                tl = t[i]
            if th is None and (v[i] - hi) * sgn >= 0:
                th = t[i]
                break
        if tl is not None and th is not None and th > tl:
            out["rate"] = abs(hi - lo) / (th - tl) / 1e6
        tol = abs(d) * 1e-3
        for i in range(len(t) - 1, -1, -1):
            if t[i] < t_edge or t[i] > t_end:
                continue
            if abs(v[i] - b) > tol:
                out["tsettle"] = (t[i] - t_edge) * 1e6
                break
        seg = [v[i] for i in range(len(t)) if t_edge <= t[i] <= t_end]
        if seg:
            peak = max(seg) if d > 0 else min(seg)
            out["overshoot"] = abs((peak - b) / d) * 100
        return out

    up = edge(t_up, t_dn, v0, v1)
    dn = edge(t_dn, tstop, v1, v2)
    res["slew_rise_v_per_us"] = up.get("rate")
    res["slew_fall_v_per_us"] = dn.get("rate")
    rates = [r for r in (up.get("rate"), dn.get("rate")) if r is not None]
    if rates:
        res["slew_v_per_us"] = min(rates)          # the limiting direction
        if len(rates) == 2 and min(rates) > 0:
            res["slew_asym"] = max(rates) / min(rates)
    res["tsettle_us"] = up.get("tsettle", 0.0)
    res["tsettle_fall_us"] = dn.get("tsettle", 0.0)
    res["overshoot_pct"] = up.get("overshoot")
    return res


BENCHES = dict(op=bench_op, ac=bench_ac, psrr=bench_psrr, tran=bench_tran)
