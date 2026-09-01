# DDR4 PuD Timing Reference

## Summary

This document records the timing evidence and derivation used to construct
the initial DDR4_PuD timing model.

PRADA [Shin et al., ICCAD 2024] is the primary reference for PuD-specific
circuit behavior and operation latency.

The baseline DDR4 timing comes from the actual Ramulator2 `DDR4_2400R` preset
used by the DDR4_PuD model. That preset defines `tCK = 833 ps` and
`nRP = 16 CK`, so the modeled precharge recovery is `tRP = 13.328 ns`.

The timing quantities used in this document are:

```text
tOC          =  5.00 ns
tCS          =  4.00 ns
tSR          = 23.992 ns
tRP          = 13.328 ns
tN           = 35.00 ns

T_ACT_P      = 46.32 ns
T_RowCopy    = 50.32 ns
T_TRA        = 54.32 ns
T_5RA        = 62.32 ns
T_NOT        = 81.32 ns
```

Evidence classification:

```text
tOC      : directly reported by PRADA
tN       : directly reported by PRADA
tRP      : actual Ramulator2 DDR4_2400R baseline timing (16 CK at 833 ps)
T_ACT_P  : derived from PRADA's reported temporal-NOT latency
tCS      : DDR4_PuD timing-model assumption calibrated from PRADA RowCopy
tSR      : derived from T_ACT_P, tOC, tCS, and DDR4 tRP
```

The model interprets the activation phases as:

```text
A*      = tOC + tCS
A       = tCS
A_S*    = tOC + tCS + tSR
A_S     = tCS + tSR
N       = tN
P       = DDR4 PREpb, followed by the ordinary DDR4 tRP recovery
```

The mapping of reference-level `P` to ordinary per-bank `PREpb` is an
accepted DDR4_PuD simulator decision. Once `P` is represented as `PREpb`,
its recovery timing is the ordinary DDR4 `tRP`; `tRP` is not a new
PuD-specific timing assumption.

For the selected Ramulator2 `DDR4_2400R` baseline:

```text
tCK = 833 ps
nRP = 16 CK
tRP = nRP * tCK = 13.328 ns
```

PRADA's directly reported temporal-NOT latency of `81.32 ns` remains the
aggregate calibration target. Changing the project baseline `tRP` changes the
derived `tSR`; it does not change that source-reported aggregate.

The purpose of this document is to preserve the timing evidence, derivation,
and provenance used by DDR4_PuD. Exact Ramulator2 directed timing constraints
are project modeling decisions and are documented separately.

---

## 1. PRADA command sequences

PRADA separates activation into:

1. offset cancellation,
2. WL activation and cell-BL charge sharing,
3. sensing and restoration.

PRADA defines:

```text
A      : enable a WL without final sensing
A_S    : activation with sensing
A*     : first WL-only activation with offset cancellation
A_S*   : first sensed activation with offset cancellation
N      : NOT command
P      : final precharge
```

Relevant primitive sequences are:

```text
RowCopy:
A_S*(src) -> A(dst) -> P

Multi-destination RowCopy:
A_S*(src) -> A(dst0) -> A(dst1) -> ... -> P

TRA:
A*(x) -> A(y) -> A_S(z) -> P

5RA:
A*(v) -> A(w) -> A(x) -> A(y) -> A_S(z) -> P

NOT:
A_S*(src) -> N -> P
```

PRADA states that RowCopy first completes sensing of the source and then
enables the destination WL.

For TRA and 5RA, participating WLs are enabled sequentially and final sensing
is performed only after charge sharing among the participating rows.

**Source:** Shin et al., ICCAD 2024, §4.2.

---

## 2. Direct PRADA timing values

### 2.1 Offset cancellation

PRADA performs SPICE simulation using a major DRAM vendor's production
sub-20nm technology and explicitly reports:

```text
tOC = 5 ns
```

**Source:** PRADA §6.1 and Figure 8.

### 2.2 NOT command

PRADA implements `N` with internal BLSA operations including separate BL
precharge, BL-BL-bar charge sharing, another separate precharge, and final
sensing.

PRADA explicitly reports:

```text
tN = 35 ns
```

**Source:** PRADA §6.1 and Figure 8.

### 2.3 Charge-sharing interval in Figure 8

PRADA Figure 8 visually separates the first sensed activation into:

```text
OC -> CS -> Sensing & Restore
```

The interval labeled `CS` is approximately 4 ns in the plotted waveform.

PRADA does not explicitly define a timing parameter named `tCS`.
The initial DDR4_PuD model uses:

