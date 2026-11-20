Status: Accepted

Question

How are the PRADA-derived PuD compute operations represented as Ramulator2
commands, and what timing, command-bus occupancy, activation-window, and
destination-count rules does the DDR4 binding use for them?

Decision

This is the canonical command-identity and DDR4 compute-timing authority for
the [unified DDR4 PuD substrate](ddr4-pud-unified-substrate.md). Range-local
timing scope, recovery, conflicts, and movement timing are in the
[execution decision](mimdram-execution-and-timing.md). The command identities
are shared by the GDDR7 and HBM3 bindings; their numeric timing is in the
[multistandard decision](pud-multistandard-substrate.md).

**Command identities**

Represent the activation variants `A`, `A*`, `A_S`, and `A_S*` as four
explicit lower-level DRAM commands with the identifiers `ACT_PUD`,
`ACT_PUD_OC`, `ACT_PUD_S`, and `ACT_PUD_S_OC`, respectively.

Represent `N` as one explicit lower-level DRAM command. Keep the internal
circuit phases described by the reference, including separate BL/BL-bar
precharge, BL-BL-bar charge sharing, and sensing, internal to `N`. Do not
expose them as independently schedulable Ramulator2 commands. This is a
simulator abstraction, not a claim that `N` is physically a single
indivisible circuit operation.

Keep RowCopy, MAJ3, MAJ5, NOT, and NOT_COPY as controller-sequenced
request-level operations only. Do not introduce device-level primitive
commands for them. `NOT_COPY` is a request-level composition of the same
activation commands, `N`, and `PREpb`.

**DDR4 timing baseline and derivation**

Use the Ramulator2 `DDR4_2400R` preset as the authoritative DDR4 PuD
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

`tSR` is a derived DDR4 PuD modeling quantity, not a timing value directly
reported by PRADA. Preserving the PRADA aggregate while using the actual
`DDR4_2400R` `tRP` causes `tSR` to absorb the baseline difference.

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

**Directed constraints**

Convert each continuous directed timing value independently to Ramulator2
cycles using `ceil(t / tCK)`. These constraints are enforced from the history
of each protected resolved compute range, not a Bank-global compute history
(see the [execution decision](mimdram-execution-and-timing.md)):

- `ACT_PUD_OC -> ACT_PUD`: 11 CK.
- `ACT_PUD -> ACT_PUD`: 5 CK.
- `ACT_PUD -> ACT_PUD_S`: 5 CK.
- `ACT_PUD_S_OC -> ACT_PUD`: 40 CK.
- `ACT_PUD_S_OC -> N`: 40 CK.
- `ACT_PUD -> PREpb`: 5 CK.
- `ACT_PUD_S -> PREpb`: 34 CK.
- `N -> PREpb`: 43 CK.
- `N -> ACT_PUD`: 43 CK (the NOT_COPY destination activation, using the
  same `nPUD_N` interval).
- `PREpb -> ACT_PUD_OC / ACT_PUD_S_OC`: inherited `nRP = 16 CK`.

Independent ceiling of each constraint makes simulated primitive latency
slightly larger than the continuous-time reference latency:

```text
RowCopy = 61 CK = 50.813 ns
TRA     = 66 CK = 54.978 ns
5RA     = 76 CK = 63.308 ns
NOT     = 99 CK = 82.467 ns
```

**Simulator modeling assumptions**

- `N` is one aggregate command with no exposed internal timing boundaries.
- Each PuD command occupies the command bus for one CK.
- Internal operation latency is represented by directed timing constraints,
  not by command-bus occupancy.
- PuD activations do not participate in `tRRD` or `tFAW`.
- Unrelated banks receive no additional PuD timing restriction beyond the
  existing shared command bus. Conventional Bank/rank timing retains its
  ordinary scope.
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

Conventional commands that conflict with a protected PuD context are governed
by the [execution decision](mimdram-execution-and-timing.md). Standard DDR4
timings remain unchanged.

Rationale

