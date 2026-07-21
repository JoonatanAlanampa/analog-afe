"""Input-referred noise: the phase-1 bench the topology decision waits on.

Why this one first. The NMOS input pair was not chosen, it was FORCED --
a PMOS pair cannot bias at mid-rail on 1.8 V (docs/design-notes.md §1).
The device that survived is the noisier one in the flicker band, and
audio IS a flicker band. Until that cost is a number, the "cost stated
honestly" in the design notes is a caveat, not evidence.

What it measures, per candidate, in the unity-gain configuration:

  * total input-referred noise integrated over 20 Hz - 20 kHz, against
    spec row 13 (< 100 uV rms)
  * the flicker corner -- where 1/f noise power falls to the thermal
    floor. In audio this number matters more than the total: below the
    corner the noise is coloured and audible as hiss/rumble character.
  * which DEVICE dominates, and by which MECHANISM. ngspice exposes
    per-device `.1overf` (flicker) and `.id` (thermal channel) vectors,
    so this is measured per transistor, not attributed by argument.

And, for the comparison the design notes owe: ota_5t_pmos, the abandoned
PMOS-input version, simulated at a common mode where it actually works
(0.5 V). That is the price of the headroom decision.

    python tb/noise.py            # all candidates -> docs/noise.md
    python tb/noise.py miller_ota

NOTE the analyses are run at each candidate's OWN valid common mode, and
the PMOS reference has the opposite bias polarity (its vb diode goes to
VDD, so it needs a sink, not a source). Comparing two amplifiers at a
common mode where one of them does not bias is how the first version of
this whole bench went wrong; it is not repeated here.
"""
import json
import math
import sys
from pathlib import Path

from common import (VDD, VCM, TEMP, ROOT, OUT, MODELS, header, load_net,
                    run_ngspice, parse_meas, read_wrdata, ib_of, subckt_of,
                    VARIANTS, SPICE)
from benches import DEV_RE

# candidate -> (spice stem, bias current, input common mode, bias polarity)
#   "src"  = current pushed INTO vb  (diode-connected NMOS to vss)
#   "sink" = current pulled OUT of vb (diode-connected PMOS to vdd)
CANDIDATES = {name: (sub, ib, VCM, "src") for name, (sub, ib) in VARIANTS.items()}
CANDIDATES["ota_5t_pmos"] = ("ota_5t_pmos", 20e-6, 0.5, "sink")

F_LO, F_HI = 20.0, 20e3          # the audio band, and the spec's band
NOISE_LIMIT_UV = 100.0           # spec row 13
LOAD = "line"                    # the primary corner
# Spec row 3: 1 V pp output, centred mid-rail. A microvolt figure only
# becomes a decision once it is a ratio against the signal that has to
# sit on top of it.
SIGNAL_VRMS = 1.0 / (2 * math.sqrt(2))          # 1 V pp sine = 354 mV rms


def _preamble(name, load):
    sub, ib, vcm, pol = CANDIDATES[name]
    src = f"ib 0 vb dc {ib}" if pol == "src" else f"ib vb 0 dc {ib}"
    return f"""{header()}
{(SPICE / f'{sub}.sp').read_text()}
vdd vdd 0 dc {VDD}
vss vss 0 0
{src}
xdut vin vout vout vb vdd vss {sub}
{load_net(load)}
vin vin 0 dc {vcm} ac 1
"""


def devices_of(stem):
    """Transistors of a spice file, BY FILE -- not via VARIANTS.

    ota_5t_pmos is deliberately not a candidate, so it has no VARIANTS
    entry; resolving through that table is what broke the first run.
    """
    txt = (SPICE / f"{stem}.sp").read_text()
    return [(m.group(1), m.group(6)) for m in DEV_RE.finditer(txt)]


