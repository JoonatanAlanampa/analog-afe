"""Comparator bench -- phase 3. Two candidates, measured, not asserted.

The block: the decision element of the paddle SAR (docs/spec-comparator.md).
Candidate 1 is a bare StrongARM latch (`spice/strongarm.sp`); candidate 2 puts
a pre-amp in front of that SAME latch (`spice/comparator.sp`). The question the
bench answers is whether the pre-amp earns its quiescent current, and the answer
has to come from offset, kickback and hysteresis rather than from the textbook.

WHY THESE METRICS, for THIS job (all traced in docs/spec-comparator.md):
  * offset      -- a STATIC offset in a SAR is a benign full-scale shift, so the
                   number that matters is its SPREAD (sigma over mismatch), not
                   one draw's value. Monte Carlo, `tt_mm`.
  * hysteresis  -- a clocked comparator remembers its last decision through the
                   nodes the reset phase failed to clear. In a SAR the previous
                   decision is CORRELATED with the current one (a binary search
                   walks toward the answer), so hysteresis is NOT averaged away
                   and is a first-order error. Measured as the gap between the
                   threshold approached after a + decision and after a -.
  * delay, BOTH directions -- the repo's standing lesson (design-notes 5): a
                   one-directional stimulus measures the better direction. A
                   StrongARM's two outputs are pulled by different devices.
  * metastability -- delay vs overdrive gives the regeneration time constant
                   tau directly (t_d = t_0 + tau*ln(V_x/dV)); the SAR's error
                   probability follows from tau and the time a bit trial has.
  * kickback    -- the input is the DAC's ~1 pF top plate, a CHARGE-HOLDING
                   node: charge the comparator pushes back into it is a
                   conversion error, not a settling nuisance. Budget 3.5 fC
                   (= 0.5 LSB on 1 pF at 8 bits over 1.8 V).
  * charge/decision -- the honest current metric for a clocked block. The bare
                   latch draws ZERO static current, so quoting "Iq" would hand
                   it the comparison by definition; what is comparable is the
                   charge each decision costs plus whatever is burned between
                   decisions.

    python tb/comparator.py op        strongarm
    python tb/comparator.py thr       strongarm     # threshold + hysteresis
    python tb/comparator.py delay     strongarm     # both directions vs overdrive
    python tb/comparator.py meta      strongarm     # regeneration tau
    python tb/comparator.py kick      strongarm     # into a 1 pF top plate
    python tb/comparator.py mc        strongarm 30  # offset sigma
    python tb/comparator.py pvt       strongarm
    python tb/comparator.py all       strongarm
"""
import json
import math
import re
import statistics
import sys

from common import (VDD, OUT, ENV, header, run_ngspice, SPICE)

# common.parse_meas anchors on end-of-line, which is right for `print` output
# but silently drops EVERY `meas` result: ngspice appends the measurement
# window ("istat = -7.7e-07 from= 4.5e-08 to= 5.0e-08"). The first version of
# this bench reported nan for every current until that was traced -- a parser
# that matches nothing looks exactly like a circuit that measured nothing.
MEAS_RE = re.compile(r"^(\w+)\s*=\s*([-+0-9.eE]+)", re.M)


def meas(stdout):
    vals = {}
    for m in MEAS_RE.finditer(stdout):
        try:
            vals[m.group(1).lower()] = float(m.group(2))
        except ValueError:
            pass
    return vals

# ---------------------------------------------------------------- setup ----
# Both candidates present the same pins EXCEPT the bias node: the bare latch is
# fully clocked and needs no reference at all, which is itself a result.
CAND = {
    "strongarm":  dict(sub="strongarm",  bias=False, params="mi=4 li=1",
                       needs=[]),
    "comparator": dict(sub="comparator", bias=True,
                       params="mp=8 lp=1 mi=4 li=1",
                       # candidate 2 instantiates the SAME latch file, so the
                       # comparison is genuinely "what does the pre-amp add"
                       # and not two differently-tuned latches.
                       needs=["strongarm"]),
}

CLOAD = 10e-15      # SAR logic gate load on each output
IB = 20e-6          # same constant-gm reference the audio buffer uses

# Input common mode. Mutable, like common.ENV, because spec row 11 is a SWEEP:
# the DAC top plate does not sit politely at mid-rail -- how far it moves is
# decided by phase 4's switching scheme, so every metric here has to be
# measurable at any common mode using the SAME code (the corner-sweep lesson
# from tb/corners.py: a sweep that re-implements its own measurement is
# comparing two benches, not two operating points).
CM = {"v": 0.9}


