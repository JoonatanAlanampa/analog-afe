* -----------------------------------------------------------------------
* comparator -- pre-amp + StrongARM latch. Candidate 2 of 2 for the paddle
* SAR's comparator; candidate 1 is the bare latch (spice/strongarm.sp). The
* question tb/comparator.py answers is whether this pre-amp earns its
* quiescent current, measured on offset, kickback and metastability rather
* than assumed.
*
* A CORRECTION TO WHAT WAS BANKED. topology-review.md kept the 5T OTA on the
* grounds that its shape suits "the comparator pre-amp", because it drives a
* capacitive load. The differential PAIR transfers; the MIRROR LOAD does not.
* A 5T OTA is single-ended by construction -- the mirror folds the two sides
* into one node -- and a StrongARM needs a DIFFERENTIAL drive, one node per
* input. So the load here is a pair of diode-connected PMOS instead: gain
* gm_n/gm_p, differential in and differential out, and an output common mode
* pinned at VDD-|Vgs_p| ~ 0.9 V, which is where the latch's input pair wants
* to sit anyway. What was really banked was the input pair, not the OTA.
*
* Why a pre-amp at all, for a block this slow:
*   - it divides the LATCH's offset by its gain, referred to the input;
*   - it isolates the latch's kickback from the SAR's DAC top plate, which is
*     the charge-holding node the whole converter's accuracy rests on.
* Both are measured in docs/comparator.md; neither is taken on faith.
*
* Pins: vip vin outp outn clk vb vdd vss  (vb = the 20 uA constant-gm bias,
* the same reference spice/biasgen.sp provides to the audio buffer).
* -----------------------------------------------------------------------
.subckt comparator vip vin outp outn clk vb vdd vss mp=8 lp=1 mi=4 li=1

* --- bias diode: external source into vb sets 20 uA --------------------
* Same convention as miller_ota.sp -- the subckt carries its own diode so
* every bench biases it by pushing a current INTO vb, and the mirror ratio
* is visible here rather than hidden in a testbench.
xmb   vb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* === pre-amp: NMOS pair, PMOS diode loads ==============================
* Long devices again (lp=1 default): the pre-amp's own mismatch is referred
* straight to the input, so it is the one place in the chain where sizing for
* matching is not optional. Its gain then divides everything downstream.
xmt   ptail vb   vss   vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xm1   pon   vip  ptail vss  sky130_fd_pr__nfet_01v8  w=5 l={lp} m={mp}
xm2   pop   vin  ptail vss  sky130_fd_pr__nfet_01v8  w=5 l={lp} m={mp}
xm3   pon   pon  vdd   vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=2
xm4   pop   pop  vdd   vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=2

* === the same latch, driven differentially by the pre-amp ==============
* pop rises with vip (xm1 pulls pon DOWN), so pop is the vip-positive output
* and feeds the latch's vip input -- the sense of the whole comparator is
* preserved: outp HIGH means vip > vin.
xlatch pop pon outp outn clk vdd vss strongarm mi={mi} li={li}

.ends