def totals(name, load=LOAD):
    """Integrated input/output noise plus the spectrum, over the band."""
    tag = f"noise_{name}_{load}"
    net = f"""* {name} noise, load={load}
{_preamble(name, load)}
.noise v(vout) vin dec 40 {F_LO} {F_HI}
.control
run
setplot noise2
print inoise_total onoise_total
setplot noise1
wrdata {tag}_spec.txt inoise_spectrum
.endc
.end
"""
    out = run_ngspice(net, tag)
    v = parse_meas(out)
    res = dict(inoise_v=v.get("inoise_total"), onoise_v=v.get("onoise_total"))
    rows = read_wrdata(OUT / f"{tag}_spec.txt", 2)
    res["spectrum"] = rows
    if rows:
        # input-referred density at the band edges, nV/rtHz
        res["in_20hz_nv"] = rows[0][1] * 1e9
        res["in_20khz_nv"] = rows[-1][1] * 1e9
    return res


def breakdown(name, freq, load=LOAD):
    """Per-device, per-mechanism output noise power at one frequency.

    A single-point .noise makes every per-device vector a scalar, so the
    values come back through the same `name = value` parser the operating
    point bench uses -- no log scraping.
    """
    sub = CANDIDATES[name][0]
    tag = f"noisedev_{name}_{int(freq)}"
    prints = []
    names = []
    for inst, model in devices_of(sub):
        for mech in ("1overf", "id"):
            vec = f"onoise.m.xdut.x{inst}.m{model}.{mech}"
            prints.append(f"print {vec}")
            names.append((inst, mech, vec.lower()))
    net = f"""* {name} per-device noise at {freq} Hz
{_preamble(name, load)}
.noise v(vout) vin lin 1 {freq} {freq} 1
.control
run
setplot noise1
{chr(10).join(prints)}
.endc
.end
"""
    out = run_ngspice(net, tag)
    v = parse_meas(out)
    contrib = {}
    for inst, mech, vec in names:
        val = v.get(vec)
        if val is None or val != val:
            continue
        contrib.setdefault(inst, {})[mech] = val      # V^2/Hz
    return contrib


def flicker_corner(name, load=LOAD):
    """Frequency where summed 1/f noise power equals summed thermal.

    Measured, by evaluating both mechanisms across the band and finding
    the crossing -- not read off a slope by eye.
    """
    pts = []
    f = F_LO
    while f <= F_HI * 1.001:
        c = breakdown(name, f, load)
        one = sum(d.get("1overf", 0.0) for d in c.values())
        th = sum(d.get("id", 0.0) for d in c.values())
        pts.append((f, one, th))
        f *= 10.0
    for i in range(1, len(pts)):
        f0, o0, t0 = pts[i - 1]
        f1, o1, t1 = pts[i]
        if o0 <= 0 or o1 <= 0 or t0 <= 0 or t1 <= 0:
            continue
        r0, r1 = math.log10(o0 / t0), math.log10(o1 / t1)
        if r0 >= 0 >= r1:                     # crosses unity in this decade
            k = r0 / (r0 - r1)
            return 10 ** (math.log10(f0) + k * (math.log10(f1) -
                                                math.log10(f0))), pts
    return None, pts


def corner_note(corner, pts):
    """Say WHERE the corner is, or how far outside the band it sits.

    'above band' on its own is not a measurement. If 1/f still dominates
    at 20 kHz, the number that matters is by how much -- that is what
    says whether the whole audio band is flicker-coloured or only its
    bottom octave.
    """
    if corner:
        return f"{corner:.0f} Hz"
    if pts:
        f, one, th = pts[-1]
        if th > 0 and one > th:
            return f"> {f/1e3:.0f} kHz (1/f still {one/th:.1f}x thermal)"
        if one > 0 and th >= one:
            return f"< {pts[0][0]:.0f} Hz (thermal-dominated in band)"
    return "--"


def snr_db(inoise_v):
    if not inoise_v or inoise_v <= 0:
        return None
    return 20 * math.log10(SIGNAL_VRMS / inoise_v)


def fmt_d(x, unit):
    """Auto-scaled noise density."""
    if x is None or x != x:
        return "--"
    return (f"{x/1e3:.2f} µ{unit}" if abs(x) >= 1e3 else f"{x:.3g} n{unit}")