def vcm():
    return CM["v"]

# One transient carries TWO decisions: the first primes the latch's memory
# (that is what makes hysteresis measurable), the second is the one measured.
T_R1, T_E1, T_R2, T_SW, T_E2, T_END = 20e-9, 40e-9, 45e-9, 50e-9, 60e-9, 80e-9
TEDGE = 100e-12
T_SAMPLE = 75e-9    # 15 ns after the measured edge: regeneration is long done


def sub(name):
    """The candidate's netlist plus every subckt it instantiates."""
    parts = [(SPICE / f"{d}.sp").read_text() for d in CAND[name]["needs"]]
    parts.append((SPICE / f"{CAND[name]['sub']}.sp").read_text())
    return "\n".join(parts)


def supplies(cand):
    """Header, models, rails and the two-decision clock -- shared by every copy."""
    return f"""{header()}
{sub(cand)}
vsup vdd 0 dc {ENV["vdd"]}
vgnd vss 0 0
vinn vin 0 dc {vcm()}
vclk clk 0 dc 0 pwl(0 0 {T_R1:g} 0 {T_R1+TEDGE:g} {ENV["vdd"]} {T_E1:g} {ENV["vdd"]}
+ {T_E1+TEDGE:g} 0 {T_E2:g} 0 {T_E2+TEDGE:g} {ENV["vdd"]} {T_END:g} {ENV["vdd"]})
"""


def copy(cand, k, prime_dv, dv, params=None, vcm_k=None):
    """One independent DUT copy at its own overdrive.

    Each copy gets its OWN bias source and vb node. Sharing one 20 uA source
    across N copies would silently divide it -- every copy would run at
    20/N uA and the whole scan would measure a starved comparator.
    """
    c = CAND[cand]
    cm = vcm() if vcm_k is None else vcm_k
    lines = [
        f"vinp{k} vip{k} 0 dc {cm+dv:.9g} pwl(0 {cm+prime_dv:.9g} "
        f"{T_R2:g} {cm+prime_dv:.9g} {T_R2+1e-9:g} {cm+dv:.9g} "
        f"{T_END:g} {cm+dv:.9g})",
    ]
    # each copy carries its OWN reference source when the sweep is over common
    # mode, so one netlist can hold several operating points at once
    refnode = "vin" if vcm_k is None else f"vin{k}"
    if vcm_k is not None:
        lines.append(f"vinn{k} {refnode} 0 dc {cm:.9g}")
    pins = f"vip{k} {refnode} outp{k} outn{k} clk"
    if c["bias"]:
        lines.append(f"ib{k} 0 vb{k} dc {IB}")
        pins += f" vb{k}"
    lines.append(f"xdut{k} {pins} vdd vss {c['sub']} {params or c['params']}")
    lines.append(f"clp{k} outp{k} 0 {CLOAD}")
    lines.append(f"cln{k} outn{k} 0 {CLOAD}")
    return "\n".join(lines)


# ------------------------------------------------------------- decision ----
def scan(cand, dvs, prime_dv, tag, params=None):
    """K primed decisions in ONE ngspice run.

    WHY NOT BISECTION. Bisection needs ~20 SEQUENTIAL runs per threshold, and
    a run here is dominated by loading the sky130 library, not by solving the
    circuit -- so the search cost was ~95 % startup. The decisions at different
    overdrives are independent, so K copies of the DUT go in one netlist and
    the threshold falls out of three K-way scans instead of twenty runs. Same
    measurement, ~7x less wall clock, which is what makes the Monte Carlo and
    PVT sweeps below affordable at all.
    """
    primes = prime_dv if isinstance(prime_dv, (list, tuple)) \
        else [prime_dv] * len(dvs)
    body = "\n".join(copy(cand, k, primes[k], dv, params)
                     for k, dv in enumerate(dvs))
    ms = "\n".join(f"meas tran vop{k} find v(outp{k}) at={T_SAMPLE:g}\n"
                   f"meas tran von{k} find v(outn{k}) at={T_SAMPLE:g}"
                   for k in range(len(dvs)))
    net = f"""* {cand} scan of {len(dvs)} overdrives
{supplies(cand)}
{body}
.tran 20p {T_END:g}
.control
run
{ms}
.endc
.end
"""
    out = run_ngspice(net, tag)
    v = meas(out)
    res = []
    for k in range(len(dvs)):
        vop = v.get(f"vop{k}", float("nan"))
        von = v.get(f"von{k}", float("nan"))
        res.append(dict(dv=dvs[k], vop=vop, von=von, outp_high=vop > von))
    return res


