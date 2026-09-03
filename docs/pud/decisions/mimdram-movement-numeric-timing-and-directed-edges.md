Status: Superseded

Superseded by
`docs/pud/decisions/mimdram-movement-timing-and-resource-model.md`.

Question

What numeric parameters, directed timing dependencies, timing-domain
assignments, and isolated latency boundaries should the initial MIMDRAM
LC-MOV and GB-MOV movement substrate use?

Decision

Use the Ramulator2 `DDR4_2400R` preset as the project baseline for the
combined movement substrate:

```text
tCK  = 833 ps
nRCD = 16 CK
nRTP = 9 CK
nRAS = 39 CK
nRP  = 16 CK
nWR  = 18 CK
```

These are project combined-substrate values inherited from the selected
Ramulator2 preset. They are not MIMDRAM-reported component timings. MIMDRAM's
original evaluation identifies a DDR4-2400 configuration but does not, in the
authoritative project reference, establish the `DDR4_2400R` speed-bin suffix
or this exact component-timing tuple.

Adopt FIGARO's guarded relocation value as an explicit initial simulator
assumption:

```text
tRELOC = 1 ns
nRELOC = ceil(1000 ps / 833 ps) = 2 CK
```

FIGARO directly reports the guarded `1 ns` value for its related relocation
mechanism. FIGARO does not directly validate either MIMDRAM's local LC-MOV
path or its neighboring-global-SA GB-MOV path. Applying the value to both
MIMDRAM movement mechanisms is a project simulator decision.

Retain preset timing parameters in their existing integral CK form. Convert
each independently enforced continuous-time quantity independently with:

```text
nX = ceil(tX / tCK)
```

In particular, the LC composite interval is:

```text
nRELOC + nWR
= ceil(tRELOC / tCK) + preset_nWR
= 2 + 18
= 20 CK
```

It is not obtained by reconverting rounded preset nanosecond values or by
quantizing the combined continuous interval as one new parameter.

Use these LC-MOV primitive-local controller timing dependencies, where the
numbers identify occurrences in the accepted six-occurrence sequence:

| Predecessor | Following occurrence | Delay |
| --- | --- | ---: |
| occurrence 0 `ACT_MOV(source)` | occurrence 1 `RD_MOV(source)` | `nRCD = 16 CK` |
| occurrence 1 `RD_MOV(source)` | occurrence 2 source `PREpb` | `nRTP = 9 CK` |
| occurrence 4 `WR_MOV(destination)` | occurrence 5 terminal `PREpb` | `nRELOC + nWR = 20 CK` |

The first two relationships apply the Bank-local readiness structure of the
source-described regular source `ACT-RD-PRE` analogy. HFF retention changes
what persists across the source PRE; it does not add a source-side relocation
delay. These analogues do not import ordinary external-DQ timing into
`RD_MOV`.

The LC post-`WR_MOV` placement of `tRELOC` and its serialization with `nWR`
are accepted architectural and simulator modeling choices, not a
source-stated directed timing edge. MIMDRAM states that destination WR asserts
the path from the retained HFF value to the destination local row buffer and
reports a conservative equation containing `tRELOC` and `tWR`. It does not
explicitly locate `tRELOC` after the issued WR command or establish that
relocation and write restoration cannot overlap. The initial model chooses:

```text
WR_MOV(destination) -> terminal PREpb = nRELOC + nWR
```

because it causally associates relocation with the command that establishes
the destination path and reproduces the published conservative critical-path
structure. This decomposition may be refined if stronger MIMDRAM
circuit/control evidence becomes available.

Use these context-independent Device timing relationships for LC-MOV:

```text
most recent ACT_MOV in the target Bank -> PREpb  = nRAS = 39 CK
most recent ACT_MOV in the target Bank -> WR_MOV = nRAS = 39 CK
PREpb -> ACT_MOV                                  = nRP  = 16 CK
```

The two `ACT_MOV` relationships use history distance/window 1 in the current
timing representation: the most recent `ACT_MOV` occurrence recorded in the
target Bank. For LC-MOV this means:

- source PRE is constrained relative to source ACT;
- destination WR is constrained relative to destination ACT; and
- terminal PRE is constrained relative to destination ACT.

Waiting until destination ACT plus `nRAS` before destination WR is an
explicit conservative simulator decision used to represent the second
activation/restoration interval before transfer. MIMDRAM does not resolve
whether destination WR could issue earlier or whether activation, relocation,
and write restoration partially overlap.

The isolated LC-MOV issue and recovery timeline is:

