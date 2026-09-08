Status: Superseded

Superseded by
`docs/pud/decisions/mimdram-movement-occurrences-and-command-identities.md`.

Question

Which source-described LC-MOV and GB-MOV phases should be explicit
Ramulator-visible command roles, and how should GB-MOV's concurrent physical
activation be represented within the current controller/device architecture?

Decision

Keep LC-MOV and GB-MOV as controller-sequenced request-level operations.
Represent their source-described controller-directed phases as explicit,
movement-specific Ramulator-visible command roles. These roles are simulator
sequence and potential timing boundaries. They do not imply exact ordinary
DRAM command encodings, a one-to-one correspondence with C/A-bus transactions,
or command-bus occupancy.

For LC-MOV, expose six ordered roles:

```text
source activation
-> source read/capture
-> source close with retained movement payload
-> destination activation
-> destination write/commit
-> destination close
```

Keep HFF enable transitions, latching and amplification, datapath propagation,
and cell restoration internal to these roles.

For GB-MOV, expose five ordered roles:

```text
source activation
-> destination activation
-> source read/drive
-> destination write/transfer
-> terminal close
```

Represent the two activation roles as separate one-address simulator commands
and reuse the existing one-command-per-tick controller issue model. Retain both
movement endpoints in the request and use the appropriate source or destination
operand for each one-address role.

The issue order of the GB-MOV activation roles does not serialize their
physical activation work. The later timing model must allow the source and
destination activation intervals to overlap consistently with MIMDRAM's
source-reported concurrent-activation behavior. The exact issue relationship
on the physical C/A bus and whether the simulator issue offset affects
end-to-end latency are not decided here.

Do not introduce true same-cycle multi-command issue or a combined
dual-endpoint Device command. Do not reuse ordinary `ACT`, `RD`, `WR`, or `PRE`
semantics for the movement roles. This command-granularity decision does not
require a generic controller/device API extension.

Reuse controller-retained request context and monotonic sequence progress.
Keep HFF, global-sense-amplifier, neighboring-multiplexer, signal-propagation,
and cell-restoration steps internal to the visible movement roles.

Rationale

MIMDRAM establishes that GB-MOV's source and destination row activations
physically overlap sufficiently for its aggregate latency relation to contain
one `tRAS` activation interval. It does not establish whether the corresponding
ACT commands occupy the same C/A cycle, successive C/A cycles, or another exact
issue relationship. Separate ordered simulator roles therefore preserve both
endpoint identities without promoting an unresolved command-issue detail to a
source fact.

One-address roles fit the current Device command, prerequisite, action, and
timing interfaces and the GenericDDR one-command-per-tick issue path. A
combined dual-endpoint command would require either hiding an endpoint from
Device logic or adding a multi-endpoint context, while true same-cycle issue
would require broader controller scheduling and atomic-issue changes. Neither
extension is required to represent overlapping physical activation intervals;
that overlap belongs to the later timing model.

Movement-specific roles preserve the source-described phase boundaries for
later timing, resource, and state decisions without inheriting ordinary
bank-opening, external-I/O, row-hit, precharge, or maintenance semantics.
Keeping circuit-internal behavior inside those roles avoids treating every
physical transition as an independently schedulable command.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records LC-MOV's
  source `ACT -> RD -> PRE`, retained HFF payload, and destination
  `ACT -> WR -> PRE` behavior.
- The same reference records that GB-MOV activates source and destination rows
  concurrently, then performs source `RD`, destination `WR`, and final
  precharge/recovery.
- MIMDRAM reports
  `T_GB-MOV = tRAS + tRELOC + tWR + tRP` and attributes the single activation
  interval to concurrent source and destination activation.
- MIMDRAM's existing-interface goal, shared command/address interface, and
  mat-information communication mechanism do not establish the exact C/A-cycle
  relationship of GB-MOV's two ACTs.

Repository evidence:

- `src/ramulator/controller/impl/generic_ddr_controller.cpp` issues at most one
  command per tick and already sequences multi-command PuD requests using
  retained request context and monotonic `pud_sequence_index` progress.
- `src/ramulator/dram/device.h` and `src/ramulator/dram/func_types.h` define
  command, timing, prerequisite, and action interfaces around one command and
  one `AddrVec_t`.
- `src/ramulator/base/request.h` provides request-owned ordered operand storage
  capable of retaining both movement endpoints.
- Ordinary command implementations give `ACT`, `RD`, `WR`, and `PREpb`
  conventional bank, access, and cleanup semantics that are not established
  for MIMDRAM movement roles.

Open issues

- Exact timing edges and numeric timing.
- Whether the one-tick-or-greater GB-MOV activation-role issue offset affects
  end-to-end latency.
- Exact movement command encodings and command-bus occupancy.
- Timing and resource scope, including mat, datapath, link, bank, rank, and
  channel constraints.
- Ownership and atomicity scope.
- Concurrency among requests using disjoint mats or other disjoint resources.
- Maintenance, refresh, row-policy, priority, and plugin interaction.
- Exact persistent device-state representation, including any retained-payload,
  active-mat, or intermediate-path state.
- Exact movement Column semantics, transfer width, alignment, and transfer
  quantization.
  Later refinement: `docs/pud/decisions/mimdram-movement-range-and-placement.md`
  accepts one local HFF width per selected LC-MOV mat and an inferred `4N`-bit
  aggregate width in the evaluated four-HFF organization. Movement Column
  semantics, alignment, and detailed transfer quantization remain unresolved.
- Exact movement command names.
- Exact movement-related precharge scope and whether mat-information transport
  commands are explicit or remain metadata/internal.