def decide(cand, dv, prime_dv, tag, params=None):
    return scan(cand, [dv], prime_dv, tag, params)[0]


def threshold(cand, prime_dv, lo=-0.06, hi=0.06, rounds=3, k=16, tagx="",
              params=None):
    """Input-referred decision threshold for ONE priming history.

    Successive K-way scans, each bracketing the flip found by the previous one.
    Resolution after `rounds` scans is (hi-lo)/k**rounds -- 120 mV / 16^3 = 29 uV
    by default, which is 1/240 of an LSB and far finer than anything the spec
    asks about.

    A scan rather than a ramp on purpose: a ramp changes the input DURING
    evaluation, so what it reports is a blend of the threshold and the slew,
    and the whole point of this number is that it is measured in microvolts.
    """
    for r in range(rounds):
        dvs = [lo + (hi - lo) * i / (k - 1) for i in range(k)]
        res = scan(cand, dvs, prime_dv, f"cmp_thr_{cand}{tagx}_r{r}", params)
        flip = None
        for i in range(1, len(res)):
            if res[i]["outp_high"] != res[i - 1]["outp_high"]:
                flip = i
                break
        if flip is None:
            return None      # no flip anywhere in the window
        lo, hi = res[flip - 1]["dv"], res[flip]["dv"]
    return 0.5 * (lo + hi)


# ------------------------------------------------------------------ op ----
def run_op(cand):
    """Static current at reset AND at evaluate, plus the charge one decision
    costs. A clocked latch has no meaningful 'Iq' -- reporting only the static
    number would flatter it; reporting only the dynamic one would hide the
    pre-amp's standing burn. Both, always."""
    tag = f"cmp_op_{cand}"
    net = f"""* {cand} static + dynamic current
{supplies(cand)}
{copy(cand, 0, 0.05, 0.05)}
.tran 20p {T_END:g}
.control
run
meas tran istat avg i(vsup) from={T_SW+2e-9:g} to={T_E2-1e-9:g}
meas tran qcyc integ i(vsup) from={T_R1+TEDGE:g} to={T_E2:g}
meas tran qdec integ i(vsup) from={T_E2:g} to={T_END:g}
.endc
.end
"""
    out = run_ngspice(net, tag)
    v = meas(out)
    # ngspice reports supply current NEGATIVE into the source; take magnitude.
    istat = abs(v.get("istat", float("nan")))
    # qcyc spans one COMPLETE decision+reset (rising edge 1 -> rising edge 2),
    # which is the charge a SAR bit trial actually costs. qeval is the evaluate
    # half alone, reported because it is the part that scales with the decision
    # and the part the reset does not pay back.
    qcyc = abs(v.get("qcyc", float("nan")))
    qeval = abs(v.get("qdec", float("nan")))
    return dict(istatic=istat, q_cycle=qcyc, q_evaluate=qeval)


# --------------------------------------------------------------- delay ----
def scan_delay(cand, dvs, tag, params=None):
    """Clock-to-output delay at K overdrives in ONE run.

    Each copy is measured on whichever output RISES for its sign of overdrive:
    a StrongARM's two outputs are pulled by different devices, so measuring
    only `outp` would report the easy direction (design-notes 5).
    """
    body = "\n".join(copy(cand, k, dv, dv, params) for k, dv in enumerate(dvs))
    # THE DECISION IS A FALLING EDGE, AND ON THE LOSER. A StrongARM's reset
    # precharges BOTH outputs to VDD, so evaluation does not raise the winner
    # -- it pulls the loser down. Measuring "when does outp rise" therefore
    # measured the RESET, and it reported nothing at all except at overdrives
    # so small that both outputs drooped and one climbed back: the four points
    # that did return a number were the recovery, not the decision, and the
    # tau fitted from them was meaningless.
    # fall=2 for the same reason trig is rise=2: the priming decision at the
    # first clock edge goes the same way, so the loser has already fallen once.
    ms = []
    for k, dv in enumerate(dvs):
        loser = f"outn{k}" if dv > 0 else f"outp{k}"
        ms.append(f"meas tran td{k} trig v(clk) val={ENV['vdd']/2:g} rise=2 "
                  f"targ v({loser}) val={ENV['vdd']/2:g} fall=2")
    net = f"""* {cand} delay scan, {len(dvs)} overdrives
{supplies(cand)}
{body}
.tran 5p {T_END:g}
.control
run
{chr(10).join(ms)}
.endc
.end
"""
    out = run_ngspice(net, tag)
    v = meas(out)
    return [v.get(f"td{k}") for k in range(len(dvs))]


