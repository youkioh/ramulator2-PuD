Status: Accepted

Question

What minimum device state should DDR4_PuD use for the intermediate phases of
the accepted PuD command sequences?

Decision

Add only the device states `PuDChargeSharing` and `PuDSensed`. Use the existing
`Closed` state after final precharge.

`A*` initiating an unsensed sequence enters `PuDChargeSharing`. Additional
unsensed `A` commands may remain in `PuDChargeSharing`. `A_S` and `A_S*` enter
`PuDSensed`. RowCopy destination `A` commands issued while sensed may remain in
`PuDSensed`, and `N` may remain in `PuDSensed`. Final precharge returns the bank
to `Closed`.

Do not add a finalized state or primitive-specific device states. Primitive
identity, operand identities and ordering, activation and destination counts,
exact sequence progress, and the next expected command remain controller
responsibilities.

This decision defines only the minimum state representation. It does not
define command legality, timing, resource occupancy, interruption,
interleaving, or scheduling behavior.

Rationale

The accepted abstraction requires the device to distinguish an unsensed
charge-sharing phase from a sensed PuD phase. The available reference does not
establish a separate device-visible physical state after final `A_S` or `N`,
and RowCopy has no finalizing command before precharge. A finalized state would
therefore encode controller sequence progress rather than a supported physical
phase.

This follows Ramulator2's split-activation architecture: LPDDR5 uses the
minimal device-visible `Activating` state for the interval between `ACT1` and
`ACT2`, while its controller retains request ownership and continuation
progress.

Evidence

The PuD primitives reference distinguishes wordline-only activation from
activation with sensing and specifies that RowCopy can issue repeated `A`
commands after `A_S*`. It does not define a separate post-majority, post-NOT,
or RowCopy-finalized physical state.

Ramulator2's LPDDR5 `ACT1` action enters `Activating`; `ACT2` advances the bank
to `Opened`; and the `RD` prerequisite path uses those device states while the
LPDDR controller tracks the request that owns the pending `ACT2`.

Open issues

Precharge legality, conventional-command legality, command prerequisites,
interleaving, timing, resource occupancy, interruption, and scheduling remain
for later decision gates.
