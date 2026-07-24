* -----------------------------------------------------------------------
* miller_fc -- FOLDED-CASCODE first stage + class-A output, Miller comp.
*
* WHY THIS EXISTS: miller_ota's 0.167% THD residual at the full 1 Vpp is
* HIGH-SIDE INPUT ICMR (docs/cmrr.md, design-notes.md section 13). The NMOS
* input pair's drains are PINNED at ~0.9 V by the PMOS DIODE mirror
* (n1 = VDD-|Vgs_p|), so when the gate (= V_CM in unity gain) rises to the
* 1.40 V peak of a 1 Vpp swing, the input device triodes (drain-pinning,
* confirmed by sweep: xm2 sat margin crosses 0 exactly at V_CM = 1.40 V).
*
* THE FIX -- unpin the input-pair drain. A folded cascode routes each input
* drain to a FOLD NODE fed by a PMOS current SOURCE (|Vds| ~ |Vdsat| ~ 0.2 V),
* so the fold node sits ~VDD-0.2 ~ 1.6 V instead of 0.9 V. The input device
* now keeps saturation with its gate near VDD, extending the high-side ICMR
* past 1.40 V. The good LOW side of the NMOS pair (holds to ~0.30 V) is kept
* -- so this targets the ONE wall that limits the 1 Vpp swing, without the
* gm-doubling / double-offset cost of a full complementary rail-to-rail pair
* (that candidate is miller_rr.sp, for the comparison the review asked for).
*
* Pins:  vinp vinn vout vb vdd vss     (same interface as miller_ota, so the
*        existing benches instantiate it unchanged)
*
* Params (same knobs as miller_ota so tb/ can retune without editing):
*   pout scales the output stage (xm5/xm6), default 1.
*   pcc / prz are the Miller cap / nulling resistor.
*
* Bias: a single external current into vb (diode NMOS xmb, ~20 uA) programs
* everything. Internal reference branches (small, ~5 uA) derive the PMOS
* source bias pb, the PMOS cascode bias pc, and the NMOS cascode bias nc.
* A real bias generator (biasgen.sp) replaces the ideal ib later.
*
* Currents: tail 20 uA (10 uA/side). Top PMOS sources 20 uA each; after the
* pair steals 10 uA, each cascode branch carries 10 uA into the NMOS cascode
* mirror, whose single-ended output cb is the high-Z gain node -> stage 2.
*
* POLARITY: stage 1 out = cb; input xm2 (gate vinp) -> fold fb -> cb; stage 2
* (xm5) inverts. Feedback closes on vinn. Sign verified by the AC/op bench
* (positive feedback would latch the op point) -- see tb/input_stage.py.
* -----------------------------------------------------------------------
.subckt miller_fc vinp vinn vout vb vdd vss pcc=4p prz=10k pout=1

* --- master bias diode: external source into vb sets 20 uA --------------
xmb   vb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* === internal bias references (small currents, ~5 uA) ==================
* pb: PMOS current-source gate. NMOS (gate vb, 5 uA) pulls a diode PMOS.
xbn1  pb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=1
xbp1  pb   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2
* pc: PMOS cascode gate. PMOS source (gate pb) into an NMOS diode (m2 -> a
* LOWER Vgs, ~0.55 V). pc must be low enough that the PMOS cascode m11 holds
* the fold node fa well BELOW VDD (so the top sources m9/m10 keep Vds margin)
* while still keeping fa HIGH enough to unpin the input-pair drains.
xbp2  pc   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2
xbn2  pc   pc   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* === stage 1: folded cascode ==========================================
* tail (20 uA)
xm0   tail vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
* NMOS input pair -- drains go UP to the fold nodes fa/fb
xm1   fa   vinn tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm2   fb   vinp tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
* PMOS top current sources (20 uA each; gate pb) -> fold nodes sit high
xm9   fa   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=8
xm10  fb   pb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=8
* PMOS cascodes (gate pc) step the signal down to the NMOS mirror; these are
* what keep fa/fb HIGH (fa = ca + |Vds_m11|) -- the whole drain-unpin trick.
xm11  ca   pc   fa   vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xm12  cb   pc   fb   vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
* NMOS mirror (simple) -- ref side ca sets nmir; mirror side output = cb.
* A cascode here would squeeze cb (must sit ~0.73 V to bias stage 2); the
* PMOS cascode already supplies the stage-1 output resistance, so a simple
* NMOS mirror is enough and keeps the output-node headroom.
xm13  ca   ca   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=4
xm14  cb   ca   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=4

* === stage 2: PMOS CS (gate cb) + NMOS sink (gate vb), class-A ==========
xm5   vout cb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m={12*pout}
xm6   vout vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m={12*pout}

* === Miller compensation (cb is the stage-1 output) ===================
rz    cb   nz   {prz}
cc    nz   vout {pcc}

.ends
