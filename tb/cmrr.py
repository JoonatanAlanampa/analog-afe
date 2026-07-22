"""Common-mode: rejection (CMRR) and input range (ICMR).

Two characterisations of the same thing -- how the input pair handles a
common-mode voltage -- and both matter for a unity-gain buffer specifically,
because in unity gain the input common mode IS the signal: it swings with the
output, 0.4-1.4 V for a 1 V pp output centred at mid-rail.

  CMRR -- differential gain / common-mode gain (`bench_cmrr`, benches.py),
          at DC / 1 kHz / 20 kHz. A CM error at the input appears at the
          output divided by CMRR; since the CM moves at the signal rate, low
          CMRR turns into distortion and crosstalk from the shared supply's
          common-mode.

  ICMR -- the input common-mode RANGE: sweep V_CM and watch where the
          open-loop gain holds and the tail + input pair stay saturated.
          This is a direct cross-check on the THD story (design-notes §11/§12):
          if the INPUT pair, not the output stage, set the 1 V pp distortion,
          then scaling the output stage would NOT have fixed THD -- and it did
          (1.44 % -> 0.167 %). So ICMR_low must sit below the 0.4 V output
          trough. This measures by how much.

Everything is quoted at the applied fix operating point (design-notes §12);
ICMR is an input-pair property, so the output-stage scaling barely moves it,
but CMRR rides on A_dm and so improves with the fix's extra loop gain.

    python tb/cmrr.py            # both -> docs/cmrr.md
    python tb/cmrr.py cmrr
    python tb/cmrr.py icmr
"""
import math
import sys
from pathlib import Path

from common import (VDD, OUT, ROOT, header, ib_of, load_net, run_ngspice,
                    read_wrdata, parse_meas, subckt_of)
from benches import bench_cmrr, _preamble
from thd import run_thd

# operating points (design-notes §12 / topology-review Call 3)
FIX_COMP, FIX_POUT = "pcc=4e-12 prz=10000", 2.5
FIX = f"{FIX_COMP} pout={FIX_POUT}"
SHIPPED = "pcc=2e-12 prz=20000 pout=1"
LOAD = "line"

# THD vs output swing AT THE FIX POINT -- the measured half of the ICMR/THD
# cross-check. If the residual THD floor were the output stage, shrinking the
# swing would not help; if it is the input-pair ICMR (input triodes at the
# 1.40 V peak of a 1 Vpp swing), a smaller swing that keeps the peak inside
# ICMR should be dramatically cleaner. It is (0.0045 % at 0.4 Vpp).
FIX_SWINGS = [0.4, 0.6, 0.8, 1.0, 1.2]

# input-pair devices to watch for ICMR (miller_ota): tail + the two inputs,
# all sky130 nfet_01v8. Values are the instance stem WITHOUT the leading `x`
# (the query template re-adds it, matching benches.py's `x{inst}` — the `x`
# is not part of the stem, so "xm0" here would query the nonexistent "xxm0").
NFET = "sky130_fd_pr__nfet_01v8"
ICMR_DEVS = {"xm0 (tail)": "m0", "xm1 (in-)": "m1", "xm2 (in+)": "m2"}


def run_cmrr():
    rows = []
    for name, params in (("fix (×2.5, Cc 4p, Rz 10k)", FIX),
                         ("shipped (×1, Cc 2p, Rz 20k)", SHIPPED)):
        r = bench_cmrr("miller_ota", LOAD, params=params,
                       tag_extra=f"_{'fix' if params == FIX else 'shp'}")
        r["name"] = name
        rows.append(r)
        print(f"CMRR {name:28s} DC {r.get('cmrr_dc_db', float('nan')):5.1f} "
              f"1k {r.get('cmrr_1k_db', float('nan')):5.1f} "
              f"20k {r.get('cmrr_20k_db', float('nan')):5.1f} dB  "
              f"(A_dm/A_cm DC = {r.get('adm_dc_db', float('nan')):.1f}/"
              f"{r.get('acm_dc_db', float('nan')):.1f})", flush=True)
    return rows


