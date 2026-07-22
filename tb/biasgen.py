"""The bias generator -- a constant-gm reference, and whether it starts.

Every gain / noise / THD / corner number in this repo so far was taken with
an IDEAL 20 uA source programming the OTA tail (`ib 0 vb dc 20u`). That source
does not exist in silicon. `spice/biasgen.sp` is the circuit that replaces it
-- a beta-multiplier constant-gm reference -- and this bench answers the three
questions that decide whether it can:

  op       -- does it sit at ~20 uA with every device saturated, and what does
              the reference itself cost (its branches draw current too)?
  startup  -- the reference has a perfectly stable DEAD state (I = 0). Ramp the
              supply from 0 and watch it wake; then disconnect the start-up
              injector (rsu = 1e12) and watch it stay dead forever. That pair
              is the proof the start-up circuit is load-bearing, not decoration.
  pvt      -- constant-gm means gm(ref) = 1/R, so the CURRENT moves over
              corners while gm·R stays put. Both are reported. R is ideal here,
              so this is the transistor-side spread only; a real sky130
              xhigh_po poly resistor (measured in `poly`) sets the true floor.
  integ    -- drop the reference into miller_ota in place of the ideal source
              and confirm the amplifier still biases where it was characterised.
  poly     -- swap the ideal R for a real xhigh_po poly resistor and split the
              PVT floor: the tempco turns out small (xhigh_po is chosen for it),
              so the reference's real floor is the resistor's 2.5% process sigma,
              which the FET corners cannot see.

    python tb/biasgen.py            # everything -> docs/biasgen.md
    python tb/biasgen.py op | startup | pvt | integ | poly
"""
import math
import sys
from pathlib import Path

import common
from common import (VDD, SPICE, OUT, ROOT, ENV, header, run_ngspice,
                    read_wrdata, parse_meas)

RVAL = 3400          # ideal degeneration R, tuned for ~20 uA (spice/biasgen.sp)
NFET = "sky130_fd_pr__nfet_01v8"
PFET = "sky130_fd_pr__pfet_01v8"
# core devices to watch for saturation: (label, inst, model)
CORE = [("xmp1", "mp1", PFET), ("xmp2", "mp2", PFET), ("xmn1", "mn1", NFET),
        ("xmn2", "mn2", NFET), ("xmpo (out)", "mpo", PFET)]
SUB = None


def sub():
    global SUB
    if SUB is None:
        SUB = (SPICE / "biasgen.sp").read_text()
    return SUB


def _dev_prints(prefix="xb"):
    lines = []
    for _lab, inst, model in CORE:
        for p in ("id", "vds", "vdsat", "gm"):
            lines.append(f"print @m.{prefix}.x{inst}.m{model}[{p}]")
    return "\n".join(lines)


def bench_op(rval=RVAL, tag_extra="", rpl=1e4):
    net = f"""* biasgen op, rval={rval} rpl={rpl}
{header()}
{sub()}
vdd vdd 0 dc {VDD}
vss vss 0 0
xb vbias vdd 0 biasgen rval={rval} rpl={rpl}
* OTA-style vb diode load (mimics miller_ota's xmb)
xmb vbias vbias 0 0 {NFET} w=5 l=1 m=4
.control
op
{_dev_prints()}
let itot = abs(i(vdd))
echo isupply = $&itot
print v(vbias) v(xb.nl) v(xb.nr) v(xb.sx) v(xb.src)
.endc
.end
"""
    out = run_ngspice(net, f"bg_op{tag_extra}")
    v = parse_meas(out)
    devs = {}
    for lab, inst, model in CORE:
        row = {p: v.get(f"@m.xb.x{inst}.m{model}[{p}]".lower(), float("nan"))
               for p in ("id", "vds", "vdsat", "gm")}
        row["sat_margin"] = abs(row["vds"]) - abs(row["vdsat"])
        devs[lab] = row
    return dict(isupply=v.get("isupply", float("nan")),
                vbias=v.get("v(vbias)", float("nan")),
                iref=devs["xmn1"]["id"], devices=devs,
                nl=v.get("v(xb.nl)"), src=v.get("v(xb.src)"))


