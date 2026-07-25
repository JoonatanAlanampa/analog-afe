"""Whole-amp extraction check for miller_rrf2.

Same reason as run_amp_extract.py: the assembled amplifier carries a poly
resistor and a MIM cap, and neither pairs through the LVS deck's SPICE reader,
so the top level is verified by EXTRACTION rather than by schematic compare.
Every block below it IS compared (run_lvs.py), so what is left to prove is the
inter-block wiring -- which is exactly what extraction shows, because KLayout
names each extracted net with every label sitting on it.

This check is stronger than miller_ota's, deliberately. There, the merged nets
happened to carry distinct label texts ("N2|P|n2") so the name alone proved the
merge. Here five different blocks all call the summing node "CB", so a net named
"CB" would prove nothing -- it could be one block's pin, unconnected. So
build_rrf2.py drops a UNIQUE tag on every riser (cb_fold, cb_cmir, cb_plow,
cb_out) and this file asserts all of them land on ONE net. Every single
block-to-block connection in the amplifier is therefore individually checked:
14 nets, 39 tagged pins.

    python layout/run_rrf2_extract.py
"""
import re
import subprocess
import sys

import run_lvs as L

DEVICES = {"nfet_01v8": 14, "pfet_01v8": 11, "res_xhigh_po": 1, "cap_mim": 1}

# display name -> tags that must ALL land on one extracted net
NETS = {
    "vss  (rail + substrate tie)":
        {"vss_biasn", "vss_nin", "vss_cmir", "vss_plow", "vss_out", "vss_tap"},
    "vdd  (rail + all four nwell ties)":
        {"vdd_biasp", "vdd_fold", "vdd_plow", "vdd_out",
         "vdd_nwfold", "vdd_nwplow", "nw_biasp", "nw_out"},
    "vb   (master bias -> tail + stage-2 sink)":
        {"vb_bias", "vb_nin", "vb_out"},
    "pb   (fold top-source bias)":
        {"pb_biasn", "pb_biasp", "pb_fold"},
    "pc   (fold cascode bias)":
        {"pc_biasn", "pc_biasp", "pc_fold"},
    "vbp  (PMOS tail bias)":
        {"vbp_biasn", "vbp_biasp", "vbp_plow"},
    "fa   (fold node A: xm1 drain = xm9 drain = xm11 source)":
        {"fa_nin", "fa_fold"},
    "fb   (fold node B: xm2 drain = xm10 drain = xm12 source)":
        {"fb_nin", "fb_fold"},
    "ca   (cascode self-bias node)":
        {"ca_fold", "ca_cmir"},
    "cb   (THE summing node: fold + cascode + PMOS pair + stage 2 + Rz)":
        {"cb_fold", "cb_cmir", "cb_plow", "cb_out", "P"},
    "vinn (both input pairs)":
        {"vinn_nin", "vinn_plow"},
    "vinp (both input pairs)":
        {"vinp_nin", "vinp_plow"},
    "vout (output = Cc top plate)":
        {"VOUT", "P2", "vout"},
    "nz   (Rz.M = Cc bottom plate)":
        {"M", "P1", "nz"},
}


def main():
    gds = L.OUT / "miller_rrf2.gds"
    sch = L.LVS / "miller_rrf2_stub.spice"
    sch.write_text(".subckt miller_rrf2 vinp vinn vout vb vdd vss\n.ends\n")
    ext = L.LVS / "miller_rrf2_ext.cir"
    if ext.exists():
        ext.unlink()
    cmd = [str(L.KLAYOUT), "-b", "-r", str(L.DECK),
           "-rd", f"input={gds}", "-rd", f"report={L.LVS / 'miller_rrf2.lvsdb'}",
           "-rd", f"schematic={sch}", "-rd", f"target_netlist={ext}",
           "-rd", "thr=4", "-rd", "run_mode=deep", "-rd", "scale=false",
           "-rd", "spice_net_names=true"]
    subprocess.run(cmd, capture_output=True, text=True, cwd=L.LVS, timeout=1200)
    txt = ext.read_text() if ext.exists() else ""
    ok = bool(txt)

    for cls, n in DEVICES.items():
        got = len(re.findall(cls, txt))
        ok &= got == n
        print(f"  devices {cls:16s}: {got}/{n} {'OK' if got == n else 'FAIL'}")

    nets = [set(t.split('|')) for t in set(re.findall(r'[A-Za-z0-9_|]+', txt))
            if '|' in t]
    for name, req in NETS.items():
        hit = any(req <= s for s in nets)
        ok &= hit
        if not hit:                       # name the pin that did not join
            best = max(nets, key=lambda s: len(req & s), default=set())
            print(f"  net {name}: FAIL -- missing {sorted(req - best)}")
        else:
            print(f"  net {name}: OK")

    # Device cards wrap with SPICE '+' continuations, and here they always do:
    # every net name is the '|'-join of all its labels, and this layout gives
    # each pin its own tag, so the names are long. Un-wrap before parsing.
    joined = txt.replace("\n+ ", " ").splitlines()
    mos = [ln.split() for ln in joined if ln[:1] == "M"]
    pb = [d[4] for d in mos if "pfet_01v8" in " ".join(d)]
    nb = [d[4] for d in mos if "nfet_01v8" in " ".join(d)]
    bok = (len(pb) == 11 and all("VDD" in b or "vdd" in b for b in pb) and
           len(nb) == 14 and all("VSS" in b or "vss" in b for b in nb))
    ok &= bok
    print(f"  bodies (11 PMOS bulk->VDD, 14 NMOS bulk->VSS): "
          f"{'OK' if bok else 'FAIL ' + str(set(pb)) + str(set(nb))}")

    # Polarity, end to end. miller_rrf2 inverts through stage 2 exactly like
    # miller_ota, so VINP must be the device that drives the summing node cb and
    # VINN the one on the reference side -- in BOTH input pairs, since the whole
    # point of the topology is that they work in parallel. Getting either
    # backwards is positive feedback and a latched output: silent in DC, fatal.
    def touches(dev, key):
        return any(key in t for t in dev[1:5])

    npair = [d for d in mos if "nfet_01v8" in " ".join(d) and " W=40" in " ".join(d)]
    ppair = [d for d in mos if "pfet_01v8" in " ".join(d)
             and " W=60" in " ".join(d) and " L=0.5" in " ".join(d)]
    pol = (len(npair) == 2 and len(ppair) == 2 and
           any(touches(d, "vinn_nin") and touches(d, "fa_nin") for d in npair) and
           any(touches(d, "vinp_nin") and touches(d, "fb_nin") for d in npair) and
           any(touches(d, "vinp_plow") and touches(d, "cb_plow") for d in ppair) and
           any(touches(d, "vinn_plow") and not touches(d, "cb_plow")
               for d in ppair))
    ok &= pol
    print(f"  polarity (NMOS VINN->fa / VINP->fb, PMOS VINP->cb): "
          f"{'OK' if pol else 'FAIL'}")

    print(f"miller_rrf2: {'EXTRACT-OK -- 27 devices, all 14 nets connected'
                          if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