```text
tCS = 4 ns
```

as the timing-model assumption for one WL activation / charge-sharing step.

This value is calibrated independently from PRADA's reported RowCopy
latency in §4 and is consistent with the interval visible in Figure 8.

**Source:** PRADA Figure 8.

---

## 3. DDR4 precharge timing

The accepted DDR4_PuD command model maps the reference-level final:

```text
P
```

to ordinary per-bank DDR4:

```text
PREpb
```

Therefore, after `P` is issued, the bank uses the ordinary DDR4 precharge
recovery timing before the next activation.

For the selected Ramulator2 `DDR4_2400R` baseline:

```text
tCK = 833 ps
nRP = 16 CK
tRP = nRP * tCK
    = 16 * 0.833
    = 13.328 ns
```

`tRP` comes from the actual Ramulator2 preset used by DDR4_PuD. It is a
baseline DDR4 timing parameter, not a PuD-specific timing assumption.

This document therefore treats:

```text
P recovery = tRP = 13.328 ns
```

**Source:** Ramulator2 `DDR4_2400R` timing preset used by DDR4_PuD.

---

## 4. Base sensed activation and sensing/restoration timing

### 4.1 Aggregate timing from PRADA

PRADA reports that NOT on temporary data can execute as:

```text
A_S* -> N -> P
```

with total latency:

```text
81.32 ns
```

PRADA directly reports:

```text
tN = 35 ns
```

Therefore, the remaining activation-plus-precharge contribution is:

```text
T_ACT_P
= 81.32 - 35.00
= 46.32 ns
```

Thus:

```text
T_ACT_P = 46.32 ns
```

This aggregate includes:

```text
offset cancellation
+ charge sharing
+ sensing/restoration
+ final precharge recovery
```

**Source:** PRADA §6.1-§6.2.

### 4.2 Derivation of sensing/restoration timing

The initial DDR4_PuD model decomposes the aggregate as:

```text
T_ACT_P
= tOC + tCS + tSR + tRP
```

Using:

```text
T_ACT_P = 46.32 ns
tOC     =  5.00 ns
tCS     =  4.00 ns
tRP     = 13.328 ns
```

gives:

```text
tSR
= 46.32 - 5.00 - 4.00 - 13.328
= 23.992 ns
```

Therefore:

```text
tSR = 23.992 ns
```

`tSR` is the sensing-and-restoration interval used by the initial DDR4_PuD
timing model.

`tSR` is not directly tabulated by PRADA. It is a derived DDR4_PuD modeling
quantity obtained by combining PRADA's aggregate operation latency with the
directly reported `tOC`, the calibrated `tCS`, and the actual Ramulator2
DDR4_2400R `tRP`. Preserving PRADA's `81.32 ns` temporal-NOT calibration
target while changing the project baseline `tRP` causes `tSR` to absorb the
difference.

The resulting activation-phase timing model is:

```text
A*      = tOC + tCS
        = 9 ns

A       = tCS
        = 4 ns

A_S*    = tOC + tCS + tSR
        = 32.992 ns

A_S     = tCS + tSR
        = 27.992 ns
```

These are timing-model quantities used to derive directed command spacing;
they are not individual timing parameters directly reported by PRADA.

---

## 5. RowCopy timing and tCS

PRADA reports:

```text
ordinary NOT latency = 131.64 ns
temporal NOT latency =  81.32 ns
```

The temporal-NOT case removes the RowCopy needed to prepare the NOT source.

Therefore:

```text
T_RowCopy
= 131.64 - 81.32
= 50.32 ns
```

For one-destination RowCopy:

```text
A_S*(src) -> A(dst) -> P
```

the initial model gives:

```text
A_S*     = tOC + tCS + tSR = 32.992 ns
A        = tCS             =  4.00 ns
P/tRP    = tRP             = 13.328 ns
```

Thus:

```text
T_RowCopy
= 32.992 + 4.00 + 13.328
= 50.32 ns
```

This exactly reconstructs the RowCopy latency derived from PRADA.

Equivalently:

```text
T_RowCopy
= T_ACT_P + tCS
= 46.32 + 4.00
= 50.32 ns
```

The model therefore uses:

```text
tCS = 4 ns
```

for each additional WL-only activation `A`.

For multi-destination RowCopy:

```text
A_S*(src) -> A(dst0) -> A(dst1) -> ... -> P
```

the initial model assumes one additional `tCS` for every destination:

```text
T_RowCopy(N destinations)
= (tOC + tCS + tSR)
  + N*tCS
  + tRP

= T_ACT_P + N*tCS
```

