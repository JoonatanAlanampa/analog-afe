* -----------------------------------------------------------------------
* strongarm -- a clocked StrongARM latch, used here as a complete comparator
* on its own. This is candidate 1 of 2 for the paddle SAR's comparator; the
* other (spice/comparator.sp) puts a pre-amp in front of this same latch, and
* tb/comparator.py measures what that pre-amp actually buys.
*
* Operation. clk LOW = reset: xm7-xm10 precharge di, dib, outp and outn to
* VDD and the tail is off, so the latch draws NO static current and keeps no
* memory of the previous decision. clk HIGH = evaluate: the tail turns on and
* di/dib discharge at rates set by the input pair; once they fall about a Vth,
* the cross-coupled pair (xm3-xm6) takes over and regenerates to the rails.
*
* Convention: outp is HIGH when vip > vin. (xm1's gate is vip and its drain
* di feeds xm3, which pulls outn down -- so the vip side wins by pulling the
* OTHER output low.)
*
* SIZING IS DELIBERATELY BACKWARDS FROM A TEXTBOOK COMPARATOR, and that is the
* one design decision worth arguing here. A StrongARM is usually sized small
* and short for speed. This one serves a paddle: the SAR runs 8 bits at video
* rate, and even at the audio-rate reach of phase 4 (~50 kSps x 10 clocks) the
* clock is ~500 kHz, so a decision has ~2 us where it needs nanoseconds. There
* is nothing to buy with speed. Offset, however, is set by mismatch, which
* scales as 1/sqrt(W*L) -- so the input pair is LONG (l=1) and WIDE (W=20 by
* default) to spend the entire speed surplus on matching. mi/li are parameters
* so tb/comparator.py can sweep that trade rather than assert it.
*
* Pins: vip vin outp outn clk vdd vss.  Params: mi (input-pair fingers), li.
* -----------------------------------------------------------------------
.subckt strongarm vip vin outp outn clk vdd vss mi=4 li=1

* --- tail switch: on during evaluate ------------------------------------
xmt   tail clk  vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.15 m=4

* --- input pair: the offset-critical devices (see header) ---------------
xm1   di    vip  tail vss  sky130_fd_pr__nfet_01v8  w=5 l={li} m={mi}
xm2   dib   vin  tail vss  sky130_fd_pr__nfet_01v8  w=5 l={li} m={mi}

* --- regenerative core: cross-coupled inverters -------------------------
* The NMOS half sits on di/dib rather than vss, which is what makes this a
* StrongARM: regeneration cannot start until the input pair has developed a
* difference on di/dib, so the decision is made on the INPUT, not on the
* latch's own mismatch.
xm3   outn  outp  di   vss  sky130_fd_pr__nfet_01v8  w=5 l=0.15 m=2
xm4   outp  outn  dib  vss  sky130_fd_pr__nfet_01v8  w=5 l=0.15 m=2
xm5   outn  outp  vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.15 m=2
xm6   outp  outn  vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.15 m=2

* --- reset: precharge every internal node to VDD ------------------------
xm7   outn  clk   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.15 m=1
xm8   outp  clk   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.15 m=1
xm9   di    clk   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.15 m=1
xm10  dib   clk   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.15 m=1

.ends