def delay(cand, dv, tag, params=None):
    return scan_delay(cand, [dv], tag, params)[0]


def run_delay(cand):
    dvs = [0.1, 0.01, 0.001, -0.001, -0.01, -0.1]
    tds = scan_delay(cand, dvs, f"cmp_del_{cand}")
    rows = [dict(dv=dv, td=td) for dv, td in zip(dvs, tds)]
    for r in rows:
        s = "--" if r["td"] is None else f"{r['td']*1e9:.3f} ns"
        print(f"  dv {r['dv']*1e3:+8.3f} mV -> "
              f"{'outn' if r['dv']>0 else 'outp'} falls {s}", flush=True)
    ups = [r["td"] for r in rows if r["dv"] > 0 and r["td"]]
    dns = [r["td"] for r in rows if r["dv"] < 0 and r["td"]]
    if ups and dns:
        # NOT an intrinsic latch asymmetry. Only ONE input moves -- `vin` is
        # the fixed reference, exactly as in the SAR -- so +100 mV and -100 mV
        # are also two different COMMON modes (0.95 V vs 0.85 V), and the tail
        # delivers more current at the higher one. The asymmetry is real and it
        # is the one the converter will see, but its cause is the single-ended
        # drive, not the two output devices.
        print(f"  direction asymmetry at |dv| = 100 mV: {ups[0]*1e9:.3f} ns "
              f"(Vcm 0.95) vs {dns[-1]*1e9:.3f} ns (Vcm 0.85) = "
              f"{max(ups[0], dns[-1])/min(ups[0], dns[-1]):.2f}x", flush=True)
    return rows


# --------------------------------------------------------------- meta ----
META_DV = [1e-1, 3e-2, 1e-2, 3e-3, 1e-3, 3e-4, 1e-4, 3e-5, 1e-5, 3e-6, 1e-6]


def run_meta(cand):
    """Delay vs overdrive -> regeneration time constant.

    A latch resolves exponentially: t_d = t_0 + tau*ln(V_x/dV). Fitting tau is
    what turns 'metastability' from a word into the SAR's error probability,
    because the trial has a fixed time budget and P(unresolved) = exp(-t/tau)
    per decade of input range.
    """
    tds = scan_delay(cand, META_DV, f"cmp_meta_{cand}")
    rows = [dict(dv=dv, td=td) for dv, td in zip(META_DV, tds)]
    for r in rows:
        s = "--" if r["td"] is None else f"{r['td']*1e9:7.3f} ns"
        print(f"  overdrive {r['dv']*1e3:9.4f} mV -> {s}", flush=True)
    def fit(lo):
        pts = [(math.log(r["dv"]), r["td"]) for r in rows
               if r["td"] and r["dv"] >= lo]
        if len(pts) < 3:
            return None
        n = len(pts)
        sx = sum(p[0] for p in pts)
        sy = sum(p[1] for p in pts)
        sxx = sum(p[0] * p[0] for p in pts)
        sxy = sum(p[0] * p[1] for p in pts)
        slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        return -slope, n                  # t_d = const - tau*ln(dv)

    # FIT THE CLEAN DECADES, AND SAY SO. Below ~0.1 mV of overdrive the
    # measured delay stops following the logarithm and flattens: at a microvolt
    # of differential on a 1.8 V circuit it is the solver's tolerance, not the
    # latch, that decides when the tie breaks. Fitting all eleven points anyway
    # would quote a tau half its real value and blame the circuit for it.
    clean = fit(1e-4)
    allp = fit(0)
    tau = clean[0] if clean else None
    if clean:
        print(f"  regeneration tau = {tau*1e12:.1f} ps over the 3 clean "
              f"decades (100 -> 0.1 mV, {clean[1]} points)", flush=True)
    if allp:
        print(f"  (all 11 points incl. the tolerance-limited tail would give "
              f"{allp[0]*1e12:.1f} ps -- not quoted)", flush=True)
    slowest = max((r["td"] for r in rows if r["td"]), default=None)
    if slowest:
        print(f"  slowest decision measured: {slowest*1e9:.3f} ns at 1 uV "
              f"overdrive, against a {2.0:.0f} us trial -- "
              f"{2e-6/slowest:.0f}x margin", flush=True)
    return dict(rows=rows, tau=tau, tau_allpoints=allp[0] if allp else None,
                slowest=slowest)


