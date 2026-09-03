Status: Superseded

Superseded by
`docs/pud/decisions/mimdram-movement-execution-ownership-and-device.md`.

Question

What minimum Device-visible state, prerequisite policy, action semantics, and
ordinary-command legality should the accepted LC-MOV and GB-MOV command
occurrences use?

Decision

Use the existing Bank node state as the sole Device-visible representation of
an active LC-MOV or GB-MOV. Preserve this simulator invariant:

```text
From first ACT_MOV issue until terminal PREpb issue, the Bank remains visibly
marked at Device level as being inside the protected movement sequence.
```

At terminal `PREpb` issue, its action changes the Bank to conventional
`Closed`. Thus the movement marker is present immediately before the terminal
occurrence and is removed by that occurrence at issue.

This continuous Device-visible marking is a simulator robustness and layering
choice, not a MIMDRAM hardware requirement. A model with zero or one
movement-specific state could theoretically delegate still more physical and
legality information to the retained controller request. Subject to the
continuous-marking invariant, the accepted shared `PREpb` identity, and the
existing Device handler API without request or cursor context, use exactly two
movement-specific Bank states:

```text
MovementActive
MovementDataValid
```

`MovementActive` is an aggregate simulator legality and occupancy state. It
means that the Bank remains inside the protected movement sequence and that
there is no unconsumed source-data/path-valid condition represented in Device
state. It is not one source-defined physical circuit state. The same state may
represent physically different moments, including after the first movement
activation, after the second GB activation, and after `WR_MOV` before terminal
`PREpb`. Use of one aggregate state does not imply that those physical
conditions are identical.

`MovementDataValid` is the aggregate state corresponding to the source
data/path-valid condition established by `RD_MOV` and not yet consumed by
`WR_MOV`. For LC-MOV, it intentionally spans all of these moments:

- after source `RD_MOV` and before source `PREpb`;
- after source `PREpb` while the HFF payload remains retained; and
- after destination `ACT_MOV` and before `WR_MOV`.

For GB-MOV, it represents the source HFF/global-SA path condition between
`RD_MOV` and `WR_MOV`.

Neither movement state stores LC/GB identity, source/destination identity,
activation count, exact occurrence position, operands, logical mat metadata,
ownership identity, row identity, timing progress, or data values. Do not add
a committed, both-endpoints-active, destination-active, per-mat, or other
role-specific state. Do not add a separate HFF-valid flag, global-SA/link flag,
per-Bank sidecar, mat scoreboard, or owner table.

Do not use conventional `Opened` or conventional `m_row_state` entries for
movement endpoint activation. Movement actions do not insert movement rows
into `m_row_state`.

Keep the retained controller request and monotonic movement cursor
authoritative for LC/GB identity, exact occurrence order, endpoint selection,
logical mat metadata, and ownership. Device prerequisites validate only
compatibility with the two aggregate movement conditions.

Before the first `ACT_MOV`, require conventional `Closed`. If the Bank is
conventionally `Opened`, return ordinary `PREpb` as a preparatory prerequisite.
That `PREpb` occurs before movement ownership acquisition and does not advance
the movement cursor. If unrelated work reopens the Bank before the first
`ACT_MOV`, preparation may repeat. An `ACT_MOV` presented in an inherited
DDR4_PuD intermediate state is illegal.

Use these movement prerequisite and action rules:

| Command | Compatible state | Action |
| --- | --- | --- |
| First `ACT_MOV` | `Closed` | Enter `MovementActive`; do not populate `m_row_state`. |
| `ACT_MOV` | `MovementActive` | Remain `MovementActive`. |
| `ACT_MOV` | `MovementDataValid` | Remain `MovementDataValid`. |
| `RD_MOV` | `MovementActive` | Enter `MovementDataValid`. |
| `WR_MOV` | `MovementDataValid` | Enter `MovementActive`. |
| `PREpb` | `MovementDataValid` | Remain `MovementDataValid`. |
| `PREpb` | `MovementActive` | Enter conventional `Closed` and clear `m_row_state` defensively. |

