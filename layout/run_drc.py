"""KLayout DRC over the layout/out/*.gds, using the sky130A_mr.drc deck.

Invocation mirrors the stdcells flow (feol+beol+offgrid), parses the .lyrdb
in Python (an empty <items> tricked a shell count in the stdcells v1).

    python layout/build.py && python layout/run_drc.py
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

HOME = Path.home()
PDK = (HOME / ".ciel" / "ciel" / "sky130" / "versions" /
       "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7" / "sky130A")
KLAYOUT = HOME / "AppData" / "Roaming" / "KLayout" / "klayout_app.exe"
DECK = PDK / "libs.tech" / "klayout" / "drc" / "sky130A_mr.drc"
OUT = Path(__file__).resolve().parent / "out"


def run_drc(gds):
    gds = Path(gds)
    report = OUT / (gds.stem + "_drc.lyrdb")
    cp = subprocess.run(
        [str(KLAYOUT), "-b", "-r", str(DECK),
         "-rd", f"input={gds}", "-rd", f"report={report}",
         "-rd", "feol=true", "-rd", "beol=true", "-rd", "offgrid=true"],
        capture_output=True, text=True, timeout=900)
    if not report.exists():
        print(f"{gds.name}: DRC RUN FAILED")
        print(cp.stdout[-1500:])
        print(cp.stderr[-500:])
        return -1
    items = ET.parse(report).getroot().findall(".//item")
    cats = Counter(i.findtext("category", "").strip("'") for i in items)
    if items:
        det = ", ".join(f"{c}:{n}" for c, n in cats.most_common())
        print(f"{gds.name}: {len(items)} violations  ({det})")
        for i in items[:14]:
            cat = i.findtext("category", "").strip("'")
            val = (i.findtext(".//value") or "").strip()
            print(f"    {cat}: {val}")
    else:
        print(f"{gds.name}: CLEAN")
    return len(items)


if __name__ == "__main__":
    tot = 0
    gdss = [Path(a) for a in sys.argv[1:]] or sorted(OUT.glob("*.gds"))
    for g in gdss:
        tot += max(0, run_drc(g))
    sys.exit(1 if tot else 0)
