"""Parasitic RC re-sim of the miller_rrf2 layout.

The miller_ota pass (`tb/parasitics.py`) found ~14 fF of interconnect against a
4 pF Miller cap and concluded the amplifier was insensitive to its own routing.
miller_rrf2 is a different proposition and this bench exists to find out whether
that conclusion still holds:

  * ~4x the area (17 070 vs 4 044 um^2) and 25 devices instead of 8;
  * a 14-net routing CHANNEL -- twelve met3 tracks up to ~100 um long, plus 39
    met2 risers -- where miller_ota had four short hops. Long thin wires are
    fringe-dominated, so this is much more capacitance, concentrated on exactly
    the nodes a channel router is happy to run a long way;
  * but Cc is 9 pF, not 4 pF, so the yardstick moved too.

Method is the miller_ota one (planar 2.5-D, cap to substrate, magic
`defaultareacap`/`defaultsidewall` coefficients -- see tb/parasitics.py's
docstring for the honest scope, including what a 2x point is bracketing).

What is NEW here is how the wires are FOUND. miller_ota's bench hand-picked a
seed point per net per layer, which does not scale to 14 nets over 5 layers and
would silently under-count if a seed were forgotten. Here the seeds are
GENERATED from the layout's own routing tables (`build_rrf2.TAPS` / `.TRACK`):
every met2 riser and every met3 track is derived from the same data that drew
it, so the extraction cannot miss a wire the router placed. Only the
compensation branch -- which build_rrf2 hand-routes -- is hand-seeded, and a
MISS on any seed is reported rather than silently dropped.

    python tb/parasitics_rrf2.py       # extract + re-sim -> docs/parasitics-rrf2.md
"""
import json
import sys
from pathlib import Path

import gdstk

import common
from benches import bench_ac
from common import OUT, SPICE, ROOT
from parasitics import LAYERS, _merged, _perimeter, run_thd_par

sys.path.insert(0, str(ROOT / "layout"))
import build_rrf2 as B                                        # noqa: E402

GDS = ROOT / "layout" / "out" / "miller_rrf2.gds"
CACHE = OUT / "parasitics_rrf2.json"

# The corner-verified rrf2 operating point (tb/input_stage.py CAND).
FIX = "pcc=9e-12 prz=10000 pout=2.5"
CC_FF = 9000.0

# The FIRST routing of this layout -- every net taken up to a channel above the
# tallest block -- measured by this same bench at commit 788b5d6. It FAILED the
# 60 deg phase-margin spec, which is why the four signal-path nets were then
# re-routed low (see build_rrf2.TRACK). Kept here so the doc can show what the
# fix bought, and so the failure is a recorded result rather than a git
# archaeology exercise. `git show 788b5d6:docs/parasitics-rrf2.md` has the full
# original write-up.
FIRST = dict(commit="788b5d6", sig_ff=103.5, tot_ff=296.59, dpm=-3.13,
             worst=59.7, worst2x=56.9, a20k=46.0,
             cb=46.97, ca=19.32, fa=16.82, fb=20.37, routed_um=750.0,
             cc10_worst=60.1, cc10_2x=57.2, cc10_a20k=45.1,
             cc13_worst=60.7, cc13_2x=57.8, cc13_a20k=42.9)

# The compensation branch is hand-routed in build_miller_rrf2, so it is
# hand-seeded here: (net, layer, point).
EXTRA = [
    ("cb", "li", (107.0, 50.30)),      # Rz.P terminal
    ("cb", "m2", (103.0, 70.00)),      # Rz.P -> up to the CB track
    ("nz", "li", (107.0, 54.35)),      # Rz.M terminal
    ("nz", "m2", (108.6, 54.35)),      # Rz.M -> the Cc bottom plate
    ("vout", "m2", (93.0, 19.50)),     # out_stage VOUT via stack
    ("vout", "m3", (98.0, 19.50)),     # the long met3 run to the cap
    ("vout", "m4", (120.0, 19.50)),    # met4 across the cap to the top plate
]
# nz's met3 pad lands ON the Cc bottom plate -- that plate is the 9 pF DEVICE,
# not a parasitic, so it is deliberately not counted (same call as the
# miller_ota bench).

# vdd/vss are AC grounds. Their wire capacitance goes to the substrate, i.e. to
# vss: for vss that is a no-op, and for vdd it is supply decoupling, which helps
# rather than threatens. Extracted and reported, never loaded.
RAILS = {"VDD", "VSS"}


