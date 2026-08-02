* -----------------------------------------------------------------------
* sar_logic -- the SAR sequencer, built ENTIRELY from the user's own standard
* cells (spice/own_cells.sp). This is PLAN.md phase 4's last item: up to here
* the sequencing was ideal XSPICE digital, deliberately, so that INL/DNL/ENOB
* were properties of the array and the comparator alone. This file replaces
* that model with the real thing -- INV_X1, NAND2_X1, NOR2_X1 and DFF_X1, the
* same cells that were drawn, DRC/LVS-signed-off, characterized, and used to
* harden CORDIC-1 with zero foundry cells in the netlist.
*
* TWO LIBRARY PROPERTIES SHAPED THIS, and both are honest constraints:
*
*   1. DFF_X1 HAS NO RESET. It is the dfxtp_1 topology, D/CLK -> Q, nothing
*      else. So every register here is cleared SYNCHRONOUSLY, by forcing its
*      D input low while `rst` is high and letting a clock edge land. That is
*      why `rst` must still be high AT a clock edge -- a reset pulse that ends
*      before the first edge would clear nothing at all, and the converter
*      would start from whatever the DC solution happened to pick.
*   2. NAND3/NOR3 ARE NOT IN THE LIBRARY (dropped in v1 on measured PPA), so
*      every function below is composed from two-input gates plus inverters.
*
* WHAT IT DOES. An 11-stage one-hot pointer walks a single 1 along the
* conversion: s0,s1 = sample; s2..s9 = the eight bit trials, MSB first;
* s10 = done. Bit b is owned by stage 2+(7-b). For its trial the pointer
* forces that bit's capacitor to VREF, and at the end of the trial the bit
* registers the comparator's decision:
*
*     b_out = s_own OR q          (forced high during the trial, then held)
*     q(next) = (q OR (s_own AND dec)) AND NOT rst
*
* q is a SET-ONLY register: it can only go high, and only during its own
* trial, which is exactly the invariant a SAR needs and is cheaper than a
* 2:1 mux. It relies on q being cleared to 0 first -- see constraint 1.
*
* WHY A SHARED DECISION REGISTER (`dec`). The code registers are clocked by
* the master clock, whose edge falls at the END of a trial -- by which time
* the comparator has been reset and BOTH its outputs are high again, so
* sampling it there would latch "keep" every time. `dec` is one DFF clocked by
* the capture strobe, which fires while the decision is still valid; the code
* registers then sample a stable value on the master edge. One extra flop for
* the whole converter, instead of a gated clock per bit.
*
* Pins: clk cap rst start keep b7 b6 b5 b4 b3 b2 b1 b0 vdd vss
*   clk   master clock -- pointer advances and code registers sample
*   cap   capture strobe -- fires mid-trial while the decision is valid
*   rst   synchronous clear, active high, MUST overlap a clock edge
*   start one-clock pulse that injects the 1 into the pointer
*   keep  the comparator's `cn`: high when the top plate is BELOW the
*         reference, i.e. the trial code is still under the input
* -----------------------------------------------------------------------
.subckt sar_logic clk cap rst start keep b7 b6 b5 b4 b3 b2 b1 b0 vdd vss

* === 11-stage one-hot pointer ==========================================
* each stage: d = (its input) AND NOT rst, then a flop. The INV+NOR2 pair is
* how "AND NOT" is spelled in a library with no AND and no reset.
xpi0 start pb0 vdd vss INV_X1
xpn0 pb0 rst pd0 vdd vss NOR2_X1
xpf0 pd0 clk s0 vdd vss DFF_X1
xpi1 s0 pb1 vdd vss INV_X1
xpn1 pb1 rst pd1 vdd vss NOR2_X1
xpf1 pd1 clk s1 vdd vss DFF_X1
xpi2 s1 pb2 vdd vss INV_X1
xpn2 pb2 rst pd2 vdd vss NOR2_X1
xpf2 pd2 clk s2 vdd vss DFF_X1
xpi3 s2 pb3 vdd vss INV_X1
xpn3 pb3 rst pd3 vdd vss NOR2_X1
xpf3 pd3 clk s3 vdd vss DFF_X1
xpi4 s3 pb4 vdd vss INV_X1
xpn4 pb4 rst pd4 vdd vss NOR2_X1
xpf4 pd4 clk s4 vdd vss DFF_X1
xpi5 s4 pb5 vdd vss INV_X1
xpn5 pb5 rst pd5 vdd vss NOR2_X1
xpf5 pd5 clk s5 vdd vss DFF_X1
xpi6 s5 pb6 vdd vss INV_X1
xpn6 pb6 rst pd6 vdd vss NOR2_X1
xpf6 pd6 clk s6 vdd vss DFF_X1
xpi7 s6 pb7 vdd vss INV_X1
xpn7 pb7 rst pd7 vdd vss NOR2_X1
xpf7 pd7 clk s7 vdd vss DFF_X1
xpi8 s7 pb8 vdd vss INV_X1
xpn8 pb8 rst pd8 vdd vss NOR2_X1
xpf8 pd8 clk s8 vdd vss DFF_X1
xpi9 s8 pb9 vdd vss INV_X1
xpn9 pb9 rst pd9 vdd vss NOR2_X1
xpf9 pd9 clk s9 vdd vss DFF_X1
xpi10 s9 pb10 vdd vss INV_X1
xpn10 pb10 rst pd10 vdd vss NOR2_X1
xpf10 pd10 clk s10 vdd vss DFF_X1

