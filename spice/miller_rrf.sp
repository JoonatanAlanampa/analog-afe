* -----------------------------------------------------------------------
* miller_rrf -- FOLDED complementary (rail-to-rail) input, two-stage Miller.
*
* The bench chain forced this. The 1 Vpp THD wall is the NMOS input pair's
* DRAIN-PIN hard wall at V_CM = 1.40 V (the swing's high peak). Two simpler
* fixes each fail:
*   miller_fc  (fold the NMOS pair)  -> high side fixed, LOW side starves
*                                       (fixed fold sources) -> 3.11 % THD.
*   miller_rr  (add a PMOS pair, both mirror-loaded) -> LOW side fixed, but
*                                       the NMOS DRAIN-PIN wall still caps the
*                                       high peak -> 0.18 % THD (no better).
* The culprit is common: the NMOS pair's drain pin at 1.40 V. Removing it
* needs FOLDING; keeping the low side needs the PMOS pair. So: BOTH.
*
* TOPOLOGY = miller_fc's folded-cascode NMOS front end (covers the HIGH side,
* no drain pin) + miller_rr's PMOS pair with NMOS-mirror load (covers the LOW
* side), the two summed at the stage-1 output cb:
*   - HIGH V_CM (1.40 V peak): folded NMOS pair strong (drain unpinned at the
*     ~1.6 V fold node); PMOS pair tail-starved but the folded NMOS carries.
*   - LOW V_CM (0.40 V trough): folded NMOS starves (fixed fold sources), but
*     the PMOS pair (good low side) carries.
*   - MID: both contribute (gm-doubling, but constant across the swing since
*     neither dies until the swing is EXCEEDED -> no gm-control needed here).
*
* This is a true rail-to-rail input: it removes BOTH hard walls. Cost vs
* miller_ota: ~2x the input devices + a folded cascode + a second tail/mirror
* (Iq, offset, area, a from-scratch layout). Quantified in tb/input_stage.py.
*
* Pins: vinp vinn vout vb vdd vss.  Params: pout, pcc, prz.
* Polarity: BOTH paths pull cb DOWN for vinp^ (folded NMOS via xm2->fb->m12;
* PMOS via xmp2), so they sum; stage 2 inverts -> negative feedback on vinn.
* -----------------------------------------------------------------------
.subckt miller_rrf vinp vinn vout vb vdd vss pcc=8p prz=10k pout=1

* --- master bias diode: external source into vb sets 20 uA --------------
xmb   vb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* === internal bias references (small currents) ========================
* pb: top PMOS-source gate.  pc: PMOS cascode gate.  vbp: PMOS-tail gate.
xbn1  pb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=1
xbp1  pb   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2
xbp2  pc   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2
xbn2  pc   pc   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xbn3  vbp  vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=1
xbp3  vbp  vbp  vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2

* === HIGH-side path: folded-cascode NMOS input -> cb ===================
xm0   tail vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xm1   fa   vinn tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm2   fb   vinp tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
* Top sources at m6 (~13.5 uA) vs m8 (~18): trims Iq (211->202 uA) and lifts
* nominal gain (65->68 dB). It does NOT fix the residual 1 Vpp THD (~0.16 %):
* that floor is the LOW-side gain deficit -- at low V_CM the NMOS tail starves,
* the folded path floods its mirror and runs up in current (lower ro), shunting
* the shared node cb (trough 54 dB vs 72 dB peak). Killing that needs a CASCODED
* summing node or tail-tracking top sources, not sizing -- see design-notes §15.
xm9   fa   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=6
xm10  fb   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=6
xm11  ca   pc   fa   vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xm12  cb   pc   fb   vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xm13  ca   ca   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=4
xm14  cb   ca   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=4

* === LOW-side path: PMOS input pair + NMOS mirror load -> cb ============
xmp0  tailp vbp  vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=8
xmp1  nP    vinn tailp vdd sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xmp2  cb    vinp tailp vdd sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xmp3  nP    nP   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xmp4  cb    nP   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* === stage 2: PMOS CS (gate cb) + NMOS sink (gate vb), class-A ==========
xm5   vout cb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m={12*pout}
xm6   vout vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m={12*pout}

* === Miller compensation (cb is the stage-1 output) ===================
rz    cb   nz   {prz}
cc    nz   vout {pcc}

.ends
