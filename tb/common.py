"""Shared paths and the ngspice runner.

Cribbed VERBATIM from stdcells/flow/common.py (same machine, same PDK
install, same ngspice binary) -- including the Windows 8.3 short-path
trick: ngspice's .lib parser splits the path on spaces, and this user's
home directory contains one. Every analog run inherits that fix.
"""
import re
import subprocess
from pathlib import Path

HOME = Path.home()
PDK = HOME / ".ciel" / "ciel" / "sky130" / "versions" / \
    "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7" / "sky130A"


def _short(p):
    """Windows 8.3 short path -- ngspice's .lib parser splits on spaces."""
    import ctypes
    buf = ctypes.create_unicode_buffer(512)
    if ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 512):
        return Path(buf.value)
    return Path(p)


MODELS = _short(PDK / "libs.tech" / "combined" / "sky130.lib.spice")
NGSPICE = Path(__file__).resolve().parents[2] / "devphys" / "tools" / \
    "Spice64" / "bin" / "ngspice_con.exe"

ROOT = Path(__file__).resolve().parents[1]
SPICE = ROOT / "spice"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

VDD = 1.8
VCM = 0.9           # input common mode = mid-rail (audio sits there)
TEMP = 25

# Candidate variants: name -> (subckt file/stem, external bias sink).
# ota_5t appears TWICE on purpose. At its natural 20 uA the single-stage
# OTA is not current-matched to the two-stage candidate (20 + 20 + 60 uA),
# and "the 5T loses" would then just be restating its bias. ota_5t_x5 runs
# the identical circuit at 100 uA so the comparison is about TOPOLOGY.
VARIANTS = {
    "ota_5t":     ("ota_5t",     20e-6),
    "ota_5t_x5":  ("ota_5t",    100e-6),
    "miller_ota": ("miller_ota", 20e-6),
}
TOPOLOGIES = list(VARIANTS)

# Load corners. The console audio path is the reason this block exists,
# so the loads are the console's, not textbook round numbers.
#
# COUPLING is part of the load spec, not a detail: an audio output sits at
# mid-rail and reaches the outside world through a series capacitor, so
# the resistive load is an AC load only. Modelling 10 kohm DC-coupled was
# the first thing tried here and it dragged the output to 0.196 V -- 20 uA
# into 10 kohm, exactly as Ohm predicts. That is a modelling error, not an
# amplifier finding, and the coupling cap is what removes it.
#
#   line   -- 10 kohm line input behind the board's 47 uF coupling cap.
#             PRIMARY SPEC.
#   pmodrc -- the cartridge Pmod's chain taken literally and DC-coupled,
#             because that is how the board is built: 120 + 33 ohm series
#             with 147 nF / 100 nF shunts and the 200 ohm volume trim to
#             ground. An op-amp dropped into the 74LVCE1G126's position
#             sees a ~353 ohm DC path. Expected to fail; the number it
#             fails by is the spec for either a board respin or an
#             output-side coupling cap.
#   phone  -- 32 ohm headphone through the 47 uF cap. Stretch corner;
#             failure here is the evidence that decides whether a
#             class-AB output stage is required.
CAC = 47e-6         # board's AC coupling capacitor
LOADS = {
    "open":   dict(desc="1 pF only -- INTRINSIC gain of the amplifier, no load"),
    "line":   dict(desc="10 kohm || 50 pF behind 47 uF coupling (line in) -- PRIMARY"),
    "pmodrc": dict(desc="cartridge-Pmod RC chain, DC-coupled (board as built, ~353 ohm DC)"),
    "phone":  dict(desc="32 ohm headphone behind 47 uF coupling (stretch)"),
}


def header():
    return (f'.lib "{MODELS}" tt\n'
            f'.temp {TEMP}\n'
            f'.option TEMP={TEMP}\n')


def subckt_of(variant):
    return VARIANTS[variant][0]


def ib_of(variant):
    return VARIANTS[variant][1]


def topo_include(variant):
    return (SPICE / f"{subckt_of(variant)}.sp").read_text()


def load_net(load, node="vout"):
    if load == "open":
        return f"cpar {node} 0 1p"
    if load == "line":
        return (f"cpar {node} 0 50p\n"
                f"cac {node} nl {CAC}\n"
                f"rl nl 0 10k")
    if load == "phone":
        return (f"cpar {node} 0 100p\n"
                f"cac {node} nl {CAC}\n"
                f"rl nl 0 32")
    # pmodrc: the board network, DC-coupled as drawn
    return (f"r1 {node} na 120\n"
            f"ca na 0 147n\n"
            f"r2 na nb 33\n"
            f"cb nb 0 100n\n"
            f"rtrim nb 0 200")


def run_ngspice(netlist_text, tag):
    """Run a netlist in batch mode, return stdout."""
    f = OUT / f"{tag}.sp"
    f.write_text(netlist_text)
    cp = subprocess.run([str(NGSPICE), "-b", str(f)], capture_output=True,
                        text=True, cwd=OUT, timeout=900)
    (OUT / f"{tag}.log").write_text(cp.stdout + "\n===STDERR===\n" + cp.stderr)
    return cp.stdout


def parse_meas(stdout):
    """Collect 'name = value' lines (print / echo output)."""
    vals = {}
    for m in re.finditer(r"^([\w.\[\]()@]+)\s*=\s*([-+0-9.eE]+)\s*$",
                         stdout, re.M):
        try:
            vals[m.group(1).lower()] = float(m.group(2))
        except ValueError:
            pass
    return vals


def read_wrdata(path, ncols):
    """Parse an ngspice `wrdata` file into ncols float columns.

    wrdata writes one x/y PAIR per vector, so a complex AC vector lands
    as (freq, real, freq, imag) -- the repeated x column is not a bug.
    """
    rows = []
    for line in Path(path).read_text().split("\n"):
        parts = line.split()
        if len(parts) < ncols:
            continue
        try:
            rows.append([float(p) for p in parts[:ncols]])
        except ValueError:
            continue
    return rows