Distinct command identifiers fit Ramulator2's command-indexed representation
without adding variant metadata to generic command interfaces. Keeping the
primitives at request level matches their controller-sequenced request mapping
and avoids multi-address or variable-length device commands. The in-scope
model does not require the internal phases of `N` to be independently
scheduled; a single explicit command provides the required identity without
introducing unsupported phase-level commands.

Using the actual simulator preset prevents the PuD model from claiming a
baseline precharge value that Ramulator2 does not use. Re-deriving `tSR`
preserves PRADA's reported aggregate latency while keeping the provenance of
each quantity explicit.

Directed constraints match Ramulator2's timing engine. One-CK command-bus
occupancy avoids mistaking internal circuit latency for command transmission
time. Linear RowCopy timing follows the repeated activation model without
inventing an unsupported destination-count penalty.

Evidence

- **Provenance.** Consolidated on 2026-11-19 from three now-Superseded
  decisions, which retain their acceptance-time text:
  [activation command representation](superseded/pud-activation-command-representation.md),
  [NOT command granularity](superseded/pud-not-command-granularity.md), and
  [timing, resource, and command-bus rules](superseded/pud-timing-resource-and-command-bus-rules.md).
  The original "target-bank-local" timing scope was refined to range-local
  scope by the execution decision. The `N -> ACT_PUD` entry documents the
  implemented interval that the execution decision already names.
- **Source facts.** Ramulator2's `DDR4_2400R` preset supplies `tCK = 833 ps`
  and `nRP = 16 CK`. PRADA directly reports `tOC = 5 ns`, `tN = 35 ns`, and
  temporal-NOT latency `81.32 ns`, and states that its internal PuD
  activations are excluded from conventional `tRRD` and `tFAW` constraints.
  The [PuD primitives](../references/pud-primitives.md) and
  [DDR4 PuD timing](../references/ddr4-pud-timing-reference.md) references
  supply the command sequences, the internal phases of `N`, and repeated
  RowCopy destination activations. Ramulator2 represents lower-level DRAM
  operations with explicit command identifiers, timing as directed command
  constraints at hierarchy levels with integral cycle values, and command-bus
  occupancy separately through command cycles.
- **Derived quantities.** `tRP = 13.328 ns`, `T_ACT_P = 46.32 ns`,
  `tSR = 23.992 ns`, the continuous activation costs and primitive totals, and
  the ceiling-converted constraints and simulated totals above.
- **Project assumptions.** The `tCS` value, resource scope, command-bus
  occupancy, cross-bank behavior, ordinary-recovery mapping to PuD opening
  commands, linear destination scaling, and unsupported intermediate refresh
  behavior are explicit project modeling assumptions rather than
  vendor-validated DRAM facts.
- **Implementation.** [Common PuD declarations](../../../python/ramulator/dram/pud.py)
  define the command identities and the PRADA phase dependencies;
  [DDR4 PuD](../../../python/ramulator/dram/ddr4_pud.py) supplies the numeric
  values (`nPUD_ACT_OC=11`, `nPUD_ACT=5`, `nPUD_ACT_S_OC=40`, `nPUD_ACT_S=34`,
  `nPUD_N=43`).

Open issues

- Vendor validation of the `tCS = 4 ns` charge-sharing interval and its
  technology dependence.
- Vendor validation of one-CK command encoding and command-bus occupancy for
  every PuD command, especially `N`.
- Vendor validation of resource occupancy, absence of additional rank/channel
  shared resources, and permitted cross-bank overlap.
- Vendor validation that PuD activations should remain excluded from
  activation-current limits corresponding to `tRRD` and `tFAW`.
- Refresh behavior during an intermediate PuD phase remains unsupported and
  requires evidence before such an interaction can be modeled.
- More detailed internal-`N` circuit fidelity, or different physical-fidelity
  assumptions for these commands, require a new decision.
- Any further target standard requires revalidation or re-derivation of `tOC`,
  `tCS`, `tSR`, `tN`, command encoding, resource scope, and the target's
  precharge timing; DDR4 values must not be copied unchanged.
