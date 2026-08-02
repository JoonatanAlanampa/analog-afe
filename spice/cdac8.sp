* -----------------------------------------------------------------------
* cdac8 -- the 8-bit binary-weighted charge-redistribution DAC of the paddle
* SAR (docs/spec-comparator.md, PLAN.md phase 4). Capacitor matching is the
* whole game here, so the array is built from the PDK's OWN MIM cap subckt
* rather than from ideal C elements: sky130_fd_pr__cap_mim_m3_1 carries a
* local mismatch term
*
*     sigma(C)/C = mismatch_factor * sw_mm_cmim / sqrt(wc*lc*mult)
*
* with sw_mm_cmim = 4.7e-3 ("MIM capacitor Ca CBCM data"), i.e. a matching
* coefficient of 0.47 %.um. That makes the array's linearity a PDK number
* instead of an assumption: run at corner `tt_mm` with a seed per draw and
* the caps mismatch themselves, exactly the way tt_mm is already used for
* transistor offset elsewhere in this repo.
*
* ⚠ WHICH MODEL SET IS LOADED CHANGES THIS NUMBER BY 6x. The PDK ships two
* MIM models. libs.tech/ngspice (via libs.ref) uses 0.01*2.8/sqrt(...) =
* 2.8 %.um and adds a perimeter term; libs.tech/combined -- the one this
* repo's harness actually loads, inherited from stdcells/flow/common.py --
* uses 0.47 %.um and no perimeter. Every number this bench quotes is the
* COMBINED model's. tb/sar.py re-runs the linearity with sw_mm_cmim
* overridden to the pessimistic value, because a 6x disagreement about
* matching is not a rounding difference in a converter.
*
* WEIGHTS ARE UNIT CELLS, NOT SCALED CAPACITORS, AND THAT IS NOT COSMETIC.
* `m=` replicates the subckt (verified: m=4 gives exactly the capacitance of
* four explicit instances) while `mult=` tells the mismatch term how many
* unit cells it is averaging over. Drawing the 128C cap as ONE capacitor of
* 128x the area instead would be WRONG BY 9.5 %: the model biases each edge
* by sw_cap_mim_dw = 0.15 um, so a unit cell is 1.42 -> 1.57 um on a side,
* and that bias does NOT scale with the drawing. 128 unit cells = 631 fF; one
* 128x-long capacitor = 571 fF. Nine percent on the MSB is ~24 LSB of DNL --
* which is the whole reason real arrays are built from identical unit cells.
*
* PLATE ORIENTATION IS NOT ARBITRARY. c0 is the met3 bottom plate (large
* parasitic to substrate); c1 is the capm plate above it. The array's `top`
* node is the floating charge-holding node, so it goes on c1 and every c0
* faces a driver that does not care what it is loaded with.
*
* THE BOTTOM-PLATE DRIVERS ARE MODELLED, AND THAT IS DELIBERATE. Each bottom
* plate is driven by an ideal 3-way mux (VIN while sampling, else VREF or GND
* per the code bit) behind `rdrv`. A real one is a logic buffer between the
* same two rails; what it contributes is its on-resistance, which is what
* rdrv models, and charge injection into a node that is DRIVEN -- so it lands
* on the driver, not on the sampled charge. The switch whose injection IS a
* conversion error is the top-plate switch, and that one is a real sky130
* transmission gate below.
*
* smp / smpn -- top-plate switch (true / complement)
* smpb       -- bottom-plate mux: 1 = drive VIN. SEPARATE from smp on purpose,
*               so the testbench can open the top switch FIRST. That ordering
*               is the entire point of bottom-plate sampling: the top switch's
*               charge injection then happens at a fixed potential and is
*               signal-INDEPENDENT, so it becomes an offset instead of a
*               distortion.
*
* Pins: top vin vcm b7..b0 smp smpn smpb vdd vss
* -----------------------------------------------------------------------
.subckt cdac8 top vin vcm b7 b6 b5 b4 b3 b2 b1 b0 smp smpn smpb vdd vss
+ wu=1.42 lu=1.42 rdrv=1k wsw=3 lsw=0.15

* === top-plate sampling switch =========================================
* A full transmission gate: an NMOS alone cannot pass vcm=0.9 V well on a
* 1.8 V rail (the same Vth-versus-supply arithmetic that killed the PMOS
* input pair in design-notes 1), and the complementary pair also cancels
* part of the clock feedthrough.
xsn top smp  vcm vss sky130_fd_pr__nfet_01v8 w={wsw} l={lsw}
xsp top smpn vcm vdd sky130_fd_pr__pfet_01v8 w={2*wsw} l={lsw}

* === the binary array ==================================================
xc7 nb7 top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=128 m=128
xc6 nb6 top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=64 m=64
xc5 nb5 top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=32 m=32
xc4 nb4 top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=16 m=16
xc3 nb3 top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=8 m=8
xc2 nb2 top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=4 m=4
xc1 nb1 top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=2 m=2
xc0 nb0 top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=1 m=1
* the terminating "dummy" unit cap: it is what makes the total 256 units, so
* one LSB is exactly Vref/256 and the array divides binary rather than 255ths
xcd nbd top sky130_fd_pr__cap_mim_m3_1 w={wu} l={lu} mult=1 m=1

* === bottom-plate drivers ==============================================
bd7 d7 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : ((v(b7) > v(vdd)/2) ? v(vdd) : 0)
bd6 d6 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : ((v(b6) > v(vdd)/2) ? v(vdd) : 0)
bd5 d5 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : ((v(b5) > v(vdd)/2) ? v(vdd) : 0)
bd4 d4 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : ((v(b4) > v(vdd)/2) ? v(vdd) : 0)
bd3 d3 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : ((v(b3) > v(vdd)/2) ? v(vdd) : 0)
bd2 d2 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : ((v(b2) > v(vdd)/2) ? v(vdd) : 0)
bd1 d1 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : ((v(b1) > v(vdd)/2) ? v(vdd) : 0)
bd0 d0 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : ((v(b0) > v(vdd)/2) ? v(vdd) : 0)
* the dummy cap never carries a code bit -- VIN while sampling, ground after
bdd dd 0 v = (v(smpb) > v(vdd)/2) ? v(vin) : 0

rd7 d7 nb7 {rdrv}
rd6 d6 nb6 {rdrv}
rd5 d5 nb5 {rdrv}
rd4 d4 nb4 {rdrv}
rd3 d3 nb3 {rdrv}
rd2 d2 nb2 {rdrv}
rd1 d1 nb1 {rdrv}
rd0 d0 nb0 {rdrv}
rdd dd nbd {rdrv}

.ends
