"""One-command regression for the layout leg: build every cell, DRC all of
them, and LVS the ones with a reference netlist. The `tb/run.py` of the layout
side -- one green run proves every device and sub-block is both manufacturable
(DRC) and the right circuit (LVS).

    python layout/verify.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sh(script):
    cp = subprocess.run([sys.executable, str(HERE / script)],
                        text=True, capture_output=True)
    print(cp.stdout, end="")
    if cp.returncode and cp.stderr:
        print(cp.stderr[-600:], end="")
    return cp.returncode


if __name__ == "__main__":
    print("=== build ===")
    sh("build.py")
    print("=== DRC (sky130A_mr) ===")
    drc = sh("run_drc.py")
    print("=== LVS (sky130.lvs) ===")
    lvs = sh("run_lvs.py")
    if drc or lvs:
        sys.exit("layout regression FAILED")
    print("\nLAYOUT REGRESSION CLEAN — all cells DRC-clean, all LVS matched")