# --------------------------------------------------------------- kick ----
def run_kick(cand, ctop=1e-12):
    """Kickback into a floating 1 pF top plate -- the SAR's charge-holding node.

    The source is a 1 Gohm path so the DC operating point still solves while the
    node is effectively floating on the 100 ns timescale of a decision (tau =
    1 ms). Modelling the input as an ideal voltage source would report ZERO
    kickback for any comparator, which is exactly the modelling error the repo's
    coupling-cap lesson warns about (design-notes 2).
    """
    c = CAND[cand]
    dv = 0.005
    tag = f"cmp_kick_{cand}"
    pins = "vip vin outp outn clk"
    bias = ""
    if c["bias"]:
        bias = f"ib 0 vb dc {IB}"
        pins += " vb"
    net = f"""* {cand} kickback into {ctop*1e12:g} pF
{supplies(cand)}
vipsrc vipx 0 dc {vcm()+dv}
rk vipx vip 1e9
ck vip 0 {ctop:g}
{bias}
xdut {pins} vdd vss {c['sub']} {c['params']}
clp outp 0 {CLOAD}
cln outn 0 {CLOAD}
.tran 5p {T_END:g}
.control
run
meas tran vpre find v(vip) at={T_E2-1e-9:g}
meas tran vmin min v(vip) from={T_E2:g} to={T_END:g}
meas tran vmax max v(vip) from={T_E2:g} to={T_END:g}
meas tran vend find v(vip) at={T_END:g}
.endc
.end
"""
    out = run_ngspice(net, tag)
    v = meas(out)
    pre = v.get("vpre", float("nan"))
    peak = max(abs(v.get("vmax", pre) - pre), abs(v.get("vmin", pre) - pre))
    resid = v.get("vend", float("nan")) - pre
    return dict(v_pre=pre, peak_v=peak, resid_v=resid,
                peak_q=peak * ctop, resid_q=resid * ctop)


# ------------------------------------------------------------------ cm ----
def run_cm(cand, lo=0.10, hi=1.70, step=0.10):
    """Threshold and delay vs INPUT COMMON MODE -- spec row 11.

    This is the row that couples phase 3 to phase 4. A charge-redistribution
    SAR's top plate does not sit at mid-rail: with classic bottom-plate
    sampling it swings the full rail on the first trial, and with a
    Vcm-based scheme roughly a quarter of it. Rather than assume a scheme and
    measure one common mode, sweep the whole rail and let phase 4 choose on
    the data -- the same move the audio buffer's ICMR sweep made when it
    turned a THD number into a named wall (design-notes 13).

    A common mode the comparator cannot work at shows up here as NO FLIP:
    the decision stops depending on the input at all.
    """
    rows = []
    n = int(round((hi - lo) / step)) + 1
    for i in range(n):
        v = round(lo + i * step, 3)
        CM["v"] = v
        sfx = f"_cm{int(v*1000)}"
        thr = threshold(cand, +0.05, tagx=sfx)
        td = delay(cand, 0.005, f"cmp_cmd_{cand}{sfx}")
        rows.append(dict(vcm=v, thr=thr, td=td))
        print(f"  Vcm {v:.2f} V  thr "
              f"{'NO FLIP' if thr is None else f'{thr*1e3:+8.3f} mV'}  "
              f"td@5mV {'--' if td is None else f'{td*1e9:7.3f} ns'}",
              flush=True)
    CM["v"] = 0.9
    ok = [r for r in rows if r["thr"] is not None]
    if ok:
        print(f"  functional common mode: {min(r['vcm'] for r in ok):.2f} .. "
              f"{max(r['vcm'] for r in ok):.2f} V", flush=True)
    return rows


