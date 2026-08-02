"""SAR ADC bench -- phase 4. The whole converter, one conversion per transient.

`spice/cdac8.sp` is the 8-bit charge-redistribution array; the comparator is
whichever phase-3 candidate won (`spice/strongarm.sp` / `spice/comparator.sp`);
and the SAR sequencing here is built from ngspice's XSPICE digital primitives.

WHY THE LOGIC IS XSPICE AND NOT OUR OWN CELLS. PLAN.md phase 4 wants the SAR
logic in the `stdcells` library eventually. Modelling it as ideal digital here
is not a shortcut around that -- it is what makes the measurement mean
something: INL, DNL and ENOB then depend on the capacitor array and the
comparator ALONE, so a linearity number cannot be quietly rescued (or spoiled)
by the logic implementation. Mapping the same sequencing onto real cells is a
separate, checkable step, and the timing it has to meet is printed here.

THE SEQUENCE (one master clock, everything else derived):
  period 0        idle -- reset releases
  periods 1-2     SAMPLE. Top plate to vcm, every bottom plate to vin.
                  The top switch opens 0.2T EARLY: bottom-plate sampling, so
                  the top switch's charge injection happens at a fixed
                  potential and lands as an offset instead of as distortion.
  periods 3-10    eight bit trials, MSB first. Within a trial:
                    t+0.0T  the pointer sets this bit -> its cap to VREF
                    t+0.5T  comparator clock rises, decision regenerates
                    t+0.75T decision captured into this bit's register
                    t+0.9T  comparator clock falls, latch resets
  period 11       done; the code is read.

  A trial's bit control is (pointer_i OR q_i): forced high while the trial is
  live, then held at whatever was captured. That is the whole SAR -- no state
  machine, and no way for a bit to be set by anything but its own decision.

    python tb/sar.py conv   0.9        # one conversion, verbose
    python tb/sar.py xfer   64         # transfer curve -> INL/DNL
    python tb/sar.py dac               # the array's 256 static levels
    python tb/sar.py fft    64         # SNDR / ENOB, coherently sampled
    python tb/sar.py mc     20         # linearity over capacitor mismatch
"""
import json
import math
import re
import statistics
import sys

from common import (VDD, OUT, ENV, header, run_ngspice, SPICE, read_wrdata)

MEAS_RE = re.compile(r"^(\w+)\s*=\s*([-+0-9.eE]+)", re.M)

# NOTE (cost a debug loop): the PDK ships TWO different MIM cap models and the
# repo loads libs.tech/COMBINED (inherited from stdcells/flow/common.py), not
# libs.tech/ngspice. They disagree about the parameter name (`mult` vs `mf`),
# about the matching coefficient by 6x (0.47 vs 2.8 %.um), and about whether
# there is a perimeter term. Including the libs.ref file "to be safe" is worse
# than useless: ngspice keeps the FIRST definition and prints only
# "redefinition ... ignored", so the netlist silently runs against whichever
# model the corner lib already supplied. Let the corner lib provide it.

NBITS = 8
T = 100e-9          # master period. 10x the spec's 500 kHz decision rate --
                    # a stress condition, not the operating point. `conv slow`
                    # re-runs at the real rate to check nothing is leaking.
VREF = 1.8
VCM = 0.9           # comparator reference AND the top plate's rest potential
CMP = "strongarm"   # comparator candidate; overridden from the command line

# "ideal" is a CONTROL, not a candidate: a B-source sign test with no input
# capacitance, no kickback and no offset. Running the converter with it says
# whether an error belongs to the array and the switches or to the comparator
# hanging off the top plate -- a question no amount of staring at a transfer
# curve answers.
SUBCKT = {"ideal": (None, [], "", False),
          "strongarm": ("strongarm", [], "mi=4 li=1", False),
          "comparator": ("comparator", ["strongarm"], "mp=8 lp=1 mi=4 li=1",
                         True)}


def meas(stdout):
    vals = {}
    for m in MEAS_RE.finditer(stdout):
        try:
            vals[m.group(1).lower()] = float(m.group(2))
        except ValueError:
            pass
    return vals


