* -----------------------------------------------------------------------
* biasgen -- constant-gm (beta-multiplier) current reference + start-up.
*   Replaces the ideal `ib` current source that programmed the OTA tail
*   through the vb diode (spec.md open question O2). Every gain / noise /
*   THD / corner number so far assumed that source was perfect; this is the
*   circuit that has to make it real, and its own silent failure mode.
*
* Core: a PMOS mirror (xmp1/xmp2) forces the two branch currents equal; the
*   NMOS side is a mirror (xmn1 diode / xmn2 at K = kmul/2 times the width)
*   with a source resistor R on the wide device. The loop settles where
*   Vgs1 = Vgs2 + I·R, i.e. gm(xmn1) = (1 - 1/sqrt(K))·2/R = 1/R for K = 4 --
*   a transconductance set by a RESISTOR, not by the process. The current I
*   that delivers that gm shifts with process (that is the whole point: gm
*   stays put, I moves), and xmpo mirrors I out to `vbias`.
*
* R is IDEAL here, so the corner sweep shows only the TRANSISTOR-side spread.
*   A layout would use a sky130 xhigh_po poly resistor (~2 kohm/sq, process
*   sigma 2.5% + a real tempco); since gm ~ 1/R, that variation maps straight
*   onto gm and is the reference's true PVT floor -- flagged in docs/biasgen.md,
*   not hidden.
*
* Start-up: the core has a perfectly stable I = 0 state (everything off,
*   self-consistent). The 3-transistor start-up senses it (nl low), injects
*   current into the PMOS gate node until the reference wakes, then switches
*   ITSELF off (xmsu1 kills sx once nl rises). Set rsu = 1e12 to disconnect
*   the injector and watch the reference sit dead forever -- that comparison
*   is the proof the start-up is load-bearing (docs/biasgen.md).
* -----------------------------------------------------------------------
.subckt biasgen vbias vdd vss rval=3400 kmul=8 rsu=1 rpl=1e4

* --- beta-multiplier core -------------------------------------------------
* PMOS mirror on top: xmp2 diode-connected (nr), xmp1 mirrors it 1:1
xmp1 nl nr vdd vdd sky130_fd_pr__pfet_01v8 w=5 l=1 m=2
xmp2 nr nr vdd vdd sky130_fd_pr__pfet_01v8 w=5 l=1 m=2
* NMOS mirror on bottom: xmn1 diode (nl), xmn2 gate=nl, K× wider, degenerated
xmn1 nl nl vss  vss sky130_fd_pr__nfet_01v8 w=5 l=1 m=2
xmn2 nr nl src  vss sky130_fd_pr__nfet_01v8 w=5 l=1 m={kmul}
* --- degeneration R: ideal `rdeg` in PARALLEL with a real xhigh_po poly ---
* Defaults (rpl = 1e4 um -> ~31 Mohm) leave the poly negligible so rval sets R.
* To use the REAL resistor, call with rval = 1e9 (ideal ~open) and rpl sized
* for the target (~1 um for 3.4 kohm). The poly's tempco + 2.5 % process sigma
* are then the reference's true PVT floor -- a constant-gm loop holds
* gm·R = const regardless of R, so gm (hence the OTA's gm) tracks 1/R and is
* only as stable as this resistor.
rdeg src vss {rval}
xrp  src vss vss sky130_fd_pr__res_xhigh_po_0p69 w=0.69 l={rpl}

* --- output mirror leg: source I into vbias (drives the OTA's vb diode) ----
xmpo vbias nr vdd vdd sky130_fd_pr__pfet_01v8 w=5 l=1 m=2

* --- 3-transistor start-up ------------------------------------------------
* nl is low while the core is dead. Then xmsu1 is off, the weak xmsu2 pulls sx
* high, xmsu3 pulls nr down and injects PMOS current; once nl rises xmsu1
* pulls sx low and xmsu3 releases. rsu is a series toggle in the inject path.
* xmsu2: gate at VSS -> an always-on but VERY weak (long-L) PMOS pull-up. It
* is the only thing driving sx while the core is dead, so it wins by default
* there; once nl rises, the much stronger xmsu1 pulls sx low and RELEASES the
* injector. Getting this ratio wrong (xmsu2 too strong) leaves xmsu3 stuck on
* and inflates the reference -- the first cut did exactly that (49.8 uA).
xmsu2 sx  vss vdd vdd sky130_fd_pr__pfet_01v8 w=1 l=20 m=1
xmsu1 sx  nl  vss vss sky130_fd_pr__nfet_01v8 w=2 l=1  m=1
xmsu3 sud sx  vss vss sky130_fd_pr__nfet_01v8 w=2 l=1  m=1
rsu   nr  sud {rsu}
.ends