# ---------------------------------------------------------------- rail ----
def run_rail(cand, vref_node=0.9):
    """Decision correctness with the REFERENCE PINNED and the other input swept
    over the whole rail -- the shape the SAR actually presents.

    This is not the same measurement as `cm`, and confusing the two would be a
    mistake: in a charge-redistribution SAR only ONE comparator input moves.
    `vin` is the fixed mid-rail reference; `vip` is the DAC top plate, which
    after the hold sits at VREF - VIN and therefore visits the entire rail on
    the MSB trial. So the question for that trial is not "what is the offset at
    this common mode" but "is the SIGN still right when the input pair is
    nowhere near its comfortable bias".

    Note the useful accident this measures: the extreme top-plate voltages
    coincide with the LARGEST differential (top plate 0.1 V means the input is
    0.8 V away from the reference), so the MSB trial asks for a lot of common
    mode and almost no resolution. Whether that trade actually holds is exactly
    what the sweep reports.
    """
    CM["v"] = vref_node                 # vin sits at the reference
    vips = [round(0.05 + 0.05 * i, 3) for i in range(34)]
    dvs = [v - vref_node for v in vips]
    res = scan(cand, dvs, dvs, f"cmp_rail_{cand}")
    rows = []
    for vip, r in zip(vips, res):
        dv = vip - vref_node
        ok = (r["outp_high"] == (dv > 0)) if abs(dv) > 1e-9 else None
        rows.append(dict(vip=vip, dv=dv, outp_high=r["outp_high"], ok=ok,
                         vop=r["vop"], von=r["von"]))
        print(f"  top plate {vip:.2f} V (dv {dv*1e3:+7.1f} mV) -> "
              f"outp {r['vop']:.3f} outn {r['von']:.3f}  "
              f"{'ok' if ok else 'WRONG' if ok is False else '--'}", flush=True)
    CM["v"] = 0.9
    bad = [r for r in rows if r["ok"] is False]
    good = [r for r in rows if r["ok"]]
    if good:
        print(f"  correct over {min(r['vip'] for r in good):.2f} .. "
              f"{max(r['vip'] for r in good):.2f} V of top plate; "
              f"{len(bad)} wrong decision(s)", flush=True)
    return rows


# ----------------------------------------------------------- kicksweep ----
def run_kicksweep(cand, ctop=1e-12):
    """Kickback vs OVERDRIVE -- the measurement phase 4 sent back.

    `run_kick` measures one point, near balance, because that is where a
    comparator's kickback is conventionally quoted. Phase 4 then found the
    converter losing ~65 fC on conversions near full scale, time-independent
    across an 8x change in conversion period (so capacitive, not leakage) and
    absent over the lower 86 % of the range. The common factor in the failing
    conversions is that their EARLY trials happen far from the reference, with
    the input pair fully steered -- a completely different operating point from
    the one the single-point measurement samples.

    So: sweep it. A comparator that is quiet at threshold and noisy at full
    steer is still a comparator that corrupts a charge-holding node, and a SAR
    spends most of its trials far from balance by construction.
    """
    c = CAND[cand]
    rows = []
    for dv in (-0.8, -0.6, -0.4, -0.2, -0.05, -0.005, 0.005, 0.05, 0.2, 0.4,
               0.6, 0.8):
        tag = f"cmp_kicksw_{cand}_{int(dv*1000)}"
        pins = "vip vin outp outn clk"
        bias = ""
        if c["bias"]:
            bias = f"ib 0 vb dc {IB}"
            pins += " vb"
        net = f"""* {cand} kickback at dv={dv:+.4g}
{supplies(cand)}
vipsrc vipx 0 dc {vcm()+dv}
rk vipx vip 1e9
ck vip 0 {ctop:g}
{bias}
xdut {pins} vdd vss {c['sub']} {c['params']}
clp outp 0 {CLOAD}
cln outn 0 {CLOAD}
.tran 5p {T_END:g}
.control
run
meas tran vpre find v(vip) at={T_E2-1e-9:g}
meas tran vend find v(vip) at={T_END:g}
.endc
.end
"""
        v = meas(run_ngspice(net, tag))
        pre, end = v.get("vpre"), v.get("vend")
        q = None if pre is None or end is None else (end - pre) * ctop
        rows.append(dict(dv=dv, resid_q=q))
        print(f"  overdrive {dv*1e3:+7.1f} mV -> residual "
              f"{'--' if q is None else f'{q*1e15:+8.3f} fC'}", flush=True)
    got = [r for r in rows if r["resid_q"] is not None]
    if got:
        worst = max(got, key=lambda r: abs(r["resid_q"]))
        near = min(got, key=lambda r: abs(r["dv"]))
        print(f"  worst {worst['resid_q']*1e15:+.3f} fC at {worst['dv']*1e3:+.0f} mV; "
              f"near balance {near['resid_q']*1e15:+.3f} fC -- ratio "
              f"{abs(worst['resid_q']/near['resid_q']) if near['resid_q'] else float('inf'):.0f}x",
              flush=True)
    return rows