For a compatible state, the prerequisite handler returns the intended
movement command. For an incompatible state, it reports an illegal state. Do
not synthesize an earlier or later movement occurrence, and do not use
ordinary `ACT` or precharge commands to repair movement sequence order.

The accepted LC-MOV state/action trace is:

```text
Closed
-> ACT_MOV -> MovementActive
-> RD_MOV  -> MovementDataValid
-> PREpb   -> MovementDataValid
-> ACT_MOV -> MovementDataValid
-> WR_MOV  -> MovementActive
-> PREpb   -> Closed
```

The accepted GB-MOV state/action trace is:

```text
Closed
-> ACT_MOV -> MovementActive
-> ACT_MOV -> MovementActive
-> RD_MOV  -> MovementDataValid
-> WR_MOV  -> MovementActive
-> PREpb   -> Closed
```

The two GB `ACT_MOV` occurrences remain separately issued and timing-visible.
Their physical activation intervals may overlap even though both occurrences
leave the aggregate Bank state `MovementActive`.

The shared `PREpb` action is state-dependent:

```text
MovementDataValid + PREpb -> MovementDataValid
MovementActive    + PREpb -> Closed
```

Device state does not independently identify a `PREpb` occurrence as LC
source `PREpb` or terminal `PREpb`. The controller cursor determines whether
`PREpb` is the correct intended occurrence. Device state determines only the
aggregate action after that occurrence reaches Device. Consequently, a direct
Device caller can present an invalid sequence that is not rejected exactly as
the architectural LC/GB sequence would be. This is intentional under the
controller-authoritative ordering boundary and avoids reproducing the exact
controller cursor in Device state.

Likewise, Device state does not distinguish first from second GB `ACT_MOV`, or
LC source from destination `ACT_MOV`. The retained request and cursor supply
those occurrence roles.

Ordinary `ACT`, `RD`, `WR`, auto-precharge accesses, inherited DDR4_PuD
commands, `PREab`, refresh, and refresh-generated closes are excluded whenever
their complete scope includes a Bank in either movement state. Controller
ownership eligibility is the primary protection and rejects independent
intersecting work before prerequisite resolution. Defensive Device legality
rejects those commands if they nevertheless reach Device. They do not abort,
repair, or reset movement.

`PREpb` is the exception to blanket close-command illegality because it is
also an accepted movement occurrence. The Device handler cannot distinguish
an owner-issued movement `PREpb` from an unrelated `PREpb` using request
provenance. Controller ownership eligibility is the sole discriminator for
that provenance; the Device applies the state-dependent action above.

Reusing the existing Bank-level `PREpb` identity and Bank state does not claim
that a physical MIMDRAM movement PRE precharges the entire physical Bank. The
physical target scope of movement PRE remains unresolved. Bank-level dispatch
is the accepted aggregate simulator abstraction.

Every state transition occurs when its command issues. A transition does not
mean that activation, capture, relocation, write restoration, or precharge
latency has completed. Directed timing remains independent. In particular,
terminal `PREpb` changes Device state to `Closed` at issue while `tRP` recovery
may continue to block successor commands.

Do not expose MIMDRAM's mat queue or `ACT-enqueue`, `PRE-enqueue`, and
`ACT-dequeue` as additional Device states or commands. No generic hierarchy,
multi-address command, Device-function API, request-context propagation,
same-cycle issue, or timing API extension is required by this state model.

This decision preserves the accepted movement command identities, timing
resource scope, and ownership boundaries. It supersedes the fine-grained
state model in
`docs/pud/decisions/mimdram-movement-device-state-prerequisites-and-actions.md`.

Rationale

The accepted layering assigns operation identity, operands, logical mat
metadata, exact occurrence progress, and ownership to the controller. Device
state therefore should not become a second movement program counter.

The project nevertheless chooses continuous Device-visible movement marking
from first `ACT_MOV` until terminal `PREpb` as a defensive simulator
invariant. It prevents conventional and inherited PuD handlers from treating
an active movement Bank as conventionally available and preserves a clear
Device-level movement occupancy condition throughout the protected sequence.