No nonlinear destination-count penalty or maximum destination count is
established by the current references.

### Ambit cross-check

Ambit independently reports from SPICE simulation that optimized
back-to-back ACTIVATEs require:

```text
tRAS + 4 ns
```

rather than:

```text
2 * tRAS
```

Ambit explains that the second activation does not require another full
sense-amplification interval and can overlap the first activation.

Ambit uses a different row-decoder organization from PRADA, so this result
is not used as a direct PRADA timing value. It is only an independent
cross-check for the 4 ns incremental activation assumption.

**Sources:**
- PRADA §4.2 and §6.2.
- Seshadri et al., MICRO 2017, §5.3.

---

## 6. TRA timing

PRADA's TRA sequence is:

```text
A*(X) -> A(Y) -> A_S(Z) -> P
```

Using the phase timings:

```text
A*      = tOC + tCS =  9.00 ns
A       = tCS       =  4.00 ns
A_S     = tCS+tSR   = 27.992 ns
P/tRP   = tRP       = 13.328 ns
```

gives:

```text
T_TRA
= 9.00 + 4.00 + 27.992 + 13.328
= 54.32 ns
```

Equivalently:

```text
T_TRA
= T_ACT_P + 2*tCS
= 46.32 + 8.00
= 54.32 ns
```

PRADA Figure 9 provides an independent consistency check.

For `a AND b = c`, PRADA can execute:

```text
RowCopy 0 -> C
RowCopy A -> X
RowCopy B -> Y
TRA(X, Y, C)
```

With:

```text
T_AND
= 3*T_RowCopy + T_TRA
= 3*50.32 + 54.32
= 205.28 ns
```

and 16 banks with 8192 row-wide bit operations per bank:

```text
16 * 8192 = 131072 bit operations
```

the corresponding throughput is:

```text
131072 / 205.28 ns
~= 638.5 GOPS
```

which is consistent with the PRADA AND bar in Figure 9
(approximately 0.64 TOPS).

Because Figure 9 is a logarithmic plot and does not tabulate exact AND
throughput, it is used as a consistency check rather than the primary source.

**Source:** PRADA Table 1, Figure 9, and §6.2.

---

## 7. 5RA timing

PRADA defines 5RA as:

```text
A* -> A -> A -> A -> A_S -> P
```

Using the phase timings:

```text
A*      =  9.00 ns
A       =  4.00 ns
A       =  4.00 ns
A       =  4.00 ns
A_S     = 27.992 ns
P/tRP   = 13.328 ns
```

gives:

```text
T_5RA
= 9.00 + 4.00 + 4.00 + 4.00 + 27.992 + 13.328
= 62.32 ns
```

Equivalently:

```text
T_5RA
= T_ACT_P + 4*tCS
= 46.32 + 16.00
= 62.32 ns
```

PRADA does not directly report a 5RA latency.

Therefore, `62.32 ns` is obtained by applying the same `tCS = 4 ns`
assumption used for RowCopy and TRA to the PRADA 5RA sequence.

**Source:** PRADA §4.2 and §5.2.

---

## 8. NOT timing

For:

```text
A_S* -> N -> P
```

the phase timings are:

```text
A_S*    = tOC+tCS+tSR = 32.992 ns
N       = tN          = 35.00 ns
P/tRP   = tRP         = 13.328 ns
```

Thus:

```text
T_NOT
= 32.992 + 35.00 + 13.328
= 81.32 ns
```

This exactly matches PRADA's reported temporal-NOT latency.

Equivalently:

```text
T_NOT
= T_ACT_P + tN
= 46.32 + 35.00
= 81.32 ns
```

**Source:** PRADA §6.1-§6.2.

---

## 9. tRRD and tFAW

PRADA explicitly argues that activations occurring during PIM computation
are free from conventional `tRRD` and `tFAW` constraints because they do not
accompany READ/WRITE commands and data I/O.

Thus, for the PRADA-based DDR4 PuD model:

```text
internal PuD activations are excluded from conventional tRRD/tFAW
```

is directly supported by PRADA.

**Source:** PRADA §5.6.

---

## 10. DDR4_PuD timing values and directed decomposition

### 10.1 Timing quantities

```text
tOC          =  5.00 ns
tCS          =  4.00 ns
tSR          = 23.992 ns
tRP          = 13.328 ns
tN           = 35.00 ns

T_ACT_P      = 46.32 ns
T_RowCopy    = 50.32 ns
T_TRA        = 54.32 ns
T_5RA        = 62.32 ns
T_NOT        = 81.32 ns
```

### 10.2 Activation-command phase costs