* === shared decision register ==========================================
xdec keep cap dec vdd vss DFF_X1

* === eight code registers ==============================================
* --- bit 7, owned by pointer stage s2 ---
xa7 s2 dec an7 vdd vss NAND2_X1
xb7 an7 a7 vdd vss INV_X1
xc7 q7 a7 orb7 vdd vss NOR2_X1
xd7 orb7 rst qd7 vdd vss NOR2_X1
xq7 qd7 clk q7 vdd vss DFF_X1
xe7 s2 q7 cb7 vdd vss NOR2_X1
xg7 cb7 b7 vdd vss INV_X1
* --- bit 6, owned by pointer stage s3 ---
xa6 s3 dec an6 vdd vss NAND2_X1
xb6 an6 a6 vdd vss INV_X1
xc6 q6 a6 orb6 vdd vss NOR2_X1
xd6 orb6 rst qd6 vdd vss NOR2_X1
xq6 qd6 clk q6 vdd vss DFF_X1
xe6 s3 q6 cb6 vdd vss NOR2_X1
xg6 cb6 b6 vdd vss INV_X1
* --- bit 5, owned by pointer stage s4 ---
xa5 s4 dec an5 vdd vss NAND2_X1
xb5 an5 a5 vdd vss INV_X1
xc5 q5 a5 orb5 vdd vss NOR2_X1
xd5 orb5 rst qd5 vdd vss NOR2_X1
xq5 qd5 clk q5 vdd vss DFF_X1
xe5 s4 q5 cb5 vdd vss NOR2_X1
xg5 cb5 b5 vdd vss INV_X1
* --- bit 4, owned by pointer stage s5 ---
xa4 s5 dec an4 vdd vss NAND2_X1
xb4 an4 a4 vdd vss INV_X1
xc4 q4 a4 orb4 vdd vss NOR2_X1
xd4 orb4 rst qd4 vdd vss NOR2_X1
xq4 qd4 clk q4 vdd vss DFF_X1
xe4 s5 q4 cb4 vdd vss NOR2_X1
xg4 cb4 b4 vdd vss INV_X1
* --- bit 3, owned by pointer stage s6 ---
xa3 s6 dec an3 vdd vss NAND2_X1
xb3 an3 a3 vdd vss INV_X1
xc3 q3 a3 orb3 vdd vss NOR2_X1
xd3 orb3 rst qd3 vdd vss NOR2_X1
xq3 qd3 clk q3 vdd vss DFF_X1
xe3 s6 q3 cb3 vdd vss NOR2_X1
xg3 cb3 b3 vdd vss INV_X1
* --- bit 2, owned by pointer stage s7 ---
xa2 s7 dec an2 vdd vss NAND2_X1
xb2 an2 a2 vdd vss INV_X1
xc2 q2 a2 orb2 vdd vss NOR2_X1
xd2 orb2 rst qd2 vdd vss NOR2_X1
xq2 qd2 clk q2 vdd vss DFF_X1
xe2 s7 q2 cb2 vdd vss NOR2_X1
xg2 cb2 b2 vdd vss INV_X1
* --- bit 1, owned by pointer stage s8 ---
xa1 s8 dec an1 vdd vss NAND2_X1
xb1 an1 a1 vdd vss INV_X1
xc1 q1 a1 orb1 vdd vss NOR2_X1
xd1 orb1 rst qd1 vdd vss NOR2_X1
xq1 qd1 clk q1 vdd vss DFF_X1
xe1 s8 q1 cb1 vdd vss NOR2_X1
xg1 cb1 b1 vdd vss INV_X1
* --- bit 0, owned by pointer stage s9 ---
xa0 s9 dec an0 vdd vss NAND2_X1
xb0 an0 a0 vdd vss INV_X1
xc0 q0 a0 orb0 vdd vss NOR2_X1
xd0 orb0 rst qd0 vdd vss NOR2_X1
xq0 qd0 clk q0 vdd vss DFF_X1
xe0 s9 q0 cb0 vdd vss NOR2_X1
xg0 cb0 b0 vdd vss INV_X1

.ends