# ----------------------------------------------------------------- mc ----
def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _probit(p):
    """Inverse normal CDF by bisection -- no scipy in this repo's toolchain."""
    lo, hi = -8.0, 8.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def run_mc(cand, npts=21, span=0.016, ncopy=24, prime_dv=+0.05, tagx=""):
    """Offset distribution by measuring the DECISION PROBABILITY, not by
    finding one device's threshold N times.

    THE METHOD, and why it is not the obvious one. Every instance in a netlist
    draws its OWN mismatch from AGAUSS, so K copies in one run are K different
    devices -- but a threshold search needs the SAME device across its scans,
    which a fresh draw per run destroys. Turn it around: hold the overdrive
    fixed within a run, count how many of the K copies decide positive, and
    sweep the overdrive across runs. That measures P(decide + | dv), whose
    fitted mean and width ARE the offset distribution's mu and sigma.

    It is also better statistics for less time: 21 runs x 24 copies = 504
    device samples, where 21 runs of bisection would have given seven.

    `span` must bracket the transition but not much more -- points that read
    0/N or N/N carry no information and are dropped, so a span of +-40 mV on a
    6 mV sigma left only five usable points out of twenty-one.
    """
    dvs = [-span + 2 * span * i / (npts - 1) for i in range(npts)]
    rows = []
    for i, dv in enumerate(dvs):
        ENV.update(corner="tt_mm", temp=25, vdd=VDD, seed=3000 + i)
        res = scan(cand, [dv] * ncopy, prime_dv, f"cmp_mc_{cand}{tagx}_{i}")
        k = sum(1 for r in res if r["outp_high"])
        rows.append(dict(dv=dv, k=k, n=len(res)))
        print(f"  dv {dv*1e3:+7.2f} mV -> {k:2d}/{len(res)} decide +",
              flush=True)
    ENV.update(corner="tt", temp=25, vdd=VDD, seed=None)
    # probit fit: Phi^-1(p) = (dv - mu)/sigma, so a straight line whose slope
    # is 1/sigma. Saturated points carry no information and are dropped.
    pts = [(r["dv"], _probit(r["k"] / r["n"])) for r in rows
           if 0 < r["k"] < r["n"]]
    fit = None
    if len(pts) >= 3:
        n = len(pts)
        sx = sum(p[0] for p in pts)
        sy = sum(p[1] for p in pts)
        sxx = sum(p[0] ** 2 for p in pts)
        sxy = sum(p[0] * p[1] for p in pts)
        slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        icpt = (sy - slope * sx) / n
        sigma = 1.0 / slope
        mu = -icpt * sigma
        fit = dict(mu=mu, sigma=sigma, npts=n,
                   nsamples=sum(r["n"] for r in rows))
        print(f"offset distribution: mu {mu*1e3:+.3f} mV, sigma "
              f"{sigma*1e3:.3f} mV, 3-sigma +-{3*sigma*1e3:.2f} mV "
              f"({fit['nsamples']} device samples over {n} usable points)",
              flush=True)
    else:
        print("  probit fit needs unsaturated points -- widen `span`",
              flush=True)
    return dict(rows=rows, fit=fit)


def run_hyst(cand):
    """Hysteresis where it is actually measurable: under mismatch.

    At `tt` the netlist is perfectly symmetric, so both priming directions give
    the same threshold and the measured hysteresis is zero -- true, but it is
    the symmetry of the schematic talking, not the reset clearing the latch.
    Re-running the probability sweep for each priming direction and comparing
    the fitted means separates the two.
    """
    out = {}
    for name, prime in (("after +", +0.05), ("after -", -0.05)):
        print(f"  priming {name}:", flush=True)
        out[name] = run_mc(cand, prime_dv=prime,
                           tagx="_hp" if prime > 0 else "_hn")
    a, b = out["after +"]["fit"], out["after -"]["fit"]
    if a and b:
        print(f"hysteresis (difference of fitted means) = "
              f"{abs(a['mu']-b['mu'])*1e6:.1f} uV; budget 3520 uV", flush=True)
    return out


