* -----------------------------------------------------------------------
* miller_rr -- COMPLEMENTARY (rail-to-rail) input, two-stage Miller.
*
* WHY (the review's named alternative, and what the benches forced):
* miller_ota's NMOS input pair triodes at V_CM = 1.40 V (drain pinned at
* ~0.9 V by the PMOS mirror) -> the HIGH half of a 1 Vpp swing distorts.
* A folded-cascode NMOS input (miller_fc) unpins the drain and fixes the
* high side, but REGRESSES the low side (ICMR 3 dB range moved to
* ~0.66..1.55 V) -- the classic one-sided folded-cascode CM range. Neither
* SINGLE NMOS pair covers the [0.40, 1.40] V a mid-rail 1 Vpp swing needs.
*
* THE COMPLEMENTARY FIX: run an NMOS pair AND a PMOS pair in parallel,
* summed at the stage-1 output cb. Each pair's WEAK side is the other's
* STRONG side:
*   - NMOS pair (PMOS mirror load): drains pinned ~0.9 V -> good LOW side
*     (to ~0.30 V), triodes HIGH at 1.40 V.
*   - PMOS pair (NMOS mirror load): drains pinned ~0.65 V -> good HIGH side,
*     triodes LOW.
* Across [0.40, 1.40] BOTH pairs are in range, so the summed gain is full on
* BOTH half-cycles. And because neither pair shuts off until the swing is
* EXCEEDED, the gm-doubling that a rail-to-rail stage normally suffers (gm
* halving near a rail) lands OUTSIDE the swing -> gm is ~constant in-band, so
* no gm-control circuit is needed for THIS swing.
*
* COST vs miller_ota (measured in tb/input_stage.py): a second input pair +
* its tail + mirror (~+40 uA Iq), a second offset contributor (~x1.4 sigma),
* and ~2x input gm -> ~2x UGF, so the Miller cap is re-tuned (larger Cc).
*
* Pins: vinp vinn vout vb vdd vss  (same interface; external 20 uA into vb).
* Params: pout scales the output stage, pcc/prz the Miller network.
*
* POLARITY (both paths must drive cb the SAME way so they sum, not cancel):
*   vinp^  -> NMOS xm2 sinks more from cb  -> cb v
*   vinp^  -> PMOS xmp2 sources less into cb -> cb v      (both pull cb down)
* Stage 2 (xm5, gate cb) then inverts: vinp^ -> vout^ -> non-inverting at
* vinp, inverting at vinn -> negative feedback closes on vinn. Verified by
* op/AC (positive feedback would latch).
* -----------------------------------------------------------------------
.subckt miller_rr vinp vinn vout vb vdd vss pcc=8p prz=10k pout=1

* --- master bias diode: external source into vb sets 20 uA (NMOS side) ---
xmb   vb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
* --- PMOS-tail bias vbp: mirror the ref current up to a PMOS diode --------
xbn1  vbp  vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=1
xbp1  vbp  vbp  vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=2

* === Path N: NMOS pair + PMOS mirror load (good LOW side) -> cb =========
xm0   tailn vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xm1   nN    vinn tailn vss sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm2   cb    vinp tailn vss sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm3   nN    nN   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=4
xm4   cb    nN   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=4

* === Path P: PMOS pair + NMOS mirror load (good HIGH side) -> cb ========
xmp0  tailp vbp  vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=8
xmp1  nP    vinn tailp vdd sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xmp2  cb    vinp tailp vdd sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xmp3  nP    nP   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xmp4  cb    nP   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* === stage 2: PMOS CS (gate cb) + NMOS sink (gate vb), class-A ==========
xm5   vout cb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m={12*pout}
xm6   vout vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m={12*pout}

* === Miller compensation (cb is the stage-1 output) ===================
* Cc default is LARGER than miller_ota's: complementary input ~= 2x gm ->
* ~2x UGF, so more Cc holds the phase margin. Retuned in tb/input_stage.py.
rz    cb   nz   {prz}
cc    nz   vout {pcc}

.ends