| Cycle | Occurrence | Readiness |
| ---: | --- | --- |
| 0 | `ACT_MOV(source)` | start |
| 16 | `RD_MOV(source)` | source ACT + `nRCD` |
| 39 | source `PREpb` | `max(source ACT+nRAS, RD+nRTP) = max(39, 25)` |
| 55 | `ACT_MOV(destination)` | source PRE + `nRP` |
| 94 | `WR_MOV(destination)` | destination ACT + `nRAS` |
| 114 | terminal `PREpb` | `max(destination ACT+nRAS, WR+nRELOC+nWR) = max(94, 114)` |
| 130 | terminal recovery complete | terminal PRE + `nRP` |

Thus:

```text
T_LC,sim
= 2 * (nRAS + nRP) + nRELOC + nWR
= 2 * (39 + 16) + 2 + 18
= 130 CK
```

Use these GB-MOV primitive-local controller timing dependencies, where the
numbers identify occurrences in the accepted five-occurrence sequence:

| Predecessor | Following occurrence | Delay |
| --- | --- | ---: |
| occurrence 0 source `ACT_MOV` | occurrence 2 `RD_MOV(source)` | `nRAS = 39 CK` |
| occurrence 2 `RD_MOV(source)` | occurrence 3 `WR_MOV(destination)` | `nRELOC = 2 CK` |
| occurrence 3 `WR_MOV(destination)` | occurrence 4 terminal `PREpb` | `nWR = 18 CK` |

The GB source-RD dependency explicitly references source ACT occurrence 0 in
the retained primitive execution context even after destination ACT occurrence
1 has issued. GB source RD does not use an unconditional Device
`ACT_MOV -> RD_MOV` relationship.

The GB relationship:

```text
RD_MOV(source) -> WR_MOV(destination) = nRELOC
```

is an accepted initial simulator decomposition of the source-reported:

```text
tRAS + tRELOC + tWR + tRP
```

critical path. It is not a source-stated RD-to-WR timing edge. MIMDRAM
establishes the RD source-path step, the WR destination-path step, the
existence and meaning of `tRELOC`, and the aggregate equation, but does not
explicitly locate `tRELOC` between these two issued commands.

This placement is chosen because it:

- preserves the visible RD/WR occurrence order;
- gives a causal source-path-to-destination-transfer dependency;
- reproduces the published conservative critical-path structure; and
- handles the accepted one-command-per-tick ACT offset without a timing-only
  command identity or cycle subtraction.

It may be refined if stronger MIMDRAM circuit/control evidence becomes
available.

Use these context-independent Device timing relationships for GB-MOV:

```text
most recent ACT_MOV in the target Bank -> WR_MOV = nRAS = 39 CK
most recent ACT_MOV in the target Bank -> PREpb  = nRAS = 39 CK
PREpb -> later opening                            = nRP  = 16 CK
```

The `ACT_MOV` relationships again use history distance/window 1. For GB-MOV,
the most recent `ACT_MOV` is destination ACT occurrence 1, so destination WR
and terminal PRE are constrained relative to destination ACT. The earlier
source ACT remains separately available to the primitive-local source-RD
dependency.

Preserve both visible GB activation occurrences and at most one command issue
per simulator tick. This does not claim that MIMDRAM uses two successive C/A
cycles or establish its exact physical command encoding. The isolated GB-MOV
issue and recovery timeline is:

| Cycle | Occurrence | Readiness |
| ---: | --- | --- |
| 0 | `ACT_MOV(source)` | start |
| 1 | `ACT_MOV(destination)` | next simulator issue slot |
| 39 | `RD_MOV(source)` | source ACT occurrence 0 + `nRAS` |
| 41 | `WR_MOV(destination)` | `max(RD+nRELOC, destination ACT+nRAS) = max(41, 40)` |
| 59 | terminal `PREpb` | `max(WR+nWR, destination ACT+nRAS) = max(59, 40)` |
| 75 | terminal recovery complete | terminal PRE + `nRP` |

The one-CK destination-ACT issue offset is neither subtracted nor ignored.
Destination activation readiness occurs at cycle 40, while source RD plus
`nRELOC` permits destination WR at cycle 41. The relocation dependency
naturally dominates and hides the offset from the critical path.

Thus:

```text
T_GB,sim
= nRAS + nRELOC + nWR + nRP
= 39 + 2 + 18 + 16
= 75 CK
```

Keep context-independent protocol and recovery constraints in Device timing.
In addition to the movement relationships above, recovery into the first
`ACT_MOV` follows the corresponding existing DDR4 opening rules:

