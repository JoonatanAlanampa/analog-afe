"""Extraction-based check for the poly resistor res_rz.

The sky130 KLayout deck extracts this precision resistor correctly as a
`sky130_fd_pr__res_xhigh_po_0p69` device, but as a 3-terminal `resistor_with_bulk`
while its SPICE reader reads `R` cards as only 2-terminal (there is no bulk-
resistor reader delegate, unlike the C-VPP path). So run_lvs.py's schematic
COMPARE cannot pair it. The extraction itself is the meaningful check for a
passive: it confirms the drawn geometry IS the intended PDK device AND measures
its value. This runs that extraction and asserts the class + resistance.

    python layout/run_res_extract.py
"""
import re
import subprocess
import sys

import run_lvs as L          # reuse its PDK/KLayout paths + patched deck

EXPECT_CLASS = "sky130_fd_pr__res_xhigh_po_0p69"
EXPECT_R, TOL = 10000.0, 0.02          # 10 kOhm target (Rz), 2% tolerance


def main():
    gds = L.OUT / "res_rz.gds"
    sch = L.LVS / "res_rz_stub.spice"
    sch.write_text(".subckt res_rz P M B\n.ends\n")    # stub; we read the extract
    ext = L.LVS / "res_rz_extracted.cir"
    if ext.exists():
        ext.unlink()
    cmd = [str(L.KLAYOUT), "-b", "-r", str(L.DECK),
           "-rd", f"input={gds}", "-rd", f"report={L.LVS / 'res_rz_ext.lvsdb'}",
           "-rd", f"schematic={sch}", "-rd", f"target_netlist={ext}",
           "-rd", "thr=4", "-rd", "run_mode=deep", "-rd", "scale=false"]
    subprocess.run(cmd, capture_output=True, text=True, cwd=L.LVS, timeout=600)
    txt = ext.read_text() if ext.exists() else ""
    m = re.search(re.escape(EXPECT_CLASS) + r"\s+R=([0-9.]+)", txt)
    ok = bool(m) and abs(float(m.group(1)) - EXPECT_R) <= EXPECT_R * TOL
    if m:
        print(f"res_rz: {'EXTRACT-OK' if ok else 'FAIL'} -- {EXPECT_CLASS} "
              f"R={float(m.group(1)):g}")
    else:
        print(f"res_rz: FAIL -- {EXPECT_CLASS} not found in extraction")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