def sources():
    """Every deterministic waveform. The sample window and the two derived
    clocks depend only on time, never on data, so they are plain PWL/PULSE
    sources rather than gates -- fewer parts and no race to reason about."""
    t_smp_open = 3 * T - 0.2 * T        # top switch opens EARLY (see header)
    # ...and the bottom plates leave `vin` LATE -- after the pointer has already
    # set the MSB. This is not a settling margin, it is a correctness fix, and
    # it was worth 21 LSB.
    #
    # The pointer flop (clk_delay 0.1 ns) and the dac_bridge (t_rise 0.1 ns) put
    # the MSB control ~0.2 ns behind the clock edge. Releasing the bottoms on
    # that same edge therefore left the array at CODE 0 for 200 ps, and at code
    # 0 the top plate sits at vcm - vin: for any input above mid-rail that is
    # NEGATIVE (-0.84 V at full scale), which forward-biases the sampling
    # switch's junction to the substrate and dumps sampled charge on the floor.
    # The charge does not come back, so the result was a permanent, one-sided,
    # time-independent code error that grew toward full scale -- exactly the
    # -21 LSB the ideal-comparator control still showed after the comparator had
    # been ruled out.
    t_bot = 3 * T + 0.05 * T
    return f"""* --- reset, and the one-period start pulse that seeds the pointer ---
vrst rst 0 dc 0 pwl(0 {VDD} {0.5*T:g} {VDD} {0.5*T+1e-10:g} 0 {12*T:g} 0)
vstart start 0 dc 0 pwl(0 {VDD} {1.5*T:g} {VDD} {1.5*T+1e-10:g} 0 {12*T:g} 0)
* --- master clock: pointer advances on the rising edge ---
vclk clk 0 dc 0 pulse(0 {VDD} {T:g} 0.1n 0.1n {0.45*T:g} {T:g})
* --- comparator clock: high through the middle of every trial ---
vcclk cclk 0 dc 0 pulse(0 {VDD} {3.5*T:g} 0.1n 0.1n {0.4*T:g} {T:g})
* --- capture strobe: rises while the decision is settled and cclk still high -
vcap cap 0 dc 0 pulse(0 {VDD} {3.75*T:g} 0.1n 0.1n {0.1*T:g} {T:g})
* --- sampling: top plate switch opens 0.2T before the bottom plates move ---
vsmp  smp  0 dc 0 pwl(0 {VDD} {t_smp_open:g} {VDD} {t_smp_open+1e-10:g} 0 {12*T:g} 0)
vsmpn smpn 0 dc 0 pwl(0 0 {t_smp_open:g} 0 {t_smp_open+1e-10:g} {VDD} {12*T:g} {VDD})
vsmpb smpb 0 dc 0 pwl(0 {VDD} {t_bot:g} {VDD} {t_bot+1e-10:g} 0 {12*T:g} 0)
"""


def digital_shared():
    """Pointer chain + the logic-level plumbing every copy shares."""
    lines = ["abr_ctl [clk rst start cap] [dclk drst dstart dcap] adc_bridge",
             "apd dlo d_pulldown"]
    # 11 pointer stages: s0,s1 = sample; s2..s9 = the eight trials; s10 = done
    for i in range(11):
        d = "dstart" if i == 0 else f"ds{i-1}"
        lines.append(f"as{i} {d} dclk dlo drst ds{i} ds{i}n d_dff")
    return "\n".join(lines)