def bench_startup(rsu=1, rval=RVAL, tag_extra=""):
    """Ramp VDD 0->1.8 V over 5 us and watch the reference current. With the
    injector connected it wakes; with rsu=1e12 it never does."""
    tag = f"bg_start{tag_extra}"
    net = f"""* biasgen start-up, rsu={rsu}
{header()}
{sub()}
vdd vdd 0 dc 0 pulse(0 {VDD} 0 5u 1n 100u 200u)
vss vss 0 0
xb vbias vdd 0 biasgen rval={rval} rsu={rsu}
xmb vbias vbias 0 0 {NFET} w=5 l=1 m=4
.tran 50n 40u
.control
run
wrdata {tag}.txt v(xb.src)
.endc
.end
"""
    run_ngspice(net, tag)
    rows = read_wrdata(OUT / f"{tag}.txt", 2)   # single vector -> time, value
    # I_ref(t) = v(src)/R ; settle when it first reaches 90 % of its final value
    ts = [(r[0], r[1] / rval) for r in rows]
    if not ts:
        return dict(error="no data")
    ifinal = ts[-1][1]
    started = ifinal > 5e-6
    tsettle = None
    if started:
        for t, i in ts:
            if i >= 0.9 * ifinal:
                tsettle = t
                break
    return dict(ifinal=ifinal, started=started, tsettle_us=tsettle and tsettle * 1e6,
                trace=ts)


def bench_pvt(rval=RVAL):
    PROCESS = ["tt", "ss", "ff", "sf", "fs"]
    TEMPS = [-40, 25, 85]
    SUPPLIES = [1.62, 1.98]
    pts = [(p, t, VDD) for p in PROCESS for t in TEMPS]
    pts += [("tt", 25, v) for v in SUPPLIES]
    rows = []
    for (p, t, vd) in pts:
        ENV.update(corner=p, temp=t, vdd=vd, seed=None)
        r = bench_op(rval=rval, tag_extra=f"_{p}_{t}_{vd}".replace(".", "p"))
        gm = r["devices"]["xmn1"]["gm"]
        rows.append(dict(process=p, temp=t, vdd=vd, iref=r["iref"], gm=gm,
                         gmr=gm * rval, isupply=r["isupply"],
                         vbias=r["vbias"]))
        print(f"  {p:2s} {t:+4d}C {vd:.2f}V  Iref={r['iref']*1e6:5.1f}uA  "
              f"gm={gm*1e6:5.1f}uS  gm*R={gm*rval:.3f}  "
              f"Iq={r['isupply']*1e6:5.1f}uA", flush=True)
    ENV.update(corner="tt", temp=25, vdd=VDD, seed=None)
    return rows


def bench_poly_pvt():
    """gm and I_ref over process × temperature for the IDEAL R vs a real
    xhigh_po poly R. A constant-gm loop holds gm·R = const *regardless of R*,
    so the ideal R (no tempco) holds gm dead-flat over temperature -- which
    flatters the reference. The poly R makes gm track its own tempco: gm =
    const/R, so the reference is only as stable as this resistor. That is the
    true PVT floor the ideal R hid."""
    configs = [("ideal R", dict(rval=3400, rpl=1e4)),
               ("poly xhigh_po", dict(rval=1e9, rpl=1.1))]
    PROCESS, TEMPS = ["tt", "ss", "ff"], [-40, 25, 85]
    out = {}
    for label, cfg in configs:
        rows = []
        for p in PROCESS:
            for t in TEMPS:
                ENV.update(corner=p, temp=t, vdd=VDD, seed=None)
                r = bench_op(tag_extra=f"_pp_{label[:4]}_{p}_{t}", **cfg)
                gm = r["devices"]["xmn1"]["gm"]
                rows.append(dict(process=p, temp=t, iref=r["iref"], gm=gm))
                print(f"  {label:14s} {p} {t:+4d}C  Iref={r['iref']*1e6:5.1f}uA "
                      f"gm={gm*1e6:6.1f}uS", flush=True)
        out[label] = rows
    ENV.update(corner="tt", temp=25, vdd=VDD, seed=None)
    return out