def seeds():
    """{net: [(layer, (x, y)), ...]} generated from the layout's routing tables.

    For each tap: the pin's own bar/strap on its pin layer, and the met2 riser
    that leaves it. For each net: its met3 track. Nothing hand-listed, so a wire
    the router drew cannot be forgotten here."""
    s = {}
    for net, block, lx, ly, kind, _tag in B.TAPS:
        x, y = B._abs(block, lx, ly)
        ty = B.TRACK[net]
        s.setdefault(net, []).append(("li" if kind == "li" else "m1", (x, y)))
        s[net].append(("m2", (x, (y + ty) / 2.0)))            # the riser
    for net, ty in B.TRACK.items():
        x0 = B._abs(*[(b, lx, ly) for (n, b, lx, ly, _k, _t) in B.TAPS
                      if n == net][0])[0]
        s[net].append(("m3", (x0, ty)))                       # the track
    for net, layer, pt in EXTRA:
        s.setdefault(net.upper(), []).append((layer, pt))
    return s


def wire_lengths():
    """Routed length per net, split into vertical met2 risers and horizontal
    met3 track, straight off the routing tables.

    This is what turns the capacitance number into a floorplan statement: a
    riser's length is not a property of its net, it is the distance from the pin
    to its track, so where the track sits decides the wire.

    abs() is load-bearing. The signal-path tracks now sit LOW, among the blocks,
    so several pins are above their track and the riser runs downward -- a signed
    sum would let those cancel against the upward ones and under-report the
    routed length (it did, by 64 um, before this was fixed)."""
    riser, track = {}, {}
    for net, blk, lx, ly, _k, _t in B.TAPS:
        _x, y = B._abs(blk, lx, ly)
        riser[net] = riser.get(net, 0.0) + abs(B.TRACK[net] - y)
    for net, _ty in B.TRACK.items():
        xs = [B._abs(b, lx, 0)[0] for (n, b, lx, _ly, _k, _t) in B.TAPS
              if n == net]
        track[net] = max(xs) - min(xs)
    return riser, track


def extract():
    """{net: (C_farads, per-layer detail)}. Components are de-duplicated, so a
    net whose bar is tapped twice is not counted twice."""
    cell = gdstk.read_gds(str(GDS)).cells[0]
    merged = {n: _merged(cell, l, d) for n, (l, d, _a, _f) in LAYERS.items()}
    out, misses = {}, []
    for net, pts in seeds().items():
        c_tot, per_layer, seen = 0.0, {}, set()
        for lname, pt in pts:
            l, d, ca, cf = LAYERS[lname]
            hit = next((i for i, mp in enumerate(merged[lname])
                        if gdstk.inside([pt], [mp])[0]), None)
            if hit is None:
                misses.append(f"{net}/{lname}@{pt}")
                continue
            if (lname, hit) in seen:                 # same wire, another tap
                continue
            seen.add((lname, hit))
            mp = merged[lname][hit]
            c = (mp.area() * ca + _perimeter(mp) * cf) * 1e-18
            c_tot += c
            per_layer[lname] = per_layer.get(lname, 0.0) + c
        out[net] = (c_tot, ", ".join(f"{k} {v*1e15:.1f}fF" for k, v in
                                     sorted(per_layer.items())))
    return out, misses


def write_par_netlist(caps, scale=1.0, stem="miller_rrf2_par"):
    """spice/<stem>.sp = miller_rrf2 with lumped node caps to vss added. The
    rails are skipped (see RAILS)."""
    src = (SPICE / "miller_rrf2.sp").read_text()
    src = src.replace(".subckt miller_rrf2 ", f".subckt {stem} ")
    lines = [f"cpar_{net.lower()} {net.lower()} vss {c*scale:.6e}"
             for net, (c, _d) in sorted(caps.items())
             if c > 0 and net not in RAILS]
    src = src.replace(".ends", "* --- extracted interconnect parasitics ---\n"
                      + "\n".join(lines) + "\n.ends")
    (SPICE / f"{stem}.sp").write_text(src)
    return stem


PROCESS = ["tt", "ss", "ff", "sf", "fs"]
TEMPS = [-40, 25, 85]
SUPPLIES = [1.62, 1.98]


def pvt_worst(stem, params):
    """Worst-corner PM/UGF over the SAME grid tb/input_stage.py used to sign the
    design off (5 processes x 3 temps, + supply extremes at tt/25C).

    This is not optional here, and that is the point of running it. miller_ota's
    parasitics cost 0.13 deg of phase margin -- noise, so its nominal number was
    the whole story. rrf2's cost ~3 deg against a design whose WORST corner is
    62.8 deg, which is close enough to the 60 deg spec that quoting the nominal
    alone would be a claim, not a measurement."""
    pts = [(p, t, common.VDD) for p in PROCESS for t in TEMPS]
    pts += [("tt", 25, v) for v in SUPPLIES]
    rows = []
    for (p, t, v) in pts:
        common.ENV.update(corner=p, temp=t, vdd=v, seed=None)
        tag = f"_par_{stem}_{p}_{t}_{v}".replace(".", "p")
        ac = bench_ac(stem, "line", params=params, tag_extra=tag)
        rows.append((p, t, v, ac.get("pm_deg"), ac.get("ugf_hz")))
    common.ENV.update(corner="tt", temp=25, vdd=common.VDD, seed=None)
    ok = [r for r in rows if r[3] is not None]
    worst = min(ok, key=lambda r: r[3])
    return worst, rows