def copy(k, vin_expr, cmp_name=None):
    """One complete converter: array + comparator + eight bit registers.

    Every copy carries its OWN registers because those are the data-dependent
    part; the pointer and the clocks are shared because they are not. That
    split is what lets K conversions at K different inputs run in ONE ngspice
    invocation -- the same trick tb/comparator.py uses, and the reason a
    1024-point transfer curve is affordable at all.
    """
    cmp_name = cmp_name or CMP
    sub, _needs, params, bias = SUBCKT[cmp_name]
    L = [f"vsig{k} ain{k} 0 dc {vin_expr}"]
    ctl = " ".join(f"c{k}_{b}" for b in range(7, -1, -1))
    L.append(f"xdac{k} top{k} ain{k} vcm {ctl} smp smpn smpb vdd vss cdac8")
    pins = f"top{k} vcm cp{k} cn{k} cclk"
    if bias:
        L.append(f"ib{k} 0 vb{k} dc 20u")
        pins += f" vb{k}"
    if sub is None:
        L.append(f"bcmp{k} cn{k} 0 v = (v(vcm) > v(top{k})) ? {VDD} : 0")
    else:
        L.append(f"xcmp{k} {pins} vdd vss {sub} {params}")
        L.append(f"clp{k} cp{k} 0 10f")
        L.append(f"cln{k} cn{k} 0 10f")
    # cn HIGH means the top plate is BELOW the reference, i.e. the trial code
    # is still under the input -> keep this bit. Bridging cn rather than cp is
    # the whole polarity of the search; getting it backwards would converge to
    # the complement of the answer, which is why `conv` prints the residue.
    L.append(f"abrc{k} [cn{k}] [dkeep{k}] adc_bridge")
    for b in range(8):
        s = f"ds{2 + (7 - b)}"          # pointer stage that owns bit b
        L.append(f"aand{k}_{b} [dcap {s}] dgc{k}_{b} d_and")
        L.append(f"aff{k}_{b} dkeep{k} dgc{k}_{b} dlo drst dq{k}_{b} "
                 f"dq{k}_{b}n d_dff")
        L.append(f"aor{k}_{b} [{s} dq{k}_{b}] dc{k}_{b} d_or")
    outs = " ".join(f"dc{k}_{b}" for b in range(8))
    anas = " ".join(f"c{k}_{b}" for b in range(8))
    L.append(f"abro{k} [{outs}] [{anas}] dac_bridge")
    qouts = " ".join(f"dq{k}_{b}" for b in range(8))
    qanas = " ".join(f"q{k}_{b}" for b in range(8))
    L.append(f"abrq{k} [{qouts}] [{qanas}] dac_bridge")
    return "\n".join(L)


MODELS = """.model adc_bridge adc_bridge(in_low=0.6 in_high=1.2 rise_delay=1p fall_delay=1p)
.model dac_bridge dac_bridge(out_low=0 out_high=1.8 t_rise=0.1n t_fall=0.1n)
.model d_dff d_dff(clk_delay=0.1n set_delay=0.1n reset_delay=0.1n ic=0)
.model d_and d_and(rise_delay=0.05n fall_delay=0.05n)
.model d_or d_or(rise_delay=0.05n fall_delay=0.05n)
.model d_pulldown d_pulldown(load=0)
"""


def netlist(vins, cmp_name=None, extra_meas="", dac_params="", tstop=None):
    cmp_name = cmp_name or CMP
    sub, needs, _p, _b = SUBCKT[cmp_name]
    # dependencies first, then the candidate itself -- unless it is the "ideal"
    # control, which is a B-source and has no subckt file at all
    inc = "\n".join((SPICE / f"{n}.sp").read_text() for n in needs)
    if sub is not None:
        inc += "\n" + (SPICE / f"{sub}.sp").read_text()
    body = "\n".join(copy(k, f"{v:.9g}", cmp_name) for k, v in enumerate(vins))
    ms = []
    for k in range(len(vins)):
        for b in range(8):
            ms.append(f"meas tran q{k}_{b} find v(q{k}_{b}) "
                      f"at={11.5*T:g}")
    tstop = tstop or 12 * T
    return f"""* {len(vins)}-way SAR conversion, comparator={cmp_name}
{header()}
{inc}
{(SPICE / "cdac8.sp").read_text()}
vsup vdd 0 dc {VDD}
vgnd vss 0 0
vvcm vcm 0 dc {VCM}
{sources()}
{digital_shared()}
{body}
{MODELS}
.tran 20p {tstop:g}
.control
run
{chr(10).join(ms)}
{extra_meas}
.endc
.end
"""


def codes_from(vals, n):
    """Assemble each copy's eight register outputs into a code."""
    out = []
    for k in range(n):
        code, ok = 0, True
        for b in range(8):
            v = vals.get(f"q{k}_{b}")
            if v is None or 0.4 < v < 1.4:      # bridge mid-level = unknown
                ok = False
                break
            if v > VDD / 2:
                code |= 1 << b
        out.append(code if ok else None)
    return out


def convert(vins, tag, cmp_name=None, **kw):
    out = run_ngspice(netlist(vins, cmp_name, **kw), tag)
    return codes_from(meas(out), len(vins))