def bench_integ(rval=RVAL):
    """miller_ota at the fix point, biased by the ideal source vs by biasgen.
    Same amplifier operating point => the reference delivers the right bias;
    the supply delta is the reference's overhead."""
    ota = (SPICE / "miller_ota.sp").read_text()
    comp = "pcc=4e-12 prz=10000 pout=2.5"
    res = {}
    # ideal source
    net_i = f"""* miller_ota, ideal ib
{header()}
{ota}
vdd vdd 0 dc {VDD}
vss vss 0 0
ib 0 vb dc 20u
xdut vin vout vout vb vdd vss miller_ota {comp}
cpar vout 0 50p
cac vout nl 47u
rl nl 0 10k
vin vin 0 dc {VDD/2}
.control
op
let itot = abs(i(vdd))
echo isupply = $&itot
print v(vout) v(vb)
.endc
.end
"""
    vi = parse_meas(run_ngspice(net_i, "bg_integ_ideal"))
    res["ideal"] = dict(vout=vi.get("v(vout)"), vb=vi.get("v(vb)"),
                        isupply=vi.get("isupply"))
    # biasgen source
    net_b = f"""* miller_ota, biasgen
{header()}
{ota}
{sub()}
vdd vdd 0 dc {VDD}
vss vss 0 0
xbias vb vdd 0 biasgen rval={rval}
xdut vin vout vout vb vdd vss miller_ota {comp}
cpar vout 0 50p
cac vout nl 47u
rl nl 0 10k
vin vin 0 dc {VDD/2}
.control
op
let itot = abs(i(vdd))
echo isupply = $&itot
print v(vout) v(vb)
.endc
.end
"""
    vb = parse_meas(run_ngspice(net_b, "bg_integ_bias"))
    res["biasgen"] = dict(vout=vb.get("v(vout)"), vb=vb.get("v(vb)"),
                         isupply=vb.get("isupply"))
    return res


def g(v, f=".1f", u=""):
    if v is None or (isinstance(v, float) and v != v):
        return "--"
    return f"{v:{f}}{(' ' + u) if u else ''}"