def fmt_v(x, unit="V"):
    if x is None or x != x:
        return "--"
    for scale, pre in ((1e-6, "µ"), (1e-9, "n"), (1e-12, "p")):
        if abs(x) >= scale:
            return f"{x/scale:.3g} {pre}{unit}"
    return f"{x:.3g} {unit}"


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    names = [only] if only else list(CANDIDATES)
    cache = OUT / "noise.json"
    res = {}
    if cache.exists():                  # so one candidate can be re-run
        try:                            # without dropping the others
            res = json.loads(cache.read_text())
        except ValueError:
            res = {}
    for n in names:
        print(f"--- noise {n}", flush=True)
        t = totals(n)
        corner, pts = flicker_corner(n)
        c1k = breakdown(n, 1000.0)
        res[n] = dict(tot=t, corner=corner, pts=pts, c1k=c1k)
        cache.write_text(json.dumps(res, indent=1))
        print(f"    input-referred {fmt_v(t['inoise_v'])} rms "
              f"({F_LO:.0f} Hz - {F_HI/1e3:.0f} kHz), "
              f"flicker corner {corner_note(corner, pts)}",
              flush=True)
    write({k: res[k] for k in CANDIDATES if k in res})


def write(res):
    L = ["# Input-referred noise\n",
         "Generated by `python tb/noise.py`. sky130 `tt` models, "
         f"{VDD} V, {TEMP} C, unity-gain buffer into the `{LOAD}` load, "
         f"integrated {F_LO:.0f} Hz - {F_HI/1e3:.0f} kHz.\n",
         "Spec row 13 is < 100 µV rms input-referred, unweighted.\n",
         "**`ota_5t_pmos` is not a candidate.** It is the abandoned "
         "PMOS-input design, simulated at the 0.5 V common mode where it "
         "actually biases, purely to price the headroom decision that "
         "forced the NMOS pair (`design-notes.md` §1). Comparing it at "
         "mid-rail would compare against a circuit that does not work.\n",
         "| candidate | V_CM | input-referred, total | vs spec | "
         "SNR vs 1 V pp | density @20 Hz | @20 kHz | flicker corner |",
         "|---|---|---|---|---|---|---|---|"]
    for n, r in res.items():
        t = r["tot"]
        iv = t.get("inoise_v")
        verdict = "--"
        if iv:
            verdict = ("PASS" if iv * 1e6 < NOISE_LIMIT_UV
                       else "**FAIL**")
        corner_s = corner_note(r["corner"], r["pts"])
        sn = snr_db(iv)
        L.append(f"| {n} | {CANDIDATES[n][2]:.1f} V "
                 f"| {fmt_v(iv)} rms | {verdict} "
                 f"| {f'{sn:.1f} dB' if sn else '--'} "
                 f"| {fmt_d(t.get('in_20hz_nv'), 'V/√Hz')} "
                 f"| {fmt_d(t.get('in_20khz_nv'), 'V/√Hz')} "
                 f"| {corner_s} |")

    L.append("\n## Dominant contributors at 1 kHz\n")
    L.append("Share of total OUTPUT noise power, split by mechanism. "
             "`1overf` is flicker, `id` is thermal channel noise.\n")
    for n, r in res.items():
        c = r["c1k"]
        tot = sum(sum(d.values()) for d in c.values())
        if not tot:
            continue
        L.append(f"### {n}\n")
        L.append("| device | flicker | thermal | share of total |")
        L.append("|---|---|---|---|")
        rank = sorted(c.items(), key=lambda kv: -sum(kv[1].values()))
        for inst, d in rank:
            s = sum(d.values())
            L.append(f"| x{inst} | {100*d.get('1overf',0)/max(s,1e-30):.0f} % "
                     f"| {100*d.get('id',0)/max(s,1e-30):.0f} % "
                     f"| **{100*s/tot:.1f} %** |")
        L.append("")
    p = Path(ROOT / "docs" / "noise.md")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