# ---------------------------------------------------------------- conv ----
def run_conv(vin, cmp_name=None):
    """One conversion, with the top plate written out so the binary search is
    visible rather than inferred."""
    tag = f"sar_conv_{int(vin*1000)}"
    extra = f"wrdata {tag}_top.txt v(top0)"
    codes = convert([vin], tag, cmp_name, extra_meas=extra)
    code = codes[0]
    ideal = int(round(vin / VREF * 256))
    print(f"  Vin {vin:.4f} V -> code {code} (ideal {ideal}, "
          f"err {'--' if code is None else code-ideal} LSB)", flush=True)
    rows = read_wrdata(OUT / f"{tag}_top.txt", 2)
    if rows:
        # the residue should collapse toward vcm; print the trial endpoints
        for i in range(3, 11):
            t = (i + 0.45) * T
            near = min(rows, key=lambda r: abs(r[0] - t))
            print(f"    trial {i-3} (bit {10-i}): top = {near[1]:+.4f} V "
                  f"({(near[1]-VCM)*1e3:+8.2f} mV from vcm)", flush=True)
    return dict(vin=vin, code=code, ideal=ideal)


# ----------------------------------------------------------------- dac ----
# Dwell per code, and a MAX TIMESTEP -- both set by a convergence study, not
# by an RC estimate. ngspice's default maximum step is tstop/50 (~100 ns here),
# and `meas ... find` INTERPOLATES between solver points, so a short dwell had
# the measurement reading the code transition rather than the settled level.
# The tell was unambiguous: on the lightly-loaded top plate the midscale DNL
# moved 0.1195 -> 0.0705 LSB AND CHANGED SIGN when only the timestep changed.
# A number that flips sign with a solver setting is the solver's, not the
# circuit's. At these settings the loaded INL is stable to ~1 % across a 10x
# range of dwell (-0.4454 at 100 ns, -0.4526 at 200 ns), so it is real.
DAC_DT = 100e-9
DAC_TMAX = " 0 1n"


def dac_netlist(cmp_name=None, params="", codes=None, load="cmp", clin=41e-15):
    """All 256 DAC levels in ONE transient, with the SAR logic taken out.

    The code is walked by driving b7..b0 from PWL sources, which is legitimate
    here precisely BECAUSE the sequence is not data-dependent: this measures
    the array, not the search. Isolating it matters -- INL from capacitor
    mismatch and INL from a comparator that decided wrongly look identical in
    a transfer curve, and only one of them is fixed by making capacitors
    bigger.

    The comparator is still INSTANTIATED, with its clock held low. Leaving it
    out would be the tidier netlist and the wrong measurement: its input
    capacitance hangs on the top plate and is VOLTAGE-DEPENDENT (gate and
    junction caps), so it contributes real curvature. A linear load only
    costs gain; a nonlinear one costs linearity.

    Sampling vin = VCM is not arbitrary either. top = vcm - vin + Vref*k, so
    sampling mid-rail puts the 256 levels on 0 .. 1.79 V -- the whole rail and
    no further. Sampling 0 V instead would ask the top plate to reach 2.69 V,
    where the switch's junctions clamp and the "DAC nonlinearity" measured
    would be a diode.
    """
    cmp_name = cmp_name or CMP
    sub, needs, cparams, bias = SUBCKT[cmp_name]
    inc = "\n".join((SPICE / f"{n}.sp").read_text() for n in needs)
    codes = codes if codes is not None else list(range(256))
    t0 = 3 * T
    # one PWL per bit, stepping at each code boundary
    src = []
    for b in range(8):
        pts = [f"0 {VDD if (codes[0] >> b) & 1 else 0:g}"]
        prev = (codes[0] >> b) & 1
        for i, c in enumerate(codes):
            cur = (c >> b) & 1
            if cur != prev:
                t = t0 + i * DAC_DT
                pts.append(f"{t:g} {VDD if prev else 0:g}")
                pts.append(f"{t + 1e-10:g} {VDD if cur else 0:g}")
                prev = cur
        pts.append(f"{t0 + len(codes) * DAC_DT:g} {VDD if prev else 0:g}")
        src.append(f"vb{b} cb_{b} 0 dc 0 pwl({' '.join(pts)})")
    ms = [f"meas tran v{i} find v(top) at={t0 + (i + 0.95) * DAC_DT:g}"
          for i in range(len(codes))]
    ctl = " ".join(f"cb_{b}" for b in range(7, -1, -1))
    cmp_pins = "top vcm cp cn vss" + (" vb" if bias else "")
    cmp_bias = "ib 0 vb dc 20u" if bias else ""
    if load == "lin":
        # a LINEAR capacitor of the same value as the comparator's input load.
        # Same attenuation, none of the voltage dependence -- the control that
        # says whether the INL bow is the parasitic's nonlinearity or something
        # else entirely.
        cmp_bias, cmp_pins = "", ""
        dut = f"cload top 0 {clin:g}"
    elif load == "none":
        cmp_bias, cmp_pins, dut = "", "", "* top plate unloaded"
    else:
        dut = f"xcmp {cmp_pins} vdd vss {sub} {cparams}\nclp cp 0 10f\ncln cn 0 10f"
    tend = t0 + len(codes) * DAC_DT + DAC_DT
    return f"""* cdac8 static transfer, {len(codes)} codes, comparator={cmp_name} (clock low)
{header()}
{params}
{inc}
{(SPICE / f"{sub}.sp").read_text()}
{(SPICE / "cdac8.sp").read_text()}
vsup vdd 0 dc {VDD}
vgnd vss 0 0
vvcm vcm 0 dc {VCM}
vain ain 0 dc {VCM}
vsmp  smp  0 dc 0 pwl(0 {VDD} {t0-0.2*T:g} {VDD} {t0-0.2*T+1e-10:g} 0 {tend:g} 0)
vsmpn smpn 0 dc 0 pwl(0 0 {t0-0.2*T:g} 0 {t0-0.2*T+1e-10:g} {VDD} {tend:g} {VDD})
vsmpb smpb 0 dc 0 pwl(0 {VDD} {t0:g} {VDD} {t0+1e-10:g} 0 {tend:g} 0)
{chr(10).join(src)}
xdac top ain vcm {ctl} smp smpn smpb vdd vss cdac8
{cmp_bias}
{dut}
.tran 200p {tend:g}{DAC_TMAX}
.control
run
{chr(10).join(ms)}
.endc
.end
"""


