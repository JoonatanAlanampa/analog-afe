* -----------------------------------------------------------------------
* miller_rrf2 -- folded rail-to-rail input with a WIDE-SWING CASCODED summing
* node.  The path to THD < 0.1 % at full 1 Vpp.
*
* miller_rrf removed the input ICMR walls but left a ~0.16 % h2 floor: the
* LOW-side gain deficit. At low V_CM the NMOS tail starves, so the folded-NMOS
* path floods its (simple) mirror and runs up in current -> its output
* impedance at the shared node cb drops -> it SHUNTS cb, dragging the trough to
* 54 dB (vs a 72 dB peak). That asymmetry is the residual distortion.
*
* FIX: cascode the folded-NMOS mirror with a WIDE-SWING bias, so its output
* impedance stays HIGH even when the current runs up -> it no longer shunts cb.
* Wide-swing (not a plain cascode) because cb must sit ~0.73 V to bias stage 2,
* and a plain two-high NMOS stack needs ~0.75 V+; wide-swing lets both devices
* stay saturated down to ~2*Vov ~ 0.3 V. The cascode gate ncb = Vth + 2*Vov is
* made by a diode-connected NMOS of 1/4 the mirror width (the classic W/4
* trick) carrying the mirror current.
*
* Everything else = miller_rrf: folded-cascode NMOS (high side) + PMOS pair
* with NMOS-mirror load (low side), summed at cb; class-A output; Miller comp.
*
* Pins: vinp vinn vout vb vdd vss.  Params: pout, pcc, prz.
* -----------------------------------------------------------------------
.subckt miller_rrf2 vinp vinn vout vb vdd vss pcc=9p prz=10k pout=1

* --- master bias diode: external source into vb sets 20 uA --------------
xmb   vb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* === bias references ==================================================
xbn1  pb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=1
xbp1  pb   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2
xbp2  pc   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2
xbn2  pc   pc   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xbn3  vbp  vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=1
xbp3  vbp  vbp  vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2
* === HIGH-side path: folded-cascode NMOS, self-biased CASCODE mirror -> cb =
xm0   tail vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xm1   fa   vinn tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm2   fb   vinp tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm9   fa   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=6
xm10  fb   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=6
xm11  ca   pc   fa   vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xm12  cb   pc   fb   vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
* Standard self-biased cascode current mirror.  Ref side self-matches the ACTUAL
* folded current: it arrives at ca and flows ca->m15->yref->m13->vss with BOTH
* m15 and m13 diode-connected, so ca and yref become the cascode/mirror gate
* references (no separate bias -> no current mismatch, the bug the wide-swing
* attempt hit).  The cascode raises the output impedance at cb so the folded
* path stops shunting the shared node at low V_CM (the §15 low-side fix).
* ca ~1.2 V self-biases, leaving m11 |Vds| = fa-ca ~0.35 V (saturated); the
* output leg cb->m16(gate ca)->cbm->m14(gate yref)->vss holds cb ~0.73 V with
* cbm ~0.2 V, so both output devices stay saturated at the tight output node.
xm15  ca    ca    yref vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=4
xm13  yref  yref  vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=4
xm16  cb    ca    cbm  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=4
xm14  cbm   yref  vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=4

* === LOW-side path: PMOS input pair + NMOS mirror load -> cb ============
* Scaled 1.5x vs the folded-N path (tail m12, pair m12, mirror m6): the trough
* (low half-cycle) gain was PMOS-path-limited ~15 dB below the peak, and that
* asymmetry is the residual h2 that pushes the TEMPERATURE corners over 0.1 %.
* A stronger low-side path lifts the trough (helps cold AND hot); the extra gm
* raises UGF, held by Cc = 9p (recovers 20 kHz loop gain vs a heavier 12p while
* keeping PM > 73 deg) -- see the default below and tb/input_stage.py.
xmp0  tailp vbp  vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=12
xmp1  nP    vinn tailp vdd sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=12
xmp2  cb    vinp tailp vdd sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=12
xmp3  nP    nP   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=6
xmp4  cb    nP   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=6

* === stage 2 + Miller compensation ====================================
xm5   vout cb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m={12*pout}
xm6   vout vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m={12*pout}
rz    cb   nz   {prz}
cc    nz   vout {pcc}

.ends