def icmr_point(vc, params):
    """Open-loop gain + input-pair saturation at one input common mode.

    The 1 GH inductor closes the loop at DC, so driving the non-inverting
    input to vc forces the whole node (vinp = vinn = vout) to vc -- the CM
    is swept by sweeping this one source. The AC (injected differentially)
    reads the open-loop gain THERE; the op reads whether the tail and pair
    are still saturated."""
    tag = f"icmr_{int(round(vc*1000))}"
    prints = []
    for inst in ICMR_DEVS.values():
        prints.append(f"print @m.xdut.x{inst}.m{NFET}[vds]")
        prints.append(f"print @m.xdut.x{inst}.m{NFET}[vdsat]")
        prints.append(f"print @m.xdut.x{inst}.m{NFET}[id]")
    net = f"""* miller_ota ICMR, Vcm={vc}, load={LOAD} {params}
{_preamble('miller_ota', LOAD, params=params)}
vcm vinp 0 dc {vc}
lfb vout vinn 1e9
vac vac 0 dc 0 ac 1
cinj vac vinn 1e9
.control
op
{chr(10).join(prints)}
let itot = abs(i(vdd))
echo isupply = $&itot
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
    for label, inst in ICMR_DEVS.items():
        vds = vals.get(f"@m.xdut.x{inst}.m{NFET}[vds]".lower(), float("nan"))
        vdsat = vals.get(f"@m.xdut.x{inst}.m{NFET}[vdsat]".lower(), float("nan"))
        idv = vals.get(f"@m.xdut.x{inst}.m{NFET}[id]".lower(), float("nan"))
        devs[label] = dict(vds=vds, vdsat=vdsat, margin=abs(vds) - abs(vdsat),
                           idv=idv)
    return dict(vcm=vc, vout=vals.get("v(vout)", float("nan")), a_lf_db=a_lf,
                devices=devs)


def run_icmr(params=FIX):
    vcms = [round(0.20 + 0.05 * i, 2) for i in range(29)]   # 0.20 .. 1.60
    rows = []
    for vc in vcms:
        r = icmr_point(vc, params)
        rows.append(r)
        tail = r["devices"]["xm0 (tail)"]
        print(f"  Vcm {vc:.2f}  Vout {r['vout']:+.3f}  A_dc "
              f"{r['a_lf_db'] or float('nan'):5.1f} dB  tail Vds "
              f"{tail['vds']:+.3f} (marg {tail['margin']:+.3f})", flush=True)
    return rows


def run_thd_swing():
    """THD at the fix point vs output swing -- the measured half of the
    ICMR/THD cross-check (see FIX_SWINGS)."""
    rows = []
    for vpp in FIX_SWINGS:
        r = run_thd("miller_ota", 1000, vpp, comp=FIX_COMP, pout=FIX_POUT)
        rows.append(dict(vpp=vpp, **r))
        lo, hi = VDD / 2 - vpp / 2, VDD / 2 + vpp / 2
        print(f"  fix THD {vpp:.1f} Vpp (out {lo:.2f}-{hi:.2f} V) -> "
              f"{r['thd_pct']:.4f}%  (h2 {r['h2']*100:.4f} h3 "
              f"{r['h3']*100:.4f})", flush=True)
    return rows


def icmr_range(rows, drop_db=3.0):
    """The FUNCTIONAL CM range: where open-loop gain is within drop_db of its
    peak. Device saturation is reported separately as the mechanism -- on the
    low side the tail is already in triode yet the gain holds, so requiring
    every device saturated would understate the range the amp actually works
    over (see design-notes §13)."""
    good = [r for r in rows if r["a_lf_db"] is not None]
    if not good:
        return None, None, None
    peak = max(r["a_lf_db"] for r in good)
    ok = [r for r in good if r["a_lf_db"] >= peak - drop_db]
    if not ok:
        return None, None, peak
    lo = min(r["vcm"] for r in ok)
    hi = max(r["vcm"] for r in ok)
    return lo, hi, peak


def gd(v, f="+.3f"):
    return "--" if v is None or (isinstance(v, float) and v != v) else f"{v:{f}}"


def write(cmrr, icmr, swing=None):
    L = ["# Common-mode: rejection (CMRR) and input range (ICMR)\n",
         "Generated by `python tb/cmrr.py`. sky130 `tt` models, "
         f"{VDD} V, 25 °C, `line` load. In a unity-gain buffer the input "
         "common mode **is** the signal — it swings with the output — so "
         "both of these are load-bearing, not formalities.\n"]

    if cmrr:
        L.append("## CMRR — common-mode rejection\n")
        L.append("Differential gain over common-mode gain "
                 "(`bench_cmrr`): one open-loop AC injected differentially, "
                 "one with the same AC on both inputs, same DC operating "
                 "point. CMRR rides on A_dm, so the THD fix's extra loop gain "
                 "lifts it too.\n")
        L.append("| operating point | CMRR @ DC | @ 1 kHz | @ 20 kHz | "
                 "A_dm(DC) / A_cm(DC) |")
        L.append("|---|---|---|---|---|")
        for r in cmrr:
            L.append(f"| {r['name']} | **{gd(r.get('cmrr_dc_db'), '.1f')} dB** "
                     f"| {gd(r.get('cmrr_1k_db'), '.1f')} dB "
                     f"| {gd(r.get('cmrr_20k_db'), '.1f')} dB "
                     f"| {gd(r.get('adm_dc_db'), '.1f')} / "
                     f"{gd(r.get('acm_dc_db'), '.1f')} dB |")
        L.append("")

    if icmr:
        lo, hi, peak = icmr_range(icmr)
        # V_CM where the input pair (xm2) leaves saturation on the high side
        tri = next((r["vcm"] for r in icmr
                    if r["devices"]["xm2 (in+)"]["margin"] < 0), None)
        L.append("## ICMR — input common-mode range\n")
        L.append(f"Swept at the fix operating point (output = CM in unity "
                 f"gain). Peak open-loop gain **{gd(peak, '.1f')} dB**; within "
                 f"3 dB of it the range is **{gd(lo, '.2f')} … {gd(hi, '.2f')} "
                 f"V**, and the input pair (xm2) holds saturation up to "
                 f"**{gd(tri, '.2f')} V** before it triodes.\n")
        L.append("The range is **asymmetric**, and that asymmetry is the whole "
                 "THD story. *Low side:* the tail sits in triode below "
                 "~0.70 V, yet the gain holds to ~0.30 V (the pair keeps "
                 "working through a triode tail), so the 0.40 V output trough "
                 "is at PEAK gain. *High side:* the input pair itself runs out "
                 f"of headroom as the tail node rises and triodes at "
                 f"{gd(tri, '.2f')} V — **exactly the 1.40 V peak of a 1 V pp "
                 "swing.**\n")
        L.append("So the 0.40–1.40 V a 1 V pp output needs is covered on the "
                 "**low** side and hits the wall on the **high** side — which "
                 "splits the THD story cleanly (confirmed just below): the "
                 "shipped 1.44 % was the low-side OUTPUT sink, fixed by scaling "
                 "the output stage (design-notes §12); the fix's residual "
                 "0.167 % is the high-side INPUT ICMR, a different device that "
                 "output current cannot reach. **This corrects §12** — the "
                 "path to ≤ 0.1 % at the full 1 V pp is a wider-ICMR *input* "
                 "(rail-to-rail / complementary pair), not a class-AB output; "
                 "or a smaller swing.\n")
        L.append("| V_CM | V_out | A_dc | tail Vds (margin) | in-pair Vds "
                 "(margin) |")
        L.append("|---|---|---|---|---|")
        for r in icmr:
            t = r["devices"]["xm0 (tail)"]
            pp = r["devices"]["xm2 (in+)"]
            flag = "" if (r["a_lf_db"] or -300) >= (peak or 0) - 3 else " ⚠"
            L.append(f"| {r['vcm']:.2f} V | {gd(r['vout'])} V "
                     f"| {gd(r['a_lf_db'], '.1f')} dB{flag} "
                     f"| {gd(t['vds'])} ({gd(t['margin'])}) "
                     f"| {gd(pp['vds'])} ({gd(pp['margin'])}) |")
        L.append("")

        if swing:
            L.append("### THD vs swing at the fix point — the cross-check\n")
            L.append("If the fix's residual were the output stage, shrinking "
                     "the swing would not help. It does, dramatically: at "
                     "0.4 V pp (peak 1.10 V, inside ICMR) the buffer is ~37× "
                     "cleaner than at 1 V pp. The floor is the high-side input "
                     "ICMR, and it is a swing limit, not a current one.\n")
            L.append("| swing | output range | THD | 2nd | 3rd |")
            L.append("|---|---|---|---|---|")
            for r in swing:
                lo2 = VDD / 2 - r["vpp"] / 2
                hi2 = VDD / 2 + r["vpp"] / 2
                inr = "" if (tri is None or hi2 <= tri + 1e-9) else " ⟵ peak past ICMR"
                L.append(f"| {r['vpp']:.1f} Vpp{inr} | {lo2:.2f}–{hi2:.2f} V "
                         f"| **{r['thd_pct']:.4f} %** | {r['h2']*100:.4f} % "
                         f"| {r['h3']*100:.4f} % |")
            L.append("")

    p = Path(ROOT / "docs" / "cmrr.md")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {p}")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "both"
    cmrr = run_cmrr() if what in ("cmrr", "both") else None
    icmr = run_icmr() if what in ("icmr", "both") else None
    swing = run_thd_swing() if what in ("icmr", "both") else None
    write(cmrr, icmr, swing)


if __name__ == "__main__":
    main()