# ---------------------------------------------------------------- pvt ----
PROCESS = ["tt", "ss", "ff", "sf", "fs"]
TEMPS = [-40, 25, 85]
SUPPLIES = [1.62, 1.98]


def run_pvt(cand):
    pts = [(p, t, VDD) for p in PROCESS for t in TEMPS]
    pts += [("tt", 25, v) for v in SUPPLIES]
    rows = []
    for (p, t, v) in pts:
        ENV.update(corner=p, temp=t, vdd=v, seed=None)
        sfx = f"_{p}_{t}_{v}".replace(".", "p")
        thr = threshold(cand, +0.05, tagx=sfx)
        td = delay(cand, 0.001, f"cmp_pvtd_{cand}{sfx}")
        rows.append(dict(process=p, temp=t, vdd=v, thr=thr, td=td))
        print(f"  {p:2s} {t:+4d}C {v:.2f}V  thr "
              f"{'--' if thr is None else f'{thr*1e3:+7.3f} mV'}  "
              f"td@1mV {'--' if td is None else f'{td*1e9:6.3f} ns'}",
              flush=True)
    ENV.update(corner="tt", temp=25, vdd=VDD, seed=None)
    return rows


# ---------------------------------------------------------------- thr ----
def run_thr(cand):
    """Threshold after a + decision and after a - decision. The gap IS the
    hysteresis; the midpoint is the systematic offset at this corner."""
    tp = threshold(cand, +0.05, tagx="_hp")
    tn = threshold(cand, -0.05, tagx="_hn")
    if tp is None or tn is None:
        print(f"  NO FLIP: prime+ {tp} prime- {tn}", flush=True)
        return dict(thr_after_pos=tp, thr_after_neg=tn, hyst=None, offset=None)
    print(f"  threshold after a + decision: {tp*1e6:+9.1f} uV", flush=True)
    print(f"  threshold after a - decision: {tn*1e6:+9.1f} uV", flush=True)
    print(f"  hysteresis = {abs(tp-tn)*1e6:.1f} uV, systematic offset = "
          f"{(tp+tn)/2*1e6:+.1f} uV", flush=True)
    return dict(thr_after_pos=tp, thr_after_neg=tn, hyst=abs(tp - tn),
                offset=(tp + tn) / 2)


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    cand = sys.argv[2] if len(sys.argv) > 2 else "strongarm"
    print(f"=== {cand} ({CAND[cand]['params']}) ===", flush=True)
    res = {}
    if what in ("op", "all"):
        o = run_op(cand)
        res["op"] = o
        print(f"op: static {o['istatic']*1e6:.3f} uA, charge/decision "
              f"{o['q_cycle']*1e15:.1f} fC (evaluate half {o['q_evaluate']*1e15:.1f} fC)",
              flush=True)
    if what in ("thr", "all"):
        res["thr"] = run_thr(cand)
    if what in ("delay", "all"):
        res["delay"] = run_delay(cand)
    if what in ("kick", "all"):
        k = run_kick(cand)
        res["kick"] = k
        print(f"kickback: peak {k['peak_v']*1e3:.3f} mV = {k['peak_q']*1e15:.2f} fC, "
              f"residual {k['resid_v']*1e3:+.3f} mV = {k['resid_q']*1e15:+.2f} fC "
              f"(budget 3.5 fC)", flush=True)
    if what in ("meta", "all"):
        res["meta"] = run_meta(cand)
    if what == "mc":
        res["mc"] = run_mc(cand)
    if what == "kicksweep":
        res["kicksweep"] = run_kicksweep(cand)
    if what == "hyst":
        res["hyst"] = run_hyst(cand)
    if what == "cm":
        res["cm"] = run_cm(cand)
    if what == "rail":
        res["rail"] = run_rail(cand)
    if what == "pvt":
        res["pvt"] = run_pvt(cand)
    if res:
        p = OUT / f"comparator_{cand}_{what}.json"
        p.write_text(json.dumps(res, indent=1))
        print(f"-> {p}", flush=True)


if __name__ == "__main__":
    main()
