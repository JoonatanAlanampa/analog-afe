* -----------------------------------------------------------------------
* ota_5t_pmos -- REFERENCE ONLY. NOT A CANDIDATE.
*
* This is the ORIGINAL PMOS-input version of ota_5t, the one that was
* abandoned because it cannot operate at mid-rail on a 1.8 V rail:
* V_tail = V_CM + |Vgs| = 0.9 + 0.88 = 1.78 V leaves the tail source
* 19 mV, and it simulates in triode delivering 3.87 uA of a requested
* 20 (docs/design-notes.md section 1).
*
* It is kept, and simulated, for exactly one purpose: the NMOS pair that
* replaced it is the NOISIER device in the flicker band this circuit
* works in, and "the cost is some extra 1/f noise" is not a number.
* Running this at a common mode where it DOES work (V_CM = 0.5 V, inside
* a PMOS pair's input range) turns that hand-wave into a measured ratio.
*
* Do not promote this to a candidate without also solving the mid-rail
* problem -- a lower V_CM costs output swing, which is spec row 3.
*
* Pins:  vinp vinn vout vb vdd vss
*   vb   = bias node, diode to VDD -- an external sink of IB FROM vb to
*          vss programs the tail. NOTE this is the opposite polarity to
*          the NMOS-tailed designs, whose vb diode goes to vss.
* -----------------------------------------------------------------------
.subckt ota_5t_pmos vinp vinn vout vb vdd vss

* --- bias diode: external sink on vb sets the mirror voltage -----------
xmb   vb   vb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=4

* --- tail current source (1:1 with xmb) --------------------------------
xm0   tail vb   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=4

* --- input differential pair ------------------------------------------
xm1   n1   vinp tail vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8
xm2   vout vinn tail vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m=8

* --- NMOS mirror load (n1 is the diode side) ---------------------------
xm3   n1   n1   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xm4   vout n1   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

.ends