Under that invariant, one movement-specific state is insufficient for the
shared `PREpb` action. LC source `PREpb` must preserve the source-data-valid
condition, while terminal LC/GB `PREpb` must remove movement marking and return
the Bank to `Closed`. Because the Device handler receives no request or cursor
context, `MovementDataValid` supplies the minimum additional aggregate
distinction. `MovementActive` supplies continuous movement marking when that
unconsumed data/path condition is absent.

Additional phase states could make direct Device invocation reject more
out-of-order occurrences, but they would primarily reproduce activation count,
endpoint role, and exact controller progress. Continuous Bank ownership
already excludes independent same-Bank work, and the retained cursor already
enforces the architectural LC/GB sequence. The two accepted states retain the
chosen defensive invariant without that duplication.

The state model is compatible with GB activation overlap because issue-time
state transitions do not represent completion of physical timing intervals.
It also preserves LC HFF retention across source precharge without storing
payload values or detailed circuit objects.

Evidence

- `docs/pud/references/mimdram-inter-column-data-movement.md` records LC-MOV's
  source `ACT -> RD -> PRE`, HFF retention across source `PRE`, destination
  `ACT -> WR -> PRE`, GB-MOV's overlapping source/destination activation,
  source HFF/global-SA path after `RD`, destination consumption after `WR`, and
  terminal precharge/recovery. It explicitly does not prescribe simulator
  state granularity.
- `docs/pud/decisions/mimdram-movement-occurrences-and-command-identities.md`
  accepts the shared `ACT_MOV`, `RD_MOV`, `WR_MOV`, and existing `PREpb`
  identities, preserves every source-described occurrence, and assigns exact
  occurrence roles to the retained controller request and cursor.
- `docs/pud/decisions/mimdram-movement-ownership-and-atomicity.md` accepts
  continuous Bank ownership from first `ACT_MOV` through terminal `PREpb`,
  pre-prerequisite rejection of independent intersecting work, and
  controller-authoritative monotonic sequence progress.
- `docs/pud/decisions/mimdram-mat-targeting-and-transport-abstraction.md`
  retains mat metadata in the request/controller and rejects explicit per-mat
  Device state for the initial model.
- `src/ramulator/dram/func_types.h` and `src/ramulator/dram/device.cpp` show
  that prerequisite/action handlers receive a Bank node, command ID, address
  vector, and clock, but not the retained request or controller cursor.
- Existing DDR4_PuD command handlers use only `PuDChargeSharing` and
  `PuDSensed` for persistent physical phases while repeated occurrence count,
  operand selection, and request progress remain in
  `src/ramulator/controller/impl/generic_ddr_controller.cpp`.
- Ordinary `ACT` populates conventional `m_row_state`; ordinary `PREpb` enters
  `Closed` and clears that map; and existing all-Bank/refresh handlers operate
  over the same Bank state through the current Device dispatch interfaces.

Open issues

- Exact numeric LC/GB directed timing edges; mapping of `tRAS`, `tRP`, `tWR`,
  and `tRELOC`; the GB activation-occurrence issue gap; independent CK
  quantization; and terminal recovery constraints.
- Whether the final numeric timing graph requires a simulator-only timing
  alias to select different `ACT_MOV` history occurrences for LC and GB.
- Movement command encoding and command/address-bus occupancy, including
  `tRRD`, `tFAW`, activation-current, and other shared Rank/Channel effects.
- Exact physical movement PRE scope below the Bank-aggregate simulator model.
- Movement Column unit, valid range, alignment, HFF-selected datapath mapping,
  detailed transfer quantization, and GB width interpretation.
- Refresh deadlines, maximum deferral, admission near deadlines, priority
  overflow, scope-aware priority bypass, and physical validation of row-policy
  or behavior-changing plugin interaction.
- Exact request departure, callback, statistics-completion, modeled
  data-availability cycles, mixed completion ordering, and movement-specific
  statistics.
- Future same-Bank disjoint-mat MIMD support, including finer mat/range/link
  ownership, legality, timing, and Device representation.