def run_dac(cmp_name=None, params="", tag="sar_dac", quiet=False,
            load="cmp"):
    out = run_ngspice(dac_netlist(cmp_name, params, load=load), tag)
    v = meas(out)
    levels = [v.get(f"v{i}") for i in range(256)]
    if any(x is None for x in levels):
        print(f"  MISSING {sum(1 for x in levels if x is None)} levels",
              flush=True)
        return None
    lin = dac_linearity(levels)
    if not quiet:
        print(f"  LSB {lin['lsb']*1e3:.4f} mV (ideal {VREF/256*1e3:.4f} mV, "
              f"top-plate attenuation {(1-lin['lsb']/(VREF/256))*100:.2f} %)",
              flush=True)
        print(f"  DNL {lin['dnl_min']:+.4f} .. {lin['dnl_max']:+.4f} LSB"
              f"   INL {lin['inl_min']:+.4f} .. {lin['inl_max']:+.4f} LSB",
              flush=True)
        print(f"  worst DNL at code {lin['dnl_at']}, worst INL at code "
              f"{lin['inl_at']}  (midscale DNL {lin['dnl'][128]:+.4f})",
              flush=True)
    return dict(levels=levels, **lin)


def dac_linearity(levels):
    """Endpoint-fit INL/DNL, the textbook definition.

    Endpoint rather than best-fit on purpose: a best-fit line hides a bowed
    transfer inside a smaller number, and the question here is whether the
    ARRAY divides binary -- for which the two ends are the reference.
    """
    lsb = (levels[-1] - levels[0]) / (len(levels) - 1)
    dnl = [0.0] + [(levels[i] - levels[i - 1]) / lsb - 1.0
                   for i in range(1, len(levels))]
    inl = [(levels[i] - (levels[0] + lsb * i)) / lsb
           for i in range(len(levels))]
    return dict(lsb=lsb, dnl=dnl, inl=inl,
                dnl_max=max(dnl), dnl_min=min(dnl),
                inl_max=max(inl), inl_min=min(inl),
                dnl_at=max(range(len(dnl)), key=lambda i: abs(dnl[i])),
                inl_at=max(range(len(inl)), key=lambda i: abs(inl[i])))


