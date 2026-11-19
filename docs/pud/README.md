# PuD documentation index

Entry point for the Processing-using-DRAM (PuD) extension of Ramulator2.
This page only maps documents; each linked document is the authority for its
own content. Working rules for the documents live in
[AGENTS.md](../../AGENTS.md#project-documents).

## Where to start

1. [DDR4 PuD user guide](ddr4-pud-user-guide.md) — how to configure and run
   the canonical PuD substrate.
2. [Adding PuD primitives](adding-pud-primitives.md) — development playbook
   for adding new primitives.
3. The current decisions below, grouped by modeling boundary.

## Current decisions (`decisions/`)

These are current project authority. Historical decisions are in
[`decisions/superseded/`](decisions/superseded/); each points to its successor.

### DDR4 substrate, commands, and timing

- [ddr4-pud-unified-substrate](decisions/ddr4-pud-unified-substrate.md) —
  canonical public DDR4 PuD execution model and mat-range selection.
- [ddr4-pud-code-structure](decisions/ddr4-pud-code-structure.md) — how
  `DDR4_PuD` reuses DDR4 while leaving standard DDR4 unchanged.
- [pud-activation-command-representation](decisions/pud-activation-command-representation.md) —
  activation-variant command identities and operation levels.
- [pud-not-command-granularity](decisions/pud-not-command-granularity.md) —
  `N` as one explicit command.
- [pud-timing-resource-and-command-bus-rules](decisions/pud-timing-resource-and-command-bus-rules.md) —
  DDR4 PuD timing, resource occupancy, command bus, and activation windows.

### MIMDRAM geometry and movement

- [mimdram-substrate-and-movement-request-boundary](decisions/mimdram-substrate-and-movement-request-boundary.md) —
  where movement lives and what one movement request represents.
- [mimdram-addressing-geometry-and-payload](decisions/mimdram-addressing-geometry-and-payload.md) —
  common address, geometry, affected-location, and payload contract.
- [mimdram-mat-target-transport-abstraction](decisions/mimdram-mat-target-transport-abstraction.md) —
  delivery of the resolved mat range to each activation.
- [mimdram-movement-execution-ownership-and-device](decisions/mimdram-movement-execution-ownership-and-device.md) —
  execution state, ownership, admission, recovery, and completion.
- [mimdram-movement-timing-and-resource-model](decisions/mimdram-movement-timing-and-resource-model.md) —
  movement timing histories, shared resources, and ACT overhead.

### Operation lowering and workloads

- [pud-operation-physical-lowering](decisions/pud-operation-physical-lowering.md) —
  lowering symbolic primitive traces to physical local rows.
- [mimdram-reduction-placement-and-movement-lowering](decisions/mimdram-reduction-placement-and-movement-lowering.md) —
  reduction merging over the directed GB topology.
- [pud-gemv-macro-contract](decisions/pud-gemv-macro-contract.md) — GEMV
  evaluation baselines, static placement, and shared-K GEMM reuse.

### Multistandard (DDR4 / GDDR7 / HBM3)

- [pud-multistandard-substrate](decisions/pud-multistandard-substrate.md) —
  common substrate architecture, GDDR7/HBM3 bindings, common trace, and
  GEMV/GEMM placement and fusion. Its common execution-model amendment
  (no finite control-engine capacity) amends several decisions above.

## References (`references/`)

Technical source material. Not project decisions.

- [pud-primitives](references/pud-primitives.md) — PuD primitive overview.
- [ddr4-pud-timing-reference](references/ddr4-pud-timing-reference.md) — DDR4 PuD timing.
- [mimdram-geometry](references/mimdram-geometry.md) — MIMDRAM geometry.
- [mimdram-inter-column-data-movement](references/mimdram-inter-column-data-movement.md) — MIMDRAM LC/GB movement.
- [mimdram-data-mapping-and-vector-reduction](references/mimdram-data-mapping-and-vector-reduction.md) — MIMDRAM data mapping and reduction.
- [gddr7-pud-modeling-reference](references/gddr7-pud-modeling-reference.md) — GDDR7 evidence and alternatives.
- [hbm3-pud-modeling-reference](references/hbm3-pud-modeling-reference.md) — HBM3 evidence and alternatives.
- [gpu-pud-gemv-programming-model](references/gpu-pud-gemv-programming-model.md)
  and its [`.cu` specification](references/gpu-pud-gemv-programming-model.cu) —
  project GPU-PuD GEMV programming model.

Dated investigations and audits are in
[`references/investigations/`](references/investigations/).

## Plans (`plans/`)

No implementation plan is active. Completed plans are historical records in
[`plans/completed/`](plans/completed/); source code takes precedence over
their status statements.