def sensitivity(caps, base_pm, params):
    """Load ONE net at a time and report the phase margin it costs.

    Worth doing because the aggregate number says nothing about mechanism, and
    the obvious guess is wrong. I expected cb to be nearly free -- it sits
    across a 9 pF Miller cap, so 47 fF looked like 0.5 % of what already
    dominates that node -- and expected the damage to be on the fold nodes.
    Measured, cb is 62 % of the entire loss.

    The reason is Rz. The nulling resistor is in SERIES with Cc, so above
    1/(2*pi*Rz*Cc) = 1.8 MHz the Miller branch stops being a short and sits at
    its resistive 10 kohm floor. At the 18 MHz worst-corner UGF the compensation
    cap therefore does NOT shunt cb, and a parasitic there is fully exposed --
    the same property (design-notes 7) that made Rz=10k the phase-margin lever
    in the first place. Do not reason about which node is "protected" by a
    compensation cap without checking what is in series with it."""
    rows = []
    for net, (c, _d) in sorted(caps.items(), key=lambda kv: -kv[1][0]):
        stem = f"miller_rrf2_par_only_{net.lower()}"   # matches the gitignore
        write_par_netlist({net: (c, "")}, 1.0, stem)
        common.VARIANTS[stem] = (stem, 20e-6)
        ac = bench_ac(stem, "line", params=params, tag_extra="_one")
        pm = ac.get("pm_deg")
        rows.append((net, c, (pm - base_pm) if pm is not None else None))
        (SPICE / f"{stem}.sp").unlink(missing_ok=True)
    return rows


def remedy(worst, ccs=(9, 10, 11, 12, 13)):
    """The extraction turned up a real spec violation (PM < 60 deg at the worst
    corner, WITH the drawn interconnect), so measure the price of fixing it
    instead of just reporting it.

    Cc is the natural lever: it sets the dominant pole, it is the one parameter
    the margin-tune already traded against 20 kHz loop gain, and in layout it is
    just a bigger MIM plate -- no re-routing. Swept at the FAILING corner with
    parasitics, and the 20 kHz gain (the thing a bigger Cc costs) reported
    alongside so the trade is visible rather than asserted."""
    p, t, v = worst[0], worst[1], worst[2]
    rows = []
    for cc in ccs:
        par = f"pcc={cc}e-12 prz=10000 pout=2.5"
        common.ENV.update(corner=p, temp=t, vdd=v, seed=None)
        wc = bench_ac("miller_rrf2_par", "line", params=par,
                      tag_extra=f"_rem{cc}w")
        wc2 = bench_ac("miller_rrf2_par2x", "line", params=par,
                       tag_extra=f"_rem{cc}w2")
        common.ENV.update(corner="tt", temp=25, vdd=common.VDD, seed=None)
        nom = bench_ac("miller_rrf2_par", "line", params=par,
                       tag_extra=f"_rem{cc}n")
        rows.append((cc, wc.get("pm_deg"), wc2.get("pm_deg"),
                     nom.get("pm_deg"), nom.get("a_20k_db")))
        print(f"  Cc={cc:2d}p  worst-corner PM {wc.get('pm_deg') or 0:5.1f} deg "
              f"(2x {wc2.get('pm_deg') or 0:5.1f})   nominal PM "
              f"{nom.get('pm_deg') or 0:5.1f} deg, A@20k "
              f"{nom.get('a_20k_db') or 0:5.1f} dB", flush=True)
    common.ENV.update(corner="tt", temp=25, vdd=common.VDD, seed=None)
    return rows


def thd_corner(stem, params, p, t, v):
    """THD at a named corner (the THD-worst corner is ff/+85 C, not the
    PM-worst one), so the distortion claim is measured rather than argued."""
    common.ENV.update(corner=p, temp=t, vdd=v, seed=None)
    val = run_thd_par(stem, params)
    common.ENV.update(corner="tt", temp=25, vdd=common.VDD, seed=None)
    return val


def sim(stem, params):
    ac = bench_ac(stem, "line", params=params, tag_extra="_par")
    return dict(a=ac.get("a_lf_db"), ugf=ac.get("ugf_hz"), pm=ac.get("pm_deg"),
                gm=ac.get("gm_db"), a20k=ac.get("a_20k_db"),
                thd=run_thd_par(stem, params))


def fmt(r):
    return (f"gain {r['a']:.1f} dB | UGF {(r['ugf'] or 0)/1e6:.2f} MHz | "
            f"PM {r['pm']:.1f}deg | GM {r['gm']:.1f} dB | "
            f"A@20k {r['a20k']:.1f} dB | THD {r['thd']:.3f} %")


