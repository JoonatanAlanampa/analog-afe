"""Whole-amp extraction check for miller_ota.

The assembled amplifier is fully routed but cannot be LVS-*compared* against a
hand-written reference: its passives (the poly resistor and the MIM cap) don't
pair through the deck's SPICE reader (see run_passive_extract.py). So this
verifies the wiring by *extraction* instead -- and that turns out to be a strong
check, because KLayout tags every extracted net with all the labels on it. A net
that comes out named "N2|P|n2" is proof that the out_stage gate (N2), the
resistor end (P) and the top-level n2 wire are one electrical node.

It asserts (a) the device set -- 5 NMOS + 3 PMOS + 1 res + 1 cap = the ten
devices of miller_ota.sp -- and (b) that the four signal nets merge the labels
they must: n2 (stage-1 out = xm5 gate = Rz.P), vout (output = Cc top plate), nz
(Rz.M = Cc bottom plate) and the shared vb.

    python layout/run_amp_extract.py

POLARITY: the feedback sign now matches miller_ota.sp's inverting convention --
the input device with gate VINN drains to n1 (the diode/mirror side), the VINP
device drives n2 (the stage-1 output into stage 2). This is asserted below
(getting it backwards is positive feedback and a latched output, a silent
failure worth a regression check).
"""
import re
import subprocess
import sys

import run_lvs as L

DEVICES = {"nfet_01v8": 5, "pfet_01v8": 3, "res_xhigh_po": 1, "cap_mim": 1}
NETS = {  # display name -> labels that must ALL land on one extracted net
    "n2   (stage-1 out = xm5 gate = Rz.P)": {"N2", "P", "n2"},
    "vout (output = Cc top plate)":         {"P2", "VOUT"},
    "nz   (Rz.M = Cc bottom plate)":        {"M", "P1", "nz"},
    "vb   (bias diode = tail = sink gate)": {"VB", "vb"},
    "vss  (rail = substrate body tie)":     {"VSS", "vss_tap"},
}


def main():
    gds = L.OUT / "miller_ota.gds"
    sch = L.LVS / "miller_ota_stub.spice"
    sch.write_text(".subckt miller_ota vinp vinn vout vb vdd vss\n.ends\n")
    ext = L.LVS / "miller_ota_ext.cir"
    if ext.exists():
        ext.unlink()
    cmd = [str(L.KLAYOUT), "-b", "-r", str(L.DECK),
           "-rd", f"input={gds}", "-rd", f"report={L.LVS / 'miller_ota.lvsdb'}",
           "-rd", f"schematic={sch}", "-rd", f"target_netlist={ext}",
           "-rd", "thr=4", "-rd", "run_mode=deep", "-rd", "scale=false",
           "-rd", "spice_net_names=true"]
    subprocess.run(cmd, capture_output=True, text=True, cwd=L.LVS, timeout=600)
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
        print(f"  net {name}: {'OK' if hit else 'FAIL'}")

    # body ties: every transistor bulk (the 4th terminal) sits on its rail
    joined = re.sub(r"\\\s*\r?\n", " ", txt).splitlines()
    pb = [ln.split()[4] for ln in joined if "pfet_01v8" in ln and ln[:1] == "M"]
    nb = [ln.split()[4] for ln in joined if "nfet_01v8" in ln and ln[:1] == "M"]
    bok = (len(pb) == 3 and all("VDD" in b for b in pb) and
           len(nb) == 5 and all("VSS" in b for b in nb))
    ok &= bok
    print(f"  bodies (PMOS bulk->VDD, NMOS bulk->VSS): "
          f"{'OK' if bok else 'FAIL ' + str(pb) + str(nb)}")

    # feedback sign: the W=40 input pair. VINN-gate device must reach n1 (diode
    # side), VINP-gate device must reach n2 (stage-1 out) -- miller_ota.sp's
    # inverting convention. (KLayout may swap S/D, so check all D/G/S/B nets.)
    inp = [ln.split() for ln in joined
           if "nfet_01v8" in ln and " W=40" in ln and ln[:1] == "M"]

    def touches(dev, key):
        return any(key in t for t in dev[1:5])
    pol = (len(inp) == 2 and
           any(touches(d, "VINN") and touches(d, "N1") for d in inp) and
           any(touches(d, "VINP") and touches(d, "n2") for d in inp))
    ok &= pol
    print(f"  feedback sign (VINN->n1, VINP->n2): {'OK' if pol else 'FAIL'}")

    print(f"miller_ota: {'EXTRACT-OK -- 10 devices, key nets connected'
                         if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