```text
PREpb -> ACT_MOV = nRP
PREab -> ACT_MOV = nRP
RDA   -> ACT_MOV = nRTP + nRP
WRA   -> ACT_MOV = nCWL + nBL + nWR + nRP
REFab -> ACT_MOV = nRFC
```

Terminal `PREpb` continues to impose ordinary `nRP` recovery before later
ordinary ACT, inherited DDR4_PuD opening commands, another `ACT_MOV`, or
refresh as applicable under the existing hierarchy constraints. Source LC
`PREpb -> destination ACT_MOV = nRP` is an instance of this general Device
recovery rule, not a separate primitive-local timing edge.

Do not duplicate any primitive-local edge in Device timing. Do not introduce
a timing-only command identity. Do not encode timing progress in Device state.
An occurrence must be request-eligible, prerequisite-compatible,
primitive-local-timing-ready, and Device-timing-ready before issue.
Primitive-local readiness must participate in candidate timing readiness so
that a locally timing-blocked movement does not prevent ready work in another
Bank from being selected.

The retained primitive execution context must conceptually preserve the issue
cycles needed by later occurrence-specific dependencies. An occurrence-indexed
representation such as:

```text
issue_cycle[occurrence_index]
```

is sufficient; a smaller equivalent is permitted. The LC graph later
references issue cycles for occurrence pairs `0 -> 1`, `1 -> 2`, and `4 -> 5`.
The GB graph references `0 -> 2`, `2 -> 3`, and `3 -> 4`. This decision does
not choose C++ fields or an API.

Initially add no movement-specific:

- `tRRD` or `tFAW` participation for `ACT_MOV`;
- unconditional ordinary `ACT_MOV -> ACT_MOV = nRC` constraint;
- ordinary external RD/WR burst, CAS, DQ-turnaround, or sibling-rank DQ timing
  for `RD_MOV` or `WR_MOV`; or
- undocumented shared internal Rank/Channel movement-datapath constraint.

These omissions are explicit initial-model limitations, not claims that the
physical constraints or shared resources do not exist. Movement ACT
activation-current behavior and undocumented shared physical resources remain
uncharacterized. T3 mat-information transport remains accepted, so its queue
pressure and transport-specific C/A contention also remain outside the initial
model.

Interpret the source-reported LC-MOV and GB-MOV equations as spanning from the
first movement activation through completion of terminal precharge recovery,
because both equations include the terminal `tRP` term. Keep these boundaries
distinct:

```text
first ACT_MOV -> terminal PREpb issue
    = visible command-sequence and ownership/state-cleanup boundary

first ACT_MOV -> terminal PREpb recovery complete
    = published-equation comparison boundary

request depart/callback/statistics completion
    = unresolved movement lifecycle boundary
```

At terminal `PREpb` issue, ownership is released and Device state becomes
conventionally `Closed`. Device timing history nevertheless retains the
`PREpb` recovery deadlines and prevents illegal reuse until recovery
completes.

Rationale

The selected graph preserves every accepted visible command occurrence while
matching the two independently quantized conservative latency structures. It
uses the most recent Bank-local `ACT_MOV` history only where a single
unconditional semantic-command edge faithfully selects the intended
activation. It uses primitive-local occurrence history where LC/GB structure
or repeated-command role makes static Device history insufficient.

LC source timing follows MIMDRAM's regular `ACT-RD-PRE` analogy without
mistaking its internal RD for an ordinary host-visible read. The source PRE is
therefore controlled by `max(nRAS, nRCD+nRTP) = 39 CK`, leaving the source RD
visible at cycle 16 while the active interval remains the critical source
term.

Waiting for destination ACT plus `nRAS` before LC destination WR is the
chosen conservative representation of the second activation/restoration
term. Placing relocation after WR is better aligned with the source-described
event that creates the destination connection than placing an uncommanded
relocation interval before WR. Serializing relocation and write recovery
reproduces the conservative equation while keeping the unresolved physical
overlap explicit.

For GB-MOV, source RD must retain a dependency on ACT occurrence 0 even after
ACT occurrence 1 becomes the latest Device ACT history entry. Separately
checking destination activation readiness at WR allows the two physical
activation intervals to overlap. With `nRELOC = 2 CK`, this separate maximum
also absorbs the simulator's one-tick visible ACT issue offset without
inventing a command identity or altering the arithmetic.

General PRE and refresh recovery belong in Device timing because they remain
valid independently of primitive role and must continue to protect the Bank
after terminal ownership and movement state have ended. Occurrence-sensitive
dependencies belong in the primitive execution context under the accepted
timing-responsibility boundary.

Evidence

MIMDRAM source facts:

- LC-MOV performs source `ACT -> RD -> PRE`, retains the source value in HFFs
  across source PRE, and then performs destination `ACT -> WR -> PRE`.