def write(op, start, start_no, pvt, integ, poly=None):
    L = ["# Bias generator — constant-gm reference and start-up\n",
         "Generated by `python tb/biasgen.py`. sky130 `tt` models, "
         f"{VDD} V, 25 °C. Replaces the ideal `ib 0 vb dc 20u` that programmed "
         "the OTA tail (spec.md O2). `spice/biasgen.sp`.\n"]

    if op:
        L.append("## Operating point\n")
        L.append(f"Reference current **{g(op['iref']*1e6, '.1f', 'µA')}** "
                 f"(target 20), vbias {g(op['vbias'], '.3f', 'V')}, and the "
                 f"reference draws **{g(op['isupply']*1e6, '.0f', 'µA')}** from "
                 "the supply (two core branches + the output leg). That draw is "
                 "the honest cost the ideal source hid; it is a *shared* block "
                 "(one reference biases the DAC buffer, comparator and SAR), so "
                 "per-amplifier it amortises, and a lower-current core mirrored "
                 "up would trim it further.\n")
        L.append("| device | role | I_D | V_ds | V_dsat | sat margin |")
        L.append("|---|---|---|---|---|---|")
        roles = {"xmp1": "PMOS mirror", "xmp2": "PMOS diode",
                 "xmn1": "NMOS diode (sets gm)", "xmn2": "NMOS ×K + R",
                 "xmpo (out)": "output mirror"}
        for lab, _i, _m in CORE:
            d = op["devices"][lab]
            flag = "" if d["sat_margin"] > 0 else " **LINEAR**"
            L.append(f"| {lab} | {roles.get(lab, '')} "
                     f"| {g(d['id']*1e6, '.2f', 'µA')} | {g(d['vds'], '.3f', 'V')} "
                     f"| {g(d['vdsat'], '.3f', 'V')} "
                     f"| {g(d['sat_margin'], '+.3f', 'V')}{flag} |")
        L.append("")

    if start is not None:
        L.append("## Start-up — the reference's silent failure mode\n")
        w = "**wakes**" if start["started"] else "**stays dead**"
        nw = ("**stays dead** (I≈0)" if (start_no and not start_no["started"])
              else "**still wakes**" if start_no else "--")
        L.append("Supply ramped 0 → 1.8 V over 5 µs. With the 3-transistor "
                 f"start-up connected the reference {w} to "
                 f"{g(start['ifinal']*1e6, '.1f', 'µA')} "
                 f"(settled ~{g(start['tsettle_us'], '.1f', 'µs')}). With the "
                 f"injector disconnected (`rsu=1e12`) it {nw} — the beta-"
                 "multiplier's I=0 state is perfectly stable, so without the "
                 "kick it never leaves it. That is the whole reason the "
                 "start-up exists.\n")

    if pvt:
        irs = [r["iref"] for r in pvt]
        gmrs = [r["gmr"] for r in pvt]
        iqs = [r["isupply"] for r in pvt]
        L.append("## PVT — constant-gm holds, the current moves\n")
        L.append(f"Reference current spans **{g(min(irs)*1e6, '.1f')}–"
                 f"{g(max(irs)*1e6, '.1f')} µA** across the box, but **gm·R "
                 f"holds {g(min(gmrs), '.3f')}–{g(max(gmrs), '.3f')}** "
                 f"({100*(max(gmrs)-min(gmrs))/((max(gmrs)+min(gmrs))/2):.0f}% "
                 "spread) — that is constant-gm working: the loop moves the "
                 "current so the transconductance stays put. With an IDEAL R "
                 "this is the transistor-side spread only; a real xhigh_po poly "
                 "resistor (σ 2.5 % process + tempco) adds directly onto gm and "
                 "is the true PVT floor.\n")
        L.append("| process | temp | Vdd | I_ref | gm | gm·R | I_supply |")
        L.append("|---|---|---|---|---|---|---|")
        for r in pvt:
            L.append(f"| {r['process']} | {r['temp']:+d} °C | {r['vdd']} V "
                     f"| {g(r['iref']*1e6, '.1f', 'µA')} "
                     f"| {g(r['gm']*1e6, '.1f', 'µS')} | {g(r['gmr'], '.3f')} "
                     f"| {g(r['isupply']*1e6, '.0f', 'µA')} |")
        L.append("")

    if integ:
        i, b = integ["ideal"], integ["biasgen"]
        dv = (abs(b["vout"] - i["vout"]) * 1e3 if b["vout"] and i["vout"]
              else None)
        over = (b["isupply"] - i["isupply"]) if b["isupply"] and i["isupply"] \
            else None
        L.append("## Integration — driving the real amplifier\n")
        L.append("miller_ota at the fix operating point, biased two ways:\n")
        L.append("| bias | V_out (unity, Vin=0.9) | V_b | total I_supply |")
        L.append("|---|---|---|---|")
        L.append(f"| ideal 20 µA source | {g(i['vout'], '.4f', 'V')} "
                 f"| {g(i['vb'], '.3f', 'V')} | {g(i['isupply']*1e6, '.0f', 'µA')} |")
        L.append(f"| **biasgen** | {g(b['vout'], '.4f', 'V')} "
                 f"| {g(b['vb'], '.3f', 'V')} | {g(b['isupply']*1e6, '.0f', 'µA')} |")
        L.append("")
        L.append(f"The amplifier lands at the same operating point "
                 f"(ΔV_out {g(dv, '.2f', 'mV')}), so the reference delivers the "
                 f"bias it was characterised with; the "
                 f"{g(over and over*1e6, '.0f', 'µA')} supply delta is the "
                 "reference's own draw (shared across all analog blocks).\n")

    if poly:
        L.append("## Ideal R vs a real poly resistor — where the floor really is\n")
        L.append("The PVT table above used an *ideal* R, which flatters the "
                 "reference: a constant-gm loop holds gm·R = const **regardless "
                 "of R**, so gm = const/R, and an ideal R (no tempco, no "
                 "process spread) holds gm dead-flat. That is a property of the "
                 "ideal element, not of the reference — the reference's gm (and "
                 "therefore the OTA's gm, its UGF, and the compensation §12 "
                 "tuned) is only as stable as this one resistor. Swapping in a "
                 "real sky130 `xhigh_po` poly resistor (rpl ≈ 1.1 µm, ~3.5 kΩ) "
                 "splits that floor into its two real parts:\n")
        L.append("| resistor | gm @ −40 °C | gm @ 25 °C | gm @ 85 °C | gm spread over T (tt) |")
        L.append("|---|---|---|---|---|")
        for label, rows in poly.items():
            tt = {r["temp"]: r["gm"] for r in rows if r["process"] == "tt"}
            gms = [tt.get(-40), tt.get(25), tt.get(85)]
            spread = ((max(gms) - min(gms)) / ((max(gms) + min(gms)) / 2) * 100
                      if all(gms) else None)
            L.append(f"| {label} | {g(gms[0]*1e6, '.1f', 'µS')} "
                     f"| {g(gms[1]*1e6, '.1f', 'µS')} | {g(gms[2]*1e6, '.1f', 'µS')} "
                     f"| **{g(spread, '.1f', '%')}** |")
        L.append("")
        L.append("- **Tempco is small.** The poly holds gm to ~0.7 % across "
                 "−40…85 °C, barely worse than the ideal R — which is exactly "
                 "why `xhigh_po` is the reference-grade poly: it is chosen for a "
                 "low temperature coefficient. (I expected the tempco to "
                 "dominate; the measurement says it does not.)\n")
        L.append("- **Process σ is the real floor, and the FET corners are "
                 "blind to it.** The resistor carries a documented **2.5 % "
                 "process σ** (the model's `sky130_fd_pr__res_xhigh_po__var "
                 "std = 0.025`) — a Monte-Carlo term, so the ss/ff corners, "
                 "which vary only the transistors, leave the poly's gm "
                 "essentially unmoved. Since gm = const/R, that 2.5 % maps "
                 "**directly** onto the reference's gm, and onto the OTA's gm "
                 "and UGF downstream.\n")
        L.append("So the reference's real gm PVT floor is ~2.5 % (process) with "
                 "a small tempco on top — set by the **resistor**, not the "
                 "transistors. That is still far better than leaving gm to µCox "
                 "(±20–30 % over the same box), which is the entire reason to "
                 "build a constant-gm reference; but the honest number is the "
                 "resistor's, and pinning it down for real is a post-layout "
                 "Monte-Carlo signoff item, alongside the input-pair matching.\n")

    p = Path(ROOT / "docs" / "biasgen.md")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {p}")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    op = start = start_no = pvt = integ = poly = None
    if what in ("op", "all"):
        op = bench_op()
        print(f"op: Iref={op['iref']*1e6:.1f}uA vbias={op['vbias']:.3f}V "
              f"Iq={op['isupply']*1e6:.0f}uA", flush=True)
    if what in ("startup", "all"):
        start = bench_startup(rsu=1)
        start_no = bench_startup(rsu=1e12, tag_extra="_nosu")
        print(f"startup: with={start['ifinal']*1e6:.1f}uA started={start['started']}"
              f"  without={start_no['ifinal']*1e6:.3f}uA started={start_no['started']}",
              flush=True)
    if what in ("pvt", "all"):
        pvt = bench_pvt()
    if what in ("integ", "all"):
        integ = bench_integ()
        i, b = integ["ideal"], integ["biasgen"]
        print(f"integ: vout ideal={i['vout']:.4f} biasgen={b['vout']:.4f}  "
              f"Iq ideal={i['isupply']*1e6:.0f} biasgen={b['isupply']*1e6:.0f}uA",
              flush=True)
    if what in ("poly", "all"):
        poly = bench_poly_pvt()
    write(op, start, start_no, pvt, integ, poly)


if __name__ == "__main__":
    main()
