Status: Accepted

Question

What device-level precharge and command-legality semantics should DDR4_PuD
use for the accepted PuD phase states?

Decision

Use a phase-only device legality model. Map the reference-level final `P` to
ordinary per-bank `PREpb` as a DDR4_PuD simulator abstraction.

The legal PuD state transitions are:

- `ACT_PUD_OC` (`A*`) from `Closed` to `PuDChargeSharing`.
- `ACT_PUD_S_OC` (`A_S*`) from `Closed` to `PuDSensed`.
- `ACT_PUD` (`A`) from `PuDChargeSharing` to `PuDChargeSharing`.
- `ACT_PUD` (`A`) from `PuDSensed` to `PuDSensed`.
- `ACT_PUD_S` (`A_S`) from `PuDChargeSharing` to `PuDSensed`.
- `N` from `PuDSensed` to `PuDSensed`.
- `PREpb` from `PuDSensed` to `Closed`.

Before a pending PuD request starts, `ACT_PUD_OC` and `ACT_PUD_S_OC`
request ordinary `PREpb` as their prerequisite when the target bank is in the
conventional `Opened` state. The opening command may issue after the existing
`nRP` recovery. This preparatory `PREpb` does not advance the controller's PuD
sequence cursor; progress advances only when the intended PuD command issues.
This prerequisite does not define final arbitration between pending PuD and
ordinary Read/Write requests.

Conventional `ACT`, `RD`, and `WR` are illegal while the bank is in either
`PuDChargeSharing` or `PuDSensed`. `PREpb` from `PuDChargeSharing` is illegal.
`PREpb` from `PuDSensed` is device-legal even when it would be premature for
the owning high-level primitive.

Exact primitive sequencing, operand identity and order, activation counts,
repeated or misplaced `N`, and request-level premature precharge remain
controller responsibilities. Do not add primitive ownership or sequence
progress to device state.

The `PREpb` mapping and conventional-command legality are explicit simulator
modeling decisions, not verified physical claims.

Rationale

The device needs only to distinguish the accepted unsensed charge-sharing and
sensed phases. Repeated RowCopy destination activations remain legal in
`PuDSensed`, while the controller retains the request-specific information
needed to determine whether a command is correct for a particular primitive.
This preserves the accepted responsibility split without adding
primitive-specific states or progress tracking.

Using `PREpb` reuses the existing per-bank transition to `Closed` and row-state
cleanup. Rejecting `PREpb` during `PuDChargeSharing` avoids inventing an abort
semantics unsupported by the available reference. Reusing ordinary `PREpb`
before the first PuD activation also avoids a PuD-specific close operation or
recovery path.

Evidence

The accepted intermediate-state decision assigns only phase visibility to the
device and assigns primitive identity, operands, counts, and exact progress to
the controller. The PuD primitives reference places `P` after the sensed phase
of each supported sequence but does not define a distinct Ramulator2
precharge command or premature-precharge behavior. Ramulator2's LPDDR split
activation similarly uses minimal device phase state while its controller
tracks request ownership and continuation. Ordinary Ramulator2 `ACT` requests
`PREpb` when its target bank is conventionally open, and the accepted PuD
timing decision already assigns ordinary `nRP` recovery from `PREpb` to both
PuD opening commands.

Open issues

`PREab`, refresh interaction, scheduling and interleaving, numeric timing, and
interruption semantics remain unresolved for later decision gates.