- The LC source phase proceeds like a regular `ACT-RD-PRE` sequence apart
  from the retained HFF-enable behavior.
- LC destination WR asserts the connection from the retained HFF value to the
  destination local row buffer, after which the value is restored to the
  destination cells.
- MIMDRAM reports the conservative LC equation
  `2*(tRAS+tRP)+tRELOC+tWR`.
- GB-MOV activates source and destination rows in different mats
  concurrently, performs a source RD path step followed by a destination WR
  path step, and reports `tRAS+tRELOC+tWR+tRP`.
- The source attributes GB's single effective `tRAS` term to overlapping
  source and destination activation intervals.
- Both reported equations include terminal `tRP`, establishing terminal
  precharge recovery as their comparison boundary.
- MIMDRAM does not state the exact directed placement of `tRELOC`, the exact
  C/A issue relationship of the two GB ACTs, or complete movement-specific
  Rank/Channel shared-resource rules.

FIGARO source facts:

- FIGARO reports a raw relocation latency of `0.57 ns` and a guarded
  `tRELOC = 1 ns` for its SPICE-evaluated relocation mechanism.
- FIGARO's mechanism is physically different from the MIMDRAM LC and GB
  paths, so this evidence does not directly validate either path.

Architectural inferences:

- LC relocation is causally associated with the destination path established
  by WR.
- GB relocation causally connects the source RD path step to the destination
  WR transfer step.
- Destination activation must be sufficiently ready before the destination
  WR path can consume and restore the transferred value.

Project simulator decisions:

- Select `DDR4_2400R` as the combined substrate baseline.
- Apply FIGARO's guarded `1 ns` value to both initial movement paths.
- Map the LC source regular-sequence analogy to `nRCD`, `nRAS`, and `nRTP`.
- Wait for LC destination ACT plus `nRAS` before destination WR.
- Place LC relocation after WR and serialize `nRELOC+nWR` before terminal
  PRE.
- Place GB `nRELOC` on the primitive-local RD-to-WR dependency.
- Issue the two visible GB ACT occurrences in successive simulator ticks
  while permitting their represented physical activation intervals to
  overlap.
- Use latest target-Bank `ACT_MOV` history, window 1, for Device
  `ACT_MOV -> WR_MOV` and `ACT_MOV -> PREpb` constraints.
- Omit movement-specific `tRRD`, `tFAW`, ordinary `nRC`, external-DQ timing,
  and undocumented shared Rank/Channel path constraints from the initial
  model, recording each omission as a limitation rather than a physical
  exemption.

Repository evidence:

- `python/ramulator/dram/ddr4.py` defines the exact `DDR4_2400R` values and
  the existing Bank/Rank recovery constraints.
- `python/ramulator/dram/ddr4_pud.py` retains that preset and demonstrates the
  accepted independent-quantization and context-independent recovery
  methodology.
- `src/ramulator/dram/node.cpp` stores command history by hierarchy node and
  semantic command identity; window 1 selects the most recent occurrence.
- `src/ramulator/dram/device.cpp` updates timing history and applies the
  command action at issue, allowing terminal PRE to close Device state while
  timing recovery remains pending.
- `docs/pud/decisions/mimdram-movement-timing-responsibility.md` assigns
  occurrence-sensitive timing to the retained primitive execution context and
  context-independent protocol/recovery timing to Device.
- The accepted movement occurrence, state, resource-scope, and ownership
  decisions preserve separate visible occurrences, two aggregate movement
  states, Bank-conservative ownership, release at terminal PRE issue, and
  different-Bank progress.

Open issues

- Request depart, callback, statistics-completion, and modeled data-availability
  cycles for LC-MOV and GB-MOV.
- Exact C++ representation and localized API for primitive-local dependency
  metadata and issue-cycle history.
- Integration of composite primitive-local and Device readiness into every
  scheduler comparison and final pre-issue validation path.
- Physical validation or later refinement of the selected LC and GB
  `tRELOC` placements and the assumption that LC relocation and write recovery
  serialize.
- Physical movement command encoding and exact C/A-bus occupancy.
- Whether stronger evidence requires movement participation in `tRRD`,
  `tFAW`, activation-current limits, ordinary row-cycle constraints, or
  additional shared Rank/Channel resources.
- Movement Column units, valid ranges, alignment, HFF mapping, and detailed
  transfer quantization.
- Detailed refresh-deadline/admission policy, row-policy interaction, and
  plugin behavior during movement ownership.
- Portability of all numeric assumptions to another timing preset,
  organization, or DRAM standard.