```text
A*      = tOC + tCS
        =  9.00 ns

A       = tCS
        =  4.00 ns

A_S*    = tOC + tCS + tSR
        = 32.992 ns

A_S     = tCS + tSR
        = 27.992 ns

N       = tN
        = 35.00 ns

P       = PREpb
recovery after P = tRP
                 = 13.328 ns
```

### 10.3 Candidate directed timing decomposition

The following table records the directed decomposition implied by the timing
model.

It preserves the intended phase durations, but the exact mapping into
Ramulator2 `TimingConstraint` entries remains a separate project decision.

```text
A*    -> A       : tOC + tCS =  9.00 ns
A     -> A       : tCS       =  4.00 ns
A     -> A_S     : tCS       =  4.00 ns

A_S*  -> A       : tOC + tCS + tSR = 32.992 ns
A_S*  -> N       : tOC + tCS + tSR = 32.992 ns

A     -> P       : tCS       =  4.00 ns
A_S   -> P       : tCS + tSR = 27.992 ns
N     -> P       : tN        = 35.00 ns

P     -> next activation readiness : tRP = 13.328 ns
```

This decomposition reconstructs all initial primitive totals:

```text
RowCopy
= 32.992 + 4.00 + 13.328
= 50.32 ns

TRA
= 9.00 + 4.00 + 27.992 + 13.328
= 54.32 ns

5RA
= 9.00 + 4.00 + 4.00 + 4.00 + 27.992 + 13.328
= 62.32 ns

NOT
= 32.992 + 35.00 + 13.328
= 81.32 ns
```

### 10.4 Conversion to Ramulator cycles

Ramulator2 timing constraints use integral clock cycles. Candidate directed
timing values are therefore converted independently using:

```text
n(t) = ceil(t / tCK)
tCK  = 0.833 ns
```

The ordinary precharge recovery continues to use the preset value
`nRP = 16 CK` directly. Applying the conversion to the directed PuD values
gives:

```text
A*    -> A       : ceil( 9.000 / 0.833) = 11 CK
A     -> A       : ceil( 4.000 / 0.833) =  5 CK
A     -> A_S     : ceil( 4.000 / 0.833) =  5 CK

A_S*  -> A       : ceil(32.992 / 0.833) = 40 CK
A_S*  -> N       : ceil(32.992 / 0.833) = 40 CK

A     -> P       : ceil( 4.000 / 0.833) =  5 CK
A_S   -> P       : ceil(27.992 / 0.833) = 34 CK
N     -> P       : ceil(35.000 / 0.833) = 43 CK

P     -> next activation readiness      = nRP = 16 CK
```

Independent conservative rounding of each directed timing constraint makes
the simulated primitive latency slightly larger than the continuous-time
reference latency:

```text
RowCopy = 40 + 5 + 16                 = 61 CK = 50.813 ns
TRA     = 11 + 5 + 34 + 16            = 66 CK = 54.978 ns
5RA     = 11 + 5 + 5 + 5 + 34 + 16    = 76 CK = 63.308 ns
NOT     = 40 + 43 + 16                 = 99 CK = 82.467 ns
```

These cycle totals are simulator discretization results. They do not replace
PRADA's continuous-time evidence or the `81.32 ns` temporal-NOT calibration
target.

---

## 11. Portability of the timing methodology

The DDR4_PuD timing methodology should be reused for another DRAM standard
at the level of the phase decomposition, not by copying DDR4 numerical values
unchanged.

The reusable structure is:

```text
A*      = tOC + tCS
A       = tCS
A_S*    = tOC + tCS + tSR
A_S     = tCS + tSR
N       = tN
P       = target-standard precharge
```

For a future GDDR7_PuD or HBM_PuD model:

- use the target standard's ordinary precharge timing in place of DDR4 `tRP`;
- revalidate or re-derive `tOC`, `tCS`, `tSR`, and `tN` for the target DRAM
  technology;
- preserve the same phase-level decomposition as the starting hypothesis;
- do not assume that DDR4 numerical values transfer unchanged.

This section records a modeling methodology, not a claim that DDR4, GDDR7,
and HBM have identical internal circuit timings.

---

## References

- H. Shin, R. Park, and J. W. Lee,
  "A Processing-using-Memory Architecture for Commodity DRAM Devices
  with Enhanced Compatibility and Reliability,"
  ICCAD 2024. [PRADA]

- V. Seshadri et al.,
  "Ambit: In-Memory Accelerator for Bulk Bitwise Operations Using
  Commodity DRAM Technology,"
  MICRO 2017.
