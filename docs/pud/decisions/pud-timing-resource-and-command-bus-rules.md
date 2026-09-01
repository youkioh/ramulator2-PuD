Status: Accepted

Question

What timing, resource-occupancy, command-bus, activation-window, and
destination-count rules should DDR4_PuD use for the accepted PuD commands?

Decision

Use the Ramulator2 `DDR4_2400R` preset as the authoritative DDR4_PuD
baseline:

```text
tCK = 833 ps
nRP = 16 CK
tRP = nRP * tCK = 13.328 ns
```

Use PRADA's directly reported temporal-NOT latency of `81.32 ns` as the
aggregate calibration target. Use the source-backed values `tOC = 5 ns` and
`tN = 35 ns`. Adopt `tCS = 4 ns` as an explicit project modeling assumption.
Derive:

```text
T_ACT_P = 81.32 - 35.00
        = 46.32 ns

tSR = T_ACT_P - tOC - tCS - tRP
    = 46.32 - 5.00 - 4.00 - 13.328
    = 23.992 ns
```

`tSR` is a derived DDR4_PuD modeling quantity, not a timing value directly
reported by PRADA. Preserving the PRADA aggregate while using the actual
DDR4_2400R `tRP` causes `tSR` to absorb the baseline difference.

The continuous-time phase costs are:

```text
A*      = tOC + tCS       =  9.000 ns
A       = tCS             =  4.000 ns
A_S*    = tOC+tCS+tSR     = 32.992 ns
A_S     = tCS+tSR         = 27.992 ns
N       = tN              = 35.000 ns
P       = PREpb recovery  = 13.328 ns
```

They reconstruct the continuous-time primitive latencies:

```text
RowCopy = 32.992 + 4.000 + 13.328                 = 50.320 ns
TRA     = 9.000 + 4.000 + 27.992 + 13.328        = 54.320 ns
5RA     = 9.000 + 4.000 + 4.000 + 4.000
          + 27.992 + 13.328                       = 62.320 ns
NOT     = 32.992 + 35.000 + 13.328                = 81.320 ns
```

Convert each continuous directed timing value independently to Ramulator2
cycles using `ceil(t / tCK)`. Use these target-bank-local constraints:

- `ACT_PUD_OC -> ACT_PUD`: 11 CK.
- `ACT_PUD -> ACT_PUD`: 5 CK.
- `ACT_PUD -> ACT_PUD_S`: 5 CK.
- `ACT_PUD_S_OC -> ACT_PUD`: 40 CK.
- `ACT_PUD_S_OC -> N`: 40 CK.
- `ACT_PUD -> PREpb`: 5 CK.
- `ACT_PUD_S -> PREpb`: 34 CK.
- `N -> PREpb`: 43 CK.
- `PREpb -> ACT_PUD_OC / ACT_PUD_S_OC`: inherited `nRP = 16 CK`.

Independent ceiling of each constraint makes simulated primitive latency
slightly larger than the continuous-time reference latency:

```text
RowCopy = 61 CK = 50.813 ns
TRA     = 66 CK = 54.978 ns
5RA     = 76 CK = 63.308 ns
NOT     = 99 CK = 82.467 ns
```

Accept the following simulator modeling assumptions:

- Timing constraints are target-bank-local.
- `N` is one aggregate bank-local command with no exposed internal timing
  boundaries.
- Each PuD command occupies the command bus for one CK.
- Internal operation latency is represented by directed timing constraints,
  not by command-bus occupancy.
- PuD activations do not participate in `tRRD` or `tFAW`.
- Unrelated banks receive no additional PuD timing restriction beyond the
  existing shared command bus.
- Conventional close and refresh recovery before `ACT_PUD_OC` or
  `ACT_PUD_S_OC` follows the corresponding existing DDR4 constraint used
  before `ACT`: `PREpb` and `PREab` use `nRP`; `RDA` uses `nRTP + nRP`; `WRA`
  uses `nCWL + nBL + nWR + nRP`; and `REFab` uses `nRFC`, at the hierarchy
  levels of the existing constraints.
- Each RowCopy destination adds one 5 CK `ACT_PUD` interval.
- No nonlinear RowCopy destination-count penalty is modeled.
- Refresh during an intermediate PuD phase remains unsupported. The supported
  timing path reaches refresh only after final `PREpb` and its ordinary DDR4
  recovery constraint.

Conventional same-bank commands remain governed by the accepted device
legality decision until final `PREpb`. Standard DDR4 timings remain unchanged.

Rationale

Using the actual simulator preset prevents the PuD model from claiming a
baseline precharge value that Ramulator2 does not use. Re-deriving `tSR`
preserves PRADA's reported aggregate latency while keeping the provenance of
each quantity explicit.

Directed bank-level constraints match Ramulator2's timing engine and the
accepted bank-local PuD command model. One-CK command-bus occupancy avoids
mistaking internal circuit latency for command transmission time. Linear
RowCopy timing follows the repeated activation model without inventing an
unsupported destination-count penalty.

Evidence

Source-backed evidence:

- Ramulator2's `DDR4_2400R` preset supplies `tCK = 833 ps` and `nRP = 16 CK`.
- PRADA directly reports `tOC = 5 ns`, `tN = 35 ns`, and temporal-NOT latency
  `81.32 ns`.
- PRADA states that its internal PuD activations are excluded from
  conventional `tRRD` and `tFAW` constraints.
- The accepted PuD references supply the command sequences and repeated
  RowCopy destination activations.
- Ramulator2 represents timing as directed command constraints at hierarchy
  levels, uses integral cycle values, and represents command-bus occupancy
  separately through command cycles.

Derived project quantities are `tRP = 13.328 ns`, `T_ACT_P = 46.32 ns`,
`tSR = 23.992 ns`, the continuous activation costs and primitive totals, and
the ceiling-converted directed constraints and simulated totals above.

The `tCS` value, resource scope, command-bus occupancy, cross-bank behavior,
ordinary-recovery mapping to PuD opening commands, linear destination scaling,
and unsupported intermediate refresh behavior are explicit project modeling
assumptions rather than vendor-validated DRAM facts.

Open issues

- Vendor validation of the `tCS = 4 ns` charge-sharing interval and its
  technology dependence.
- Vendor validation of one-CK command encoding and command-bus occupancy for
  every PuD command, especially `N`.
- Vendor validation of bank-local resource occupancy, absence of additional
  rank/channel shared resources, and permitted cross-bank overlap.
- Vendor validation that PuD activations should remain excluded from
  activation-current limits corresponding to `tRRD` and `tFAW`.
- Refresh behavior during an intermediate PuD phase remains unsupported and
  requires evidence before such an interaction can be modeled.
- Portability to GDDR7 and HBM requires revalidation or re-derivation of
  `tOC`, `tCS`, `tSR`, `tN`, command encoding, resource scope, and the target
  standard's precharge timing; DDR4 values must not be copied unchanged.