# ---------------------------------------------------------------- xfer ----
def run_xfer(npts=256, per_run=16, cmp_name=None, quiet=False):
    """Transfer curve: code vs input, over the full scale.

    THIS -- not the static DAC sweep -- is the converter's linearity, and the
    difference is not pedantry. `dac` walks the code with the input fixed, so
    the top plate visits the whole rail and any voltage-dependent load on it
    shows up in full. A CONVERSION does the opposite: the binary search drives
    the top plate BACK to vcm whatever the input was, so every conversion ends
    at the same potential and the parasitic's charge at that potential is the
    same constant every time. A full-rail bow in the DAC sweep therefore does
    NOT have to appear as converter INL, and reporting the DAC number as the
    ADC's would overstate the error by an order of magnitude here.

    Inputs land at code centres ((i+0.5) LSB) on purpose: an input exactly on a
    transition makes the comparator decide on zero overdrive, and the resulting
    coin-flip would be recorded as converter error when it is nothing of the
    kind.
    """
    vins = [VREF * (i + 0.5) / npts for i in range(npts)]
    rows = []
    for i in range(0, len(vins), per_run):
        chunk = vins[i:i + per_run]
        codes = convert(chunk, f"sar_xfer_{i}", cmp_name)
        for j, (v, c) in enumerate(zip(chunk, codes)):
            ideal = int(v / VREF * 256)     # floor: inputs sit at code centres
            rows.append(dict(vin=v, code=c, ideal=ideal))
            if c is None:
                print(f"  {v:.4f} V -> CONVERSION FAILED (a register never "
                      f"resolved)", flush=True)
            elif not quiet and (c != ideal or (i + j) % 32 == 0):
                print(f"  {v:.4f} V -> {c} (ideal {ideal}"
                      f"{'' if c == ideal else f', err {c-ideal:+d}'})",
                      flush=True)
    return rows


def linearity(rows):
    """INL/DNL from a transfer curve, by fitting the endpoints.

    With fewer input points than codes this is a SAMPLED transfer curve, so it
    reports the error of the codes actually visited -- honest, and enough to
    catch a missing MSB. `dac` measures every code directly.
    """
    good = [r for r in rows if r["code"] is not None]
    if len(good) < 4:
        return None
    xs = [r["vin"] for r in good]
    ys = [r["code"] for r in good]
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    off = (sy - slope * sx) / n
    err = [y - (slope * x + off) for x, y in zip(xs, ys)]
    gain_err = slope / (256 / VREF) - 1
    return dict(inl_max=max(abs(e) for e in err), gain_err=gain_err,
                offset_code=off, errs=err,
                missing=[r["vin"] for r in rows if r["code"] is None])


# --------------------------------------------------------------- match ----
def run_match(nseeds=8):
    """Capacitor matching -> array linearity, against BOTH of the PDK's
    disagreeing MIM mismatch models.

    MEASURED WITH A LINEAR TOP-PLATE LOAD, on purpose. The comparator's real
    input capacitance puts a large bow on the static DAC sweep, but that bow
    does NOT carry into the converter (every conversion ends at the same top
    plate potential, so the parasitic's charge is the same constant each time
    -- see `run_xfer`). Capacitor mismatch is different: it corrupts the binary
    WEIGHTS, so it carries into the converter in full. Measuring mismatch with
    the nonlinear load still attached would bury the one contribution that
    transfers underneath the one that does not.
    """
    cases = [("no mismatch (tt)", "tt", ""),
             ("combined model, sw_mm_cmim = 4.7e-3 (0.47 %.um)", "tt_mm", ""),
             ("ngspice/libs.ref model, 2.8 %.um (pessimistic)", "tt_mm",
              ".param sw_mm_cmim=0.028")]
    out = {}
    for label, corner, params in cases:
        n = 1 if corner == "tt" else nseeds
        dnls, inls = [], []
        for s in range(n):
            ENV.update(corner=corner, seed=None if corner == "tt" else 5000 + s)
            r = run_dac(params=params, load="lin", quiet=True,
                        tag=f"sar_match_{len(out)}_{s}")
            if r is None:
                continue
            dnls.append(max(abs(r["dnl_min"]), abs(r["dnl_max"])))
            inls.append(max(abs(r["inl_min"]), abs(r["inl_max"])))
            print(f"    seed {s}: worst |DNL| {dnls[-1]:.4f}, "
                  f"worst |INL| {inls[-1]:.4f} LSB", flush=True)
        if dnls:
            out[label] = dict(dnl=dnls, inl=inls,
                              dnl_mean=statistics.mean(dnls),
                              inl_mean=statistics.mean(inls),
                              dnl_worst=max(dnls), inl_worst=max(inls))
            print(f"  {label}: worst |DNL| {max(dnls):.4f} LSB, worst |INL| "
                  f"{max(inls):.4f} LSB over {len(dnls)} draw(s)", flush=True)
    ENV.update(corner="tt", seed=None)
    return out