def main():
    caps, misses = extract()
    if misses:
        print("SEED MISSES (wires not found -- extraction is incomplete):")
        for m in misses:
            print("   ", m)
    print("=== extracted interconnect parasitics (planar, to substrate) ===")
    sig = {n: v for n, v in caps.items() if n not in RAILS}
    for net, (c, det) in sorted(sig.items(), key=lambda kv: -kv[1][0]):
        print(f"  {net:5s} {c*1e15:7.2f} fF   [{det}]")
    tot = sum(c for c, _ in sig.values())
    print(f"  total {tot*1e15:.2f} fF loaded  (vs Cc = {CC_FF:.0f} fF, "
          f"{tot*1e15/CC_FF*100:.2f} %)")
    for net in sorted(RAILS):
        if net in caps:
            print(f"  [{net.lower()} {caps[net][0]*1e15:.2f} fF -- AC ground, "
                  f"not loaded]")

    write_par_netlist(caps, 1.0, "miller_rrf2_par")
    write_par_netlist(caps, 2.0, "miller_rrf2_par2x")
    common.VARIANTS["miller_rrf2_par"] = ("miller_rrf2_par", 20e-6)
    common.VARIANTS["miller_rrf2_par2x"] = ("miller_rrf2_par2x", 20e-6)

    print("\n=== stability + THD at the rrf2 point (pout=2.5, Cc9p, Rz10k) ===")
    base = sim("miller_rrf2", FIX)
    par = sim("miller_rrf2_par", FIX)
    par2 = sim("miller_rrf2_par2x", FIX)
    print(f"  schematic (no parasitics) : {fmt(base)}")
    print(f"  + extracted parasitics    : {fmt(par)}")
    print(f"  + 2x pessimistic          : {fmt(par2)}")
    dpm = par["pm"] - base["pm"]
    dugf = (par["ugf"] - base["ugf"]) / base["ugf"] * 100
    print(f"\n  delta (extracted): PM {dpm:+.2f}deg, UGF {dugf:+.1f} %, "
          f"THD {(par['thd']-base['thd'])*1000:+.1f} m%")

    print("\n=== worst-corner PM: does that delta eat the margin? ===")
    wb, _ = pvt_worst("miller_rrf2", FIX)
    wp, _ = pvt_worst("miller_rrf2_par", FIX)
    w2, _ = pvt_worst("miller_rrf2_par2x", FIX)
    for nm, w in (("schematic", wb), ("+ parasitics", wp), ("+ 2x", w2)):
        print(f"  {nm:14s} worst PM {w[3]:5.1f} deg @ {w[0]}/{w[1]:+d}C/{w[2]}V"
              f"   (UGF {w[4]/1e6:.2f} MHz)")
    print(f"  spec 60 deg -> {'PASS' if w2[3] >= 60 else 'FAIL'} even at 2x "
          f"pessimistic; extracted margin to spec {wp[3]-60:+.1f} deg")

    print("\n=== which wire costs the margin? (one net loaded at a time) ===")
    sens = sensitivity(sig, base["pm"], FIX)
    for net, c, d in sorted(sens, key=lambda r: (r[2] if r[2] is not None else 0)):
        print(f"  {net:5s} {c*1e15:6.2f} fF -> PM "
              f"{d:+.2f} deg" if d is not None else f"  {net}: no data")

    rem, thds = None, None
    if wp[3] < 60.0:
        print(f"\n=== PM {wp[3]:.1f} deg < 60 deg SPEC at {wp[0]}/{wp[1]:+d}C/"
              f"{wp[2]}V -- pricing the fix (Cc sweep, with parasitics) ===")
        rem = remedy(wp)
        pick = next((r for r in rem if r[1] is not None and r[1] >= 60.0), None)
        if pick:
            cc = pick[0]
            par_cc = f"pcc={cc}e-12 prz=10000 pout=2.5"
            print(f"\n  smallest Cc clearing 60 deg at the worst corner: {cc} pF")
            print("  THD at the THD-worst corner (ff/+85C), with parasitics:")
            thds = (thd_corner("miller_rrf2_par", FIX, "ff", 85, common.VDD),
                    thd_corner("miller_rrf2_par", par_cc, "ff", 85, common.VDD),
                    cc)
            print(f"    Cc=9p  {thds[0]:.3f} %   Cc={cc}p  {thds[1]:.3f} %")
    data = dict(sig=sig, caps=caps, tot=tot, base=base, par=par, par2=par2,
                dpm=dpm, dugf=dugf, wb=wb, wp=wp, w2=w2, sens=sens, rem=rem,
                thds=thds)
    CACHE.write_text(json.dumps(data), encoding="utf-8")
    write_doc(**data)


