"""Extraction-based check for the leg's PASSIVE devices (the poly resistor Rz and
the MIM cap Cc).

Both extract correctly under the sky130 KLayout deck -- res_rz as a
`sky130_fd_pr__res_xhigh_po_0p69` at R=10000, cap_cc as a
`sky130_fd_pr__model__cap_mim` at C=2e-13 -- but neither can be paired by the
schematic COMPARE in run_lvs.py. The deck's SPICE reader delegate only builds
properly *named* device classes for the devices it handles explicitly (MOS, VPP
caps, inductors): a poly resistor is read as a 2-terminal `R` (it is extracted
as 3-terminal `resistor_with_bulk`), and a MIM cap falls through to a generic
`C` (only VPP caps get the model-named class, and the delegate force-appends a
default C=2e-16). Extraction is the meaningful check for a passive anyway: it
confirms the drawn geometry IS the intended PDK device AND measures its value.

    python layout/run_passive_extract.py
"""
import re
import subprocess
import sys

import run_lvs as L          # reuse its PDK/KLayout paths + patched deck

# (cell, device class, "<letter>=<value>" param, expected value, rel. tolerance)
PASSIVES = [
    ("res_rz", "sky130_fd_pr__res_xhigh_po_0p69", "R", 10000.0, 0.02),
    ("cap_cc", "sky130_fd_pr__model__cap_mim",    "C", 2e-13,   0.05),
]


def check(cell, cls, letter, expect, tol):
    gds = L.OUT / f"{cell}.gds"
    sch = L.LVS / f"{cell}_stub.spice"
    sch.write_text(f".subckt {cell} A B C\n.ends\n")     # stub; we read the extract
    ext = L.LVS / f"{cell}_extracted.cir"
    if ext.exists():
        ext.unlink()
    cmd = [str(L.KLAYOUT), "-b", "-r", str(L.DECK),
           "-rd", f"input={gds}", "-rd", f"report={L.LVS / (cell + '_ext.lvsdb')}",
           "-rd", f"schematic={sch}", "-rd", f"target_netlist={ext}",
           "-rd", "thr=4", "-rd", "run_mode=deep", "-rd", "scale=false"]
    subprocess.run(cmd, capture_output=True, text=True, cwd=L.LVS, timeout=600)
    txt = ext.read_text() if ext.exists() else ""
    m = re.search(re.escape(cls) + r"\s+" + letter + r"=([0-9.eE+-]+)", txt)
    if not m:
        print(f"{cell}: FAIL -- {cls} not found in extraction")
        return False
    val = float(m.group(1))
    ok = abs(val - expect) <= abs(expect) * tol
    print(f"{cell}: {'EXTRACT-OK' if ok else 'FAIL'} -- {cls} {letter}={val:g}")
    return ok


if __name__ == "__main__":
    bad = [c[0] for c in PASSIVES if not check(*c)]
    sys.exit(f"passive extract FAILED: {bad}" if bad else 0)