# ----------------------------------------------------------------- fft ----
def run_fft(n=64, cycles=7, ampl=0.85, per_run=16, cmp_name=None):
    """SNDR / ENOB from a coherently sampled sine.

    COHERENT SAMPLING, so no window is needed: `cycles` is chosen coprime with
    `n`, which puts the tone exactly in bin `cycles` and leaves every other bin
    as noise-plus-distortion. Windowing a coherent record would smear the tone
    into its neighbours and flatter the result.

    HONEST SCOPE: each sample here is a conversion of a DC level equal to the
    sine at that instant, which is what the sample-and-hold presents anyway --
    so this measures the SNDR that STATIC errors (INL, DNL, offset, kickback)
    allow. It does not include sampling jitter, input slewing during the
    acquisition window, or device noise (ngspice's transient analysis carries
    no device noise at all). It is an upper bound, and the parts it leaves out
    are named rather than folded in silently.
    """
    vins = [VCM + ampl * math.sin(2 * math.pi * cycles * i / n)
            for i in range(n)]
    codes = []
    for i in range(0, n, per_run):
        chunk = vins[i:i + per_run]
        codes.extend(convert(chunk, f"sar_fft_{i}", cmp_name))
        print(f"  {len(codes)}/{n} samples", flush=True)
    if any(c is None for c in codes):
        print(f"  {sum(1 for c in codes if c is None)} failed conversions",
              flush=True)
        return None
    mean = sum(codes) / n
    spec = []
    for k in range(n // 2 + 1):
        re_ = sum((codes[i] - mean) * math.cos(2 * math.pi * k * i / n)
                  for i in range(n))
        im = -sum((codes[i] - mean) * math.sin(2 * math.pi * k * i / n)
                  for i in range(n))
        spec.append((re_ * re_ + im * im) / (n * n))
    sig = spec[cycles]
    nd = sum(p for k, p in enumerate(spec) if k not in (0, cycles))
    sndr = 10 * math.log10(sig / nd) if nd > 0 else float("inf")
    enob = (sndr - 1.76) / 6.02
    # biggest non-signal bin: distortion shows up as a harmonic, noise does not
    worst = max((p, k) for k, p in enumerate(spec) if k not in (0, cycles))
    print(f"SNDR {sndr:.2f} dB -> ENOB {enob:.2f} bits "
          f"(ideal 8-bit SNDR 49.9 dB); largest spur in bin {worst[1]} at "
          f"{10*math.log10(worst[0]/sig):.1f} dBc", flush=True)
    return dict(codes=codes, sndr_db=sndr, enob=enob, spec=spec,
                n=n, cycles=cycles, ampl=ampl)


def main():
    global CMP
    what = sys.argv[1] if len(sys.argv) > 1 else "conv"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if len(sys.argv) > 3:
        CMP = sys.argv[3]
    print(f"=== SAR8, comparator = {CMP} ===", flush=True)
    res = {}
    if what == "conv":
        res["conv"] = run_conv(float(arg) if arg else 0.9)
    if what == "dac":
        res["dac"] = run_dac()
    if what == "fft":
        res["fft"] = run_fft(int(arg) if arg else 64)
    if what == "match":
        res["match"] = run_match(int(arg) if arg else 8)
    if what == "xfer":
        rows = run_xfer(int(arg) if arg else 256)
        res["xfer"] = rows
        lin = linearity(rows)
        res["lin"] = lin
        if lin:
            print(f"INL(sampled) max {lin['inl_max']:.2f} LSB, gain error "
                  f"{lin['gain_err']*100:+.2f} %, offset {lin['offset_code']:+.2f} "
                  f"codes, {len(lin['missing'])} failed conversions", flush=True)
    if res:
        p = OUT / f"sar_{what}.json"
        p.write_text(json.dumps(res, indent=1))
        print(f"-> {p}", flush=True)


if __name__ == "__main__":
    main()