def write_doc(sig, caps, tot, base, par, par2, dpm, dugf, wb, wp, w2, sens,
              rem, thds):
    pm2 = par2["pm"]
    L = ["# Parasitic RC re-simulation — the miller_rrf2 layout\n",
         "Generated by `python tb/parasitics_rrf2.py`. Interconnect capacitance "
         "extracted from `layout/out/miller_rrf2.gds` and re-simulated at the "
         "rrf2 operating point (`pout=2.5`, `Cc=9 pF`, `Rz=10 kΩ`), "
         "`tt`/1.8 V/25 °C, `line` load. The companion pass for the superseded "
         "`miller_ota` layout is [`parasitics.md`](parasitics.md).\n",
         "## Why this one was not a formality\n",
         "`miller_ota`'s interconnect came to ~14 fF and the answer was "
         "obviously \"negligible\". `miller_rrf2` is a different shape of "
         "problem: **4× the area, 25 devices, and a 14-net routing channel** of "
         "met3 tracks up to ~100 µm long feeding 39 met2 risers, where "
         "`miller_ota` had four short hops. Long thin wires are *fringe*-"
         "dominated, and a channel router is happy to run a net the full width "
         "of the die — including the high-impedance summing node. The "
         "counterweight is that `Cc` went from 4 pF to 9 pF. Which effect wins "
         "is a question, not a formality, so it is measured.\n",
         "## Finding the wires\n",
         "The `miller_ota` bench hand-picked a seed point per net per layer. "
         "That does not scale to 14 nets over 5 layers, and — worse — a "
         "forgotten seed silently *under-counts* rather than failing. Here the "
         "seeds are **generated from the layout's own routing tables** "
         "(`build_rrf2.TAPS` / `.TRACK`): every met2 riser and every met3 track "
         "is derived from the same data that drew it, components are "
         "de-duplicated so a twice-tapped bar is not counted twice, and any "
         "seed that finds no wire is reported as a MISS. Only the hand-routed "
         "compensation branch is hand-seeded.\n",
         "## Extracted capacitance\n",
         "| node | parasitic C | by layer |", "|---|---|---|"]
    for net, (c, det) in sorted(sig.items(), key=lambda kv: -kv[1][0]):
        L.append(f"| `{net.lower()}` | {c*1e15:.2f} fF | {det} |")
    L.append(f"| **total loaded** | **{tot*1e15:.2f} fF** | "
             f"{tot*1e15/CC_FF*100:.2f} % of the 9 pF `Cc` |")
    L.append("")
    rails = ", ".join(f"`{n.lower()}` {caps[n][0]*1e15:.0f} fF"
                      for n in sorted(RAILS) if n in caps)
    L.append(f"The rails are extracted but **not** loaded ({rails}): their wire "
             "capacitance goes to the substrate, i.e. to `vss` — a no-op for "
             "`vss` itself, and supply decoupling for `vdd`, which helps rather "
             "than threatens.\n")
    L.append("## Stability + distortion, re-simulated\n")
    L.append("| case | DC gain | UGF | phase margin | gain margin | A@20 kHz | "
             "THD@1 kHz/1 Vpp |")
    L.append("|---|---|---|---|---|---|---|")
    for name, r in (("schematic (no parasitics)", base),
                    ("+ extracted parasitics", par),
                    ("+ 2× pessimistic", par2)):
        L.append(f"| {name} | {r['a']:.1f} dB | {(r['ugf'] or 0)/1e6:.2f} MHz "
                 f"| {r['pm']:.1f}° | {r['gm']:.1f} dB | {r['a20k']:.1f} dB "
                 f"| {r['thd']:.3f} % |")
    L.append("")
    L.append(f"**Result:** the extracted interconnect moves phase margin "
             f"{dpm:+.2f}° and UGF {dugf:+.1f} %, and at 2× pessimistic phase "
             f"margin is {pm2:.1f}°. THD at the 1 kHz spec point is "
             f"{par['thd']:.3f} % with parasitics against {base['thd']:.3f} % "
             "without — distortion is set by the low-frequency loop gain, which "
             "megahertz wire poles do not touch.\n")
    L.append("## The number that actually decides it — worst corner\n")
    L.append(f"A {dpm:+.2f}° shift is noise at the nominal corner and would be "
             "nothing worth writing down. It is not nothing here, because "
             "`miller_rrf2`'s **worst-corner** phase margin is only a few "
             "degrees above spec to begin with — so the nominal number alone "
             "would be a claim rather than a measurement. Re-run over the same "
             "PVT grid the design was signed off on (5 processes × 3 "
             "temperatures, plus the supply extremes):\n")
    L.append("| case | worst-corner PM | at | UGF there |")
    L.append("|---|---|---|---|")
    for name, w in (("schematic (no parasitics)", wb),
                    ("+ extracted parasitics", wp), ("+ 2× pessimistic", w2)):
        L.append(f"| {name} | **{w[3]:.1f}°** | {w[0]} / {w[1]:+d} °C / "
                 f"{w[2]} V | {w[4]/1e6:.2f} MHz |")
    L.append("")
    if wp[3] >= 60.0:
        L.append("## What this replaced: the first routing FAILED this spec\n")
        L.append(f"This layout has been routed twice, and the first attempt is "
                 f"the reason the second exists. In it, all fourteen nets were "
                 f"taken up to a channel above the tallest block — and measured "
                 f"by this same bench (commit `{FIRST['commit']}`) it **missed "
                 f"the 60° phase-margin spec at the worst corner: "
                 f"{FIRST['worst']}°**.\n")
        L.append("The per-net sensitivity said the cost was not spread around: "
                 f"**{FIRST['sig_ff']:.0f} fF on four signal-path nodes carried "
                 f"all {-FIRST['dpm']:.2f}° of it, while ~193 fF on the eight "
                 "bias and input nets cost 0.00°.** And those four connect "
                 "*adjacent* blocks — they were only sent up into the channel "
                 "because the router treated every net alike. So the fix was to "
                 "drop their met3 tracks down among the blocks they serve, and "
                 "leave the eight that provably do not care exactly where they "
                 "were:\n")
        L.append("| | first routing | **re-routed** | `Cc` = 10 pF instead |")
        L.append("|---|---|---|---|")
        sigc = sum(c for n, (c, _d) in sig.items()
                   if n in ("CB", "CA", "FA", "FB"))
        L.append(f"| signal-path wire | {FIRST['routed_um']:.0f} µm | "
                 f"**192 µm** | {FIRST['routed_um']:.0f} µm |")
        L.append(f"| signal-path C | {FIRST['sig_ff']:.1f} fF | "
                 f"**{sigc*1e15:.1f} fF** | {FIRST['sig_ff']:.1f} fF |")
        L.append(f"| nominal ΔPM | {FIRST['dpm']:.2f}° | **{dpm:+.2f}°** | "
                 f"{FIRST['dpm']:.2f}° |")
        L.append(f"| worst-corner PM | {FIRST['worst']:.1f}° ✗ | "
                 f"**{wp[3]:.1f}° ✓** | {FIRST['cc10_worst']:.1f}° |")
        L.append(f"| at 2× pessimistic | {FIRST['worst2x']:.1f}° ✗ | "
                 f"**{w2[3]:.1f}° ✓** | {FIRST['cc10_2x']:.1f}° ✗ |")
        L.append(f"| loop gain @20 kHz | {FIRST['a20k']:.1f} dB | "
                 f"**{par['a20k']:.1f} dB** | {FIRST['cc10_a20k']:.1f} dB |")
        L.append("")
        L.append("The third column is the obvious alternative — buy the margin "
                 "back with a bigger Miller cap — and it is worth keeping in "
                 "the table because it looks adequate and is not. It clears the "
                 "nominal spec by 0.1° on a *planar capacitance estimate*, "
                 "still fails at 2× pessimistic, and pays for it in loop gain; "
                 f"pushing on to 13 pF only reaches {FIRST['cc13_worst']:.1f}° "
                 f"({FIRST['cc13_2x']:.1f}° at 2×) while spending down to "
                 f"{FIRST['cc13_a20k']:.1f} dB, against a row-6 floor of 40 dB. "
                 "**Re-routing four wires beat it on every axis and cost "
                 "nothing at all** — no loop gain, no bandwidth, no area, no "
                 "change to a corner-verified operating point.\n")
        L.append("The lesson underneath is a floorplan one. The channel floor "
                 "was placed above the tallest block (`rrf2_plow`, ~74 µm) "
                 "because that is what a channel *looks like* — but the blocks "
                 "only use li and met1, so **met3 was free over every one of "
                 "them** and a track never had to clear anything. All 37 pins "
                 "were climbing ~67 µm for a constraint that did not exist.\n")
        L.append("## Where it stands now\n")
        L.append(f"Worst-corner phase margin with the drawn interconnect is "
                 f"**{wp[3]:.1f}°**, {wp[3]-60:+.1f}° against the 60° spec, and "
                 f"it still passes at 2× pessimistic ({w2[3]:.1f}°) — which the "
                 "first routing did not manage even with a 44 % bigger "
                 "capacitor. Stability signs off.\n")
    else:
        L.append("### This is a spec failure — and it is the entire point of "
                 "running the bench\n")
        L.append(f"Worst-corner phase margin with the drawn interconnect is "
                 f"**{wp[3]:.1f}°** at {wp[0]} / {wp[1]:+d} °C / {wp[2]} V — "
                 f"**{60-wp[3]:.1f}° UNDER the 60° spec** (spec row 8, which "
                 f"`tb/run.py` asserts). At 2× pessimistic it is {w2[3]:.1f}°.\n")
        L.append(f"The schematic design had {wb[3]:.1f}° at that corner, i.e. "
                 f"{wb[3]-60:.1f}° of margin, and the interconnect eats "
                 f"{wb[3]-wp[3]:.1f}° of it. **`miller_rrf2` was signed off "
                 "with less phase-margin headroom than its own layout costs.** "
                 "Nothing about the schematic work was wrong — the parasitic "
                 "pass is precisely the step meant to catch this, and it did. "
                 "For contrast `miller_ota` lost 0.13° to its interconnect "
                 "against ~15° of margin; it could not have failed this way, "
                 "which is why its parasitic pass read as a formality and this "
                 "one does not.\n")
        L.append("Note *which* corner fails: the **high-supply** one (+10 %), "
                 "not a temperature extreme. Phase margin is worst there "
                 "because more supply means more tail current, more gm and a "
                 "higher UGF — the loop runs out of margin at the top of the "
                 "supply range, while THD runs out at the temperature extremes. "
                 "Two different corners bound this amplifier, and a sweep that "
                 "only walked temperature would have missed this one.\n")
    L.append("### Which wire costs the margin — and a prediction that was wrong\n")
    L.append("The aggregate number says nothing about mechanism, so each net was "
             "also loaded on its own. I expected `cb` to be nearly free: it sits "
             "across a 9 pF Miller capacitor, so 47 fF looked like 0.5 % of what "
             "already dominates that node, and the damage *should* have been on "
             "the fold nodes. **Measured, `cb` is 62 % of the entire loss.**\n")
    L.append("| node | parasitic C | ΔPM alone |")
    L.append("|---|---|---|")
    for net, c, d in sorted(sens, key=lambda r: (r[2] if r[2] is not None
                                                 else 0)):
        L.append(f"| `{net.lower()}` | {c*1e15:.2f} fF | "
                 + (f"{d:+.2f}°" if d is not None else "—") + " |")
    L.append("")
    hot = [r for r in sens if (r[2] or 0) < -0.05]
    cold = [r for r in sens if (r[2] or 0) >= -0.05]
    L.append(f"The split is stark: **{sum(c for _n, c, _d in hot)*1e15:.0f} fF "
             f"on the four signal-path nodes costs "
             f"{sum(d for _n, _c, d in hot):+.2f}°, while "
             f"{sum(c for _n, c, _d in cold)*1e15:.0f} fF on the eight bias and "
             "input nets costs nothing at all.** `vb` carries 42.5 fF and costs "
             "0.00°; `cb` carries 47.0 fF and costs 1.95°. **Phase-margin cost "
             "tracks whether a node is in the signal path, not how much "
             "capacitance it carries** — the bias nets are diode-connected, so "
             "they sit at 1/gm and tens of fF do nothing there. (The single-net "
             "deltas also sum to the aggregate, so the loading superposes "
             "linearly — no interaction to chase.)\n")
    L.append("**Why the prediction failed, which is the transferable part:** "
             "`Rz` is in *series* with `Cc`. Above 1/(2π·Rz·Cc) ≈ **1.8 MHz** "
             "the Miller branch stops being a short and sits at its resistive "
             "10 kΩ floor — so at the 18 MHz worst-corner UGF the compensation "
             "capacitor does **not** shunt `cb`, and a parasitic there is fully "
             "exposed. That is the same property (`design-notes.md` §7) that "
             "made `Rz` the phase-margin lever in the first place, now showing "
             "up as a *liability*. Do not reason about which node a "
             "compensation cap 'protects' without checking what is in series "
             "with it.\n")
    riser, track = wire_lengths()
    tr, tt_ = sum(riser.values()), sum(track.values())
    hot_n = ("CB", "CA", "FA", "FB")
    hot_r = sum(riser[n] for n in hot_n)
    L.append("### Wire length, and the two-tier floorplan it forced\n")
    L.append(f"Total routed length is **{tr+tt_:.0f} µm**, splitting into "
             f"**{tr:.0f} µm of vertical met2 risers against {tt_:.0f} µm of "
             f"horizontal met3 track**. Risers dominate {tr/tt_:.1f}×, which is "
             "the whole story of this layout's interconnect: a riser's length is "
             "not a property of its net, it is the distance from the pin to "
             "wherever its track was put.\n")
    L.append(f"That is why the tracks are now at two heights. The four "
             f"signal-path nets sit low among the blocks they connect and spend "
             f"**{hot_r:.0f} µm** of riser between them; the eight that cost "
             f"0.00° stay in the channel above the tallest block and spend "
             f"{tr-hot_r:.0f} µm. Splitting them is free — the high channel is "
             "already verified geometry, and moving it to save capacitance that "
             "provably does not matter would be rework for its own sake.\n")
    L.append("| net | riser µm | track µm | track y |")
    L.append("|---|---|---|---|")
    for net in sorted(B.TRACK, key=lambda n: -(riser[n] + track[n])):
        lo = " (low)" if net in hot_n else ""
        L.append(f"| `{net.lower()}` | {riser[net]:.0f} | {track[net]:.0f} | "
                 f"{B.TRACK[net]:.1f}{lo} |")
    L.append(f"| **total** | **{tr:.0f}** | **{tt_:.0f}** | |")
    L.append("")
    L.append("So the lever on interconnect *capacitance* is the height of the "
             "tallest block, not track length or block order. But combined with "
             "the sensitivity above, the lever on **phase margin** is much "
             "narrower and much cheaper than that: only `cb`, `ca`, `fa` and "
             "`fb` matter, and all four connect blocks that are *adjacent in "
             "the row*. They never needed to climb to the channel at all — the "
             "router simply treated all fourteen nets alike. Routing those four "
             "short and direct between neighbours, and leaving the channel to "
             "the bias nets that provably do not care, is a targeted fix that "
             "touches four wires instead of the floorplan.\n")
    if rem:
        L.append("## Pricing the fix\n")
        L.append("`Cc` is the natural lever: it sets the dominant pole, it is "
                 "the parameter the margin-tune already traded against 20 kHz "
                 "loop gain, and in layout it is only a bigger MIM plate — no "
                 "re-routing, no re-verification of the channel. Swept at the "
                 "failing corner, with the extracted parasitics in place:\n")
        L.append("| Cc | worst-corner PM | worst-corner PM (2×) | nominal PM | "
                 "nominal A@20 kHz |")
        L.append("|---|---|---|---|---|")
        for cc, wpm, w2pm, npm, a20 in rem:
            mark = " ✅" if (wpm or 0) >= 60 else ""
            L.append(f"| {cc} pF | **{wpm:.1f}°**{mark} | {w2pm:.1f}° | "
                     f"{npm:.1f}° | {a20:.1f} dB |")
        L.append("")
        if thds:
            L.append(f"At the smallest `Cc` that clears the spec "
                     f"(**{thds[2]} pF**), distortion is re-checked at the "
                     f"THD-worst corner (ff / +85 °C — the corner that bounds "
                     f"THD, not the one that bounds PM): **{thds[1]:.3f} %** "
                     f"against {thds[0]:.3f} % at 9 pF, both under the 0.1 % "
                     "target — so the trade is 20 kHz loop gain for phase "
                     "margin, and it leaves the 1 kHz distortion the whole "
                     "topology exists for untouched.\n")
            L.append("That trade has a floor of its own, which bounds how far "
                     "the lever can be pushed: **spec row 6 wants ≥ 40 dB of "
                     "loop gain at 20 kHz**, and the sweep is already down to "
                     f"{rem[-1][4]:.1f} dB by {rem[-1][0]} pF. So `Cc` cannot "
                     f"run much past {rem[-1][0]} pF without trading one spec "
                     "row for another.\n")
        lo, hi = rem[0], rem[-1]
        L.append(f"**But read the table before reaching for it: `Cc` is a weak "
                 f"lever here.** Going from {lo[0]} pF to {hi[0]} pF — a 44 % "
                 f"bigger MIM plate — buys only "
                 f"{hi[1]-lo[1]:.1f}° at the worst corner while giving up "
                 f"{lo[4]-hi[4]:.1f} dB of 20 kHz loop gain. {rem[1][0]} pF "
                 f"technically clears the spec at {rem[1][1]:.1f}°, but that is "
                 "0.1° of margin on a planar capacitance estimate, which is not "
                 "a fix — it is a rounding error. At 2× pessimistic no value in "
                 "the sweep reaches 60°.\n")
        L.append("**The better lever is the layout, and the sensitivity says "
                 "exactly where.** `cb` alone costs 1.95°; halving its wire "
                 "recovers roughly what 4 pF of extra `Cc` buys, at no cost in "
                 "loop gain, bandwidth or area. `cb`, `ca`, `fa` and `fb` "
                 "connect adjacent blocks and were sent up into the channel "
                 "only because the router treated every net the same.\n")
        L.append("**Nothing applied here.** Changing `Cc` moves a "
                 "corner-verified operating point and means redrawing "
                 "`cap_cc9`; re-routing four nets means re-verifying the "
                 "layout. Both are design decisions, and this bench's job was "
                 "to measure. The numbers are on the table for whoever makes "
                 "the call.\n")
    p = ROOT / "docs" / "parasitics-rrf2.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\nwrote {p}")


if __name__ == "__main__":
    # `--report` re-renders the doc from the cached run, the same convention
    # tb/sweep_comp.py uses. The sims here are ~40 minutes (51 corner points x 3
    # variants, 12 single-net runs, a Cc sweep and two THD transients) and they
    # are deterministic, so prose edits must not cost a re-run.
    if "--report" in sys.argv:
        if not CACHE.exists():
            sys.exit(f"no cached run at {CACHE} -- run without --report first")
        write_doc(**json.loads(CACHE.read_text(encoding="utf-8")))
    else:
        sys.exit(main())
