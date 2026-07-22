"""KLayout LVS over the layout cells: extract vs a reference SPICE netlist.

Mirrors the stdcells run_lvs_all.py flow: the PDK's sky130.lvs deck, patched so
the SPICE reader's UPPERCASE device-class names equate to the lowercase
extracted ones (without it the comparator pairs nothing). Success = the deck
prints "Congratulations". DRC proves geometry; this proves the circuit.

    python layout/build.py && python layout/run_lvs.py
"""
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
PDK = (HOME / ".ciel" / "ciel" / "sky130" / "versions" /
       "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7" / "sky130A")
KLAYOUT = HOME / "AppData" / "Roaming" / "KLayout" / "klayout_app.exe"
DECK_SRC = PDK / "libs.tech" / "klayout" / "lvs" / "sky130.lvs"
OUT = Path(__file__).resolve().parent / "out"
LVS = OUT / "lvs"
LVS.mkdir(parents=True, exist_ok=True)

_EQ = ('same_device_classes("sky130_fd_pr__nfet_01v8", "SKY130_FD_PR__NFET_01V8")\n'
       'same_device_classes("sky130_fd_pr__pfet_01v8", "SKY130_FD_PR__PFET_01V8")\n')
DECK = LVS / "sky130_patched.lvs"
DECK.write_text(DECK_SRC.read_text().replace("#=== COMPARE ===",
                                             _EQ + "#=== COMPARE ==="))

# reference netlists. Unit suffixes are MANDATORY (a bare number is metres, the
# reader converts to 1e6 um and nothing pairs). M cards, not X. nfet bulk = B.
REF = {
    "nfet_lvs": """.subckt nfet_lvs S G D B
M0 D G S B sky130_fd_pr__nfet_01v8 L=0.5u W=5u
.ends
""",
    # common-centroid differential pair: two W=10 (2x5 finger) NMOS, common
    # source (TAIL), gates VA/VB, drains OA/OB, shared bulk VNB.
    "cc_diff": """.subckt cc_diff VA VB OA OB TAIL VNB
MA OA VA TAIL VNB sky130_fd_pr__nfet_01v8 L=0.5u W=10u
MB OB VB TAIL VNB sky130_fd_pr__nfet_01v8 L=0.5u W=10u
.ends
""",
}


def run_lvs(name):
    gds = OUT / f"{name}.gds"
    ref = LVS / f"{name}.spice"
    ref.write_text(REF[name])
    cmd = [str(KLAYOUT), "-b", "-r", str(DECK),
           "-rd", f"input={gds}",
           "-rd", f"report={LVS / (name + '.lvsdb')}",
           "-rd", f"schematic={ref}",
           "-rd", f"target_netlist={LVS / (name + '_extracted.cir')}",
           "-rd", "thr=4", "-rd", "run_mode=deep",
           "-rd", "spice_net_names=false", "-rd", "spice_comments=false",
           "-rd", "scale=false", "-rd", "verbose=false",
           "-rd", "schematic_simplify=false", "-rd", "net_only=false",
           "-rd", "top_lvl_pins=false", "-rd", "combine=false",
           "-rd", "purge=false", "-rd", "purge_nets=false"]
    cp = subprocess.run(cmd, capture_output=True, text=True, cwd=LVS, timeout=600)
    log = cp.stdout + cp.stderr
    (LVS / f"{name}.log").write_text(log)
    if re.search(r"Congratulations", log):
        r = "MATCH"
    elif re.search(r"don'?t match|MISMATCH|ERROR", log, re.I):
        r = "MISMATCH"
    else:
        r = "UNKNOWN"
    print(f"{name}: {r}")
    return r


if __name__ == "__main__":
    bad = [n for n in (sys.argv[1:] or REF) if run_lvs(n) != "MATCH"]
    if bad:
        print(f"see {LVS}/*.log")
        sys.exit(f"LVS not matched: {bad}")
    print("ALL LVS MATCH")
