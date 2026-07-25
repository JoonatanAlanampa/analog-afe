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
    # PMOS: bulk is the nwell, tied to VDDN by the n-tap guard ring.
    "pfet_lvs": """.subckt pfet_lvs S G D VDDN
M0 D G S VDDN sky130_fd_pr__pfet_01v8 L=1u W=5u
.ends
""",
    # common-centroid differential pair: two W=10 (2x5 finger) NMOS, common
    # source (TAIL), gates VA/VB, drains OA/OB, shared bulk VNB.
    "cc_diff": """.subckt cc_diff VA VB OA OB TAIL VNB
MA OA VA TAIL VNB sky130_fd_pr__nfet_01v8 L=0.5u W=10u
MB OB VB TAIL VNB sky130_fd_pr__nfet_01v8 L=0.5u W=10u
.ends
""",
    # PMOS current mirror: xm3 diode-connected (gate=drain=N1), xm4 mirrors it.
    # Common gate N1, common source VDD, drains N1/VOUT. Floating nwell VNW.
    "pmos_mirror": """.subckt pmos_mirror N1 VOUT VDD VNW
M3 N1 N1 VDD VNW sky130_fd_pr__pfet_01v8 L=1u W=10u
M4 VOUT N1 VDD VNW sky130_fd_pr__pfet_01v8 L=1u W=10u
.ends
""",
    # NMOS current mirror: xmb diode sets VB, xm0 mirrors it to sink the tail.
    "tail_bias": """.subckt tail_bias VB TAIL VSS VNB
Mb VB VB VSS VNB sky130_fd_pr__nfet_01v8 L=1u W=10u
M0 TAIL VB VSS VNB sky130_fd_pr__nfet_01v8 L=1u W=10u
.ends
""",
    # NOTE: the passives res_rz (poly resistor) and cap_cc (MIM cap) are NOT
    # here -- they are extraction-verified instead (run_passive_extract.py). Both
    # EXTRACT correctly (res_xhigh_po_0p69 @ R=10000; cap_mim @ C=2e-13), but the
    # deck's SPICE reader delegate only builds properly *named* device classes
    # for the devices it handles explicitly (MOS, VPP caps, inductors). A poly
    # resistor is read as a 2-terminal `R` (no bulk-resistor path, while it is
    # extracted as 3-terminal resistor_with_bulk); a MIM cap falls through to a
    # generic `C` class (only VPP caps get the model name) and the delegate also
    # force-appends a default C=2e-16. So neither can be paired by a hand-written
    # reference. Extraction (device class + value) is the real check for a passive.
    # miller_ota stage 2: PMOS common-source (xm5) + NMOS current-sink (xm6)
    # sharing the output. PRODUCTION FULL-W (pout=2.5 THD fix): W=150 (m30).
    # Bulks are ports (VNB substrate, VNW well).
    "out_stage": """.subckt out_stage n2 vb vout vdd vss vnb vnw
M5 vout n2 vdd vnw sky130_fd_pr__pfet_01v8 L=0.5u W=150u
M6 vout vb vss vnb sky130_fd_pr__nfet_01v8 L=1u W=150u
.ends
""",
    # the whole 5T OTA: bias diode + tail + input pair + PMOS mirror load.
    # Internal nets n1/tail; bulks are ports (VNB substrate, VNW nwell).
    # PRODUCTION FULL-W matching miller_ota.sp: input pair W=40 (m8), mirror +
    # tail/bias W=20 (m4). Feedback-sign convention matches miller_ota.sp:
    # xm1 (gate=vinn) -> n1, xm2 (gate=vinp) -> vout(n2).
    "ota5t_core": """.subckt ota5t_core vinp vinn vout vb vdd vss vnb vnw
Mb vb vb vss vnb sky130_fd_pr__nfet_01v8 L=1u W=20u
M0 tail vb vss vnb sky130_fd_pr__nfet_01v8 L=1u W=20u
M1 n1 vinn tail vnb sky130_fd_pr__nfet_01v8 L=0.5u W=40u
M2 vout vinp tail vnb sky130_fd_pr__nfet_01v8 L=0.5u W=40u
M3 n1 n1 vdd vnw sky130_fd_pr__pfet_01v8 L=1u W=20u
M4 vout n1 vdd vnw sky130_fd_pr__pfet_01v8 L=1u W=20u
.ends
""",
    # ---- miller_rrf2 blocks (build_rrf2.py). Sizing straight off
    # spice/miller_rrf2.sp, where a device is w=5 m=N -> W = 5N um. ----------
    # NMOS high side: tail mirror (tail internal) + the input pair, whose drains
    # go to the FOLD nodes fa/fb instead of a mirror load -- that unpinning is
    # what removes miller_ota's 1.40 V ICMR wall.
    "rrf2_nin": """.subckt rrf2_nin vinp vinn fa fb vb vss vnb
Mb vb vb vss vnb sky130_fd_pr__nfet_01v8 L=1u W=20u
M0 tail vb vss vnb sky130_fd_pr__nfet_01v8 L=1u W=20u
M1 fa vinn tail vnb sky130_fd_pr__nfet_01v8 L=0.5u W=40u
M2 fb vinp tail vnb sky130_fd_pr__nfet_01v8 L=0.5u W=40u
.ends
""",
    # the self-biased cascode mirror: xm13/xm14 mirror, xm15/xm16 cascode over
    # it. Both reference devices are diode-connected (xm15 gate=drain=ca,
    # xm13 gate=drain=yref) -- that is what self-matches the actual folded
    # current; a wide-swing cascode with an independent reference collapsed.
    "rrf2_cmir": """.subckt rrf2_cmir ca cb vss vnb
M13 yref yref vss vnb sky130_fd_pr__nfet_01v8 L=0.5u W=20u
M14 cbm yref vss vnb sky130_fd_pr__nfet_01v8 L=0.5u W=20u
M15 ca ca yref vnb sky130_fd_pr__nfet_01v8 L=0.5u W=20u
M16 cb ca cbm vnb sky130_fd_pr__nfet_01v8 L=0.5u W=20u
.ends
""",
    # bias chain, split at pb/pc/vbp (which are top-level nets anyway)
    "rrf2_bias_n": """.subckt rrf2_bias_n vb pb pc vbp vss vnb
Mn1 pb vb vss vnb sky130_fd_pr__nfet_01v8 L=1u W=5u
Mn3 vbp vb vss vnb sky130_fd_pr__nfet_01v8 L=1u W=5u
Mn2 pc pc vss vnb sky130_fd_pr__nfet_01v8 L=1u W=20u
.ends
""",
    "rrf2_bias_p": """.subckt rrf2_bias_p pb pc vbp vdd vnw
Mp1 pb pb vdd vnw sky130_fd_pr__pfet_01v8 L=1u W=10u
Mp2 pc pb vdd vnw sky130_fd_pr__pfet_01v8 L=1u W=10u
Mp3 vbp vbp vdd vnw sky130_fd_pr__pfet_01v8 L=1u W=10u
.ends
""",
    # PMOS half of the fold: top sources into fa/fb, cascodes down to ca/cb.
    "rrf2_fold": """.subckt rrf2_fold pb pc fa fb ca cb vdd vnw
M9 fa pb vdd vnw sky130_fd_pr__pfet_01v8 L=1u W=30u
M10 fb pb vdd vnw sky130_fd_pr__pfet_01v8 L=1u W=30u
M11 ca pc fa vnw sky130_fd_pr__pfet_01v8 L=0.5u W=40u
M12 cb pc fb vnw sky130_fd_pr__pfet_01v8 L=0.5u W=40u
.ends
""",
    # the low-side path: PMOS tail + pair over an NMOS mirror load. Scaled 1.5x
    # vs the high side (W60/W60/W30) -- the margin tune that lifted the trough
    # gain and took the temperature corners under 0.1 %.
    "rrf2_plow": """.subckt rrf2_plow vbp vinp vinn cb vdd vss vnb vnw
Mp0 tailp vbp vdd vnw sky130_fd_pr__pfet_01v8 L=1u W=60u
Mp1 np vinn tailp vnw sky130_fd_pr__pfet_01v8 L=0.5u W=60u
Mp2 cb vinp tailp vnw sky130_fd_pr__pfet_01v8 L=0.5u W=60u
Mp3 np np vss vnb sky130_fd_pr__nfet_01v8 L=1u W=30u
Mp4 cb np vss vnb sky130_fd_pr__nfet_01v8 L=1u W=30u
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
