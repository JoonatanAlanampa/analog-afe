* -----------------------------------------------------------------------
* miller_ota -- two-stage Miller-compensated op-amp.
*   stage 1: the same 5T core (NMOS pair, PMOS mirror load), 20 uA
*   stage 2: PMOS common-source with an NMOS current-sink load, 60 uA
*   compensation: Cc from the stage-2 output back to the stage-1 output,
*                 in series with a nulling resistor Rz ~ 1/gm2 that pushes
*                 the RHP zero (gm2/Cc) out of the way.
*
* Pins:  vinp vinn vout vb vdd vss   (same as ota_5t -- the testbenches
*        instantiate either one interchangeably)
*
* Why the second stage exists: a single-stage OTA's gain is gm*ro and its
* output current is capped at the tail. The console audio output is a
* current problem before it is a gain problem. Stage 2 supplies the
* drive; stage 1 supplies the gain.
*
* Input-pair polarity is NMOS for the same measured reason as ota_5t --
* see that file's header.
*
* Polarity NOTE -- this is NOT a copy-paste of ota_5t's pin order:
* stage 2 inverts, so the inverting input must move to the OTHER side of
* the pair. Here xm1 (gate = vinn) sits on the diode side n1, and xm2
* (gate = vinp) drives the stage-1 output n2. Getting this backwards
* gives positive feedback and a latched output, not an oscillation --
* a silent failure worth naming.
* -----------------------------------------------------------------------
* Compensation is parameterised so tb/sweep_comp.py can tune it without
* editing this file: xdut ... miller_ota pcc=4p prz=3k
*
* pout scales the OUTPUT stage (xm5/xm6) only, default 1 = the shipped
* 60 uA sink. It exists because the THD bench (docs/thd.md) found the
* as-shipped stage sink-limited at the 1 Vpp spec swing; tb/thd.py drive
* sweeps it to size the distortion-vs-quiescent-current trade. Stage 1 and
* the bias diode are untouched, so gm1 (hence UGF ~ gm1/Cc) is unchanged.
.subckt miller_ota vinp vinn vout vb vdd vss pcc=2p prz=2k pout=1

* --- bias diode: external source into vb sets 20 uA --------------------
xmb   vb   vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4

* --- stage 1 ----------------------------------------------------------
xm0   tail vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m=4
xm1   n1   vinn tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm2   n2   vinp tail vss  sky130_fd_pr__nfet_01v8  w=5 l=0.5 m=8
xm3   n1   n1   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=4
xm4   n2   n1   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=1 m=4

* --- stage 2: PMOS CS, NMOS sink at 3:1 off the same vb -> 60 uA -------
* m scales with pout (default 1); both devices scale together so the
* quiescent balance and the gm2/gm-ratio are preserved, only the drive
* current (and the non-dominant pole gm2/CL) move.
xm5   vout n2   vdd  vdd  sky130_fd_pr__pfet_01v8  w=5 l=0.5 m={12*pout}
xm6   vout vb   vss  vss  sky130_fd_pr__nfet_01v8  w=5 l=1 m={12*pout}

* --- Miller compensation ----------------------------------------------
rz    n2   nz   {prz}
cc    nz   vout {pcc}

.ends
