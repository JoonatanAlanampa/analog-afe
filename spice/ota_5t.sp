* -----------------------------------------------------------------------
* ota_5t -- five-transistor OTA, NMOS input pair, PMOS mirror load.
* sky130 1v8 devices, hand-written (no generator, no PCell library).
*
* Pins:  vinp vinn vout vb vdd vss
*   vb   = bias node. An EXTERNAL source pushing IB (20 uA nominal) INTO
*          vb programs the tail through the diode-connected xmb. A real
*          bias generator (beta-multiplier / constant-gm) is a later
*          phase -- keeping it external here means every number is quoted
*          against a KNOWN current, not an unverified bias cell.
*
* WHY AN NMOS PAIR (this was measured, not assumed):
*   The first version used a PMOS pair, the textbook choice for 1/f noise.
*   It does not work here. Audio sits at mid-rail, so a unity-gain buffer
*   forces the input common mode to 0.9 V, and a PMOS pair puts its tail
*   node at VCM + |Vgs| = 0.9 + 0.88 = 1.78 V. On a 1.8 V rail that
*   leaves the tail source 19 mV: simulated in triode, delivering 3.87 uA
*   of a requested 20 uA. sky130's |Vth| ~0.9 V is simply too large a
*   fraction of this rail. The NMOS pair puts the tail at VCM - Vgs ~
*   0.3 V and has room. Cost: the noisier device in the flicker band,
*   which is why input-referred noise is an explicit phase-2 bench.
*
* Sizing rationale:
*   L = 0.5 um on the signal devices (not 0.15): audio wants gain and
*       matching, not speed. L = 1 um on every current source -- output
*       resistance sets both the DC gain and the mirror accuracy.
*   Widths are m = parallel fingers of w = 5 um, so the netlist is
*       topologically what a layout would draw (the stdcells phase-6
*       lesson: one entry per physical finger, LVS needs no overrides).
*
* Polarity: xm2 (gate = vinn) drains directly to vout, so vinn is the
* inverting input. A second stage would flip this -- see miller_ota.sp.
* -----------------------------------------------------------------------
.subckt ota_5t vinp vinn vout vb vdd vss

* --- bias diode: external source into vb sets the mirror voltage -------
xmb   vb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* --- tail current sink (1:1 with xmb) ----------------------------------
xm0   tail vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* --- input differential pair ------------------------------------------
xm1   n1   vinp tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm2   vout vinn tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8

* --- PMOS mirror load (n1 is the diode side) ---------------------------
xm3   n1   n1   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=4
xm4   vout n1   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=4

.ends
