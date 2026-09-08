# Minimal PuD Functional Simulator Design

**Status:** Proposed implementation design  
**Purpose:** Add a small value-level interpreter for existing whole-row PuD request streams while keeping Ramulator2 responsible only for timing, scheduling, command/state behavior, and energy.  
**Initial scope:** Existing RowCopy, MAJ3, MAJ5, NOT, and NOT_COPY requests only. No INT8/FP8 operation generator or GEMV implementation in this task.

---

## 1. Goal

The functional simulator answers one question:

> Given an initialized bitsliced memory state and an ordered sequence of existing PuD requests, what data remains in the referenced rows after those requests execute?

It is intentionally separate from the Ramulator2 timing path.

```text
                 future PuD operation / macro generator
                              |
                              v
                    PuD request sequence
                              |
                   +----------+----------+
                   |                     |
                   v                     v
          Functional simulator       Ramulator2
          --------------------       ----------
          data values                command sequence
          destructive effects        DRAM state
                                     scheduling
          result correctness         timing / energy
```

The two paths should consume the **same logical request sequence**. The functional simulator must not create its own alternate implementation of ADD, MUL, GEMV, or any other higher-level operation.

---

## 2. Scope Boundary

The functional simulator operates at the **existing request-level PuD primitive boundary**.

Initial supported requests:

```text
RowCopy
MAJ3
MAJ5
NOT
NOT_COPY
```

Use the actual request identifiers already present in the repository.

`NOT_COPY` is interpreted as the existing PRADA-derived NOT-and-Copy fused sequence at request level. It is not treated as a new circuit-level primitive.

The functional simulator does **not** interpret lower-level DRAM commands such as:

```text
ACT_PUD
ACT_PUD_S
ACT_PUD_OC
ACT_PUD_S_OC
N
PREpb
ACT_MOV
RD_MOV
WR_MOV
```

Command generation and timing correctness remain the responsibility of the existing Ramulator2 PuD implementation and its microbenchmarks.

---

## 3. Reuse the Existing Request Representation

Do not introduce a new generic PuD request abstraction unless the current repository makes direct reuse impossible.

Preferred interface:

```cpp
functional_sim.execute(request);
```

where `request` is the same existing `Ramulator::Request` shape used by the PuD timing path.

The functional simulator should read only the fields that already define the request's logical effect:

- request type;
- ordered operand address vectors.

Before coding, inspect the current implementations of the five supported request types and determine exactly where their operand information is stored.

If direct reuse of `Request` would require invasive changes to generic Ramulator2 code, stop and ask before introducing another representation.

### Same stream, not necessarily the same mutable object

Ramulator2 may mutate request lifecycle fields such as arrival/departure state or callbacks.

The requirement is therefore:

> Functional and timing simulation must be driven from the same logically generated request sequence.

They do not need to share one mutable C++ object instance after submission.

The functional interpreter itself must not modify the request.

---

## 4. Minimal Functional Memory State

Do not instantiate a full DRAM device.

Store only rows referenced by a test or workload.

Conceptually:

```text
FunctionalMemory
  row location -> row bits
```

A sparse representation is sufficient.

For example:

```cpp
using FunctionalRow = std::vector<uint8_t>;

class FunctionalMemory {
public:
    FunctionalRow& row(/* existing address/location */);
    const FunctionalRow& row(/* existing address/location */) const;
};
```

The exact container and key should follow repository conventions.

### Requirements

- row width is configurable for functional tests;
- small widths such as 4, 8, 16, or 32 lanes are sufficient initially;
- all data read by a test must be explicitly initialized;
- allocation does not imply zero initialization;
- no timing or open-row state is stored here.

Do not add symbolic/undefined values in the first version. Tests should initialize every row that can be read.

---

## 5. Functional Semantics

The functional simulator implements only the visible data transformation of each existing request.

### 5.1 RowCopy

The existing RowCopy request already supports one source and one or more destinations.

```text
for every destination:
    dst[:] = original_src[:]
```

Requirements:

- source is preserved;
- all destinations receive the same original source value;
- multi-destination behavior is handled by the existing ordered operand list.

### 5.2 MAJ3

For each modeled lane:

```text
m = MAJ3(x, y, z)
```

Apply the accepted destructive behavior of the existing primitive:

```text
x[:] = m
y[:] = m
z[:] = m
```

If repository documentation establishes a different visible request-level behavior, follow that authority instead of inventing one.

### 5.3 MAJ5

For each modeled lane:

```text
m = MAJ5(v, w, x, y, z)
```

Apply the accepted destructive behavior to all participating rows.

### 5.4 NOT

For the existing in-place NOT request:

```text
src[:] = ~original_src[:]
```

No timing/electrical NOT phases are modeled.

### 5.5 NOT_COPY

For the PRADA-derived fused request:

```text
inverted = ~original_src[:]

src[:] = inverted
dst[:] = inverted
```

This must reflect the visible effect of:

```text
ACT_PUD_S_OC(src) -> N -> ACT_PUD(dst) -> PREpb
```

without modeling those commands individually.

### 5.6 Deferred movement interpretation

LC-MOV and GB-MOV functional interpretation is deferred. Their timing
simulation remains available and unchanged.

---

## 6. Movement Mapping Boundary

The Accepted [movement addressing decision](../decisions/mimdram-movement-addressing-geometry-and-payload.md)
intentionally treats Column as an opaque selector. The functional mapping from
`(logical mat, Column selector, HFF position)` to row-bit/lane positions is
unresolved. Payload width alone does not determine the selected functional bits.

This does not block functional validation of PRADA-based arithmetic using the
five whole-row primitives. Movement functional semantics will be added only
after a separate mapping decision is accepted. This version rejects LC-MOV and
GB-MOV; it adds no placeholder behavior, alias/modulo rules, layout abstraction,
or Request metadata and does not change accepted movement addressing semantics.

---

## 7. Execution Model

Execution is a deterministic sequential interpreter.

Conceptually:

```cpp
class PuDFunctionalSimulator {
public:
    void execute(const Request& request);
    void execute(const std::vector<Request>& requests);

    FunctionalMemory& memory();
    const FunctionalMemory& memory() const;
};
```

Exact names are not requirements.

For the first version:

```text
request 0
-> update FunctionalMemory
request 1
-> update FunctionalMemory
...
```

Do not implement:

- timing;
- scheduler behavior;
- request reordering;
- concurrency;
- asynchronous completion;
- bank ownership;
- refresh.

Those are deliberately left to Ramulator2.

---

## 8. Bitslice Test Helpers

Provide only small helpers needed to initialize and inspect functional tests.

Useful operations:

```text
write integer/vector values into bit-plane rows
read bit-plane rows back into integer/vector values
fill a row with 0 or 1
compare a decoded result with a host reference
```

These are test utilities, not new PuD requests.

Do not introduce a general data-layout or transposition framework in this task.

---

## 9. Validation

### 9.1 Primitive tests

Add focused functional tests for:

```text
RowCopy
  - single destination
  - multiple destinations
  - source preservation

MAJ3
  - majority truth behavior
  - destructive participant update

MAJ5
  - majority truth behavior
  - destructive participant update

NOT
  - in-place inversion

NOT_COPY
  - source becomes inverted
  - destination receives the same inverted value
```

### 9.2 First sequence-level integration test

Use the exact 11-step PRADA Table 2 two-bit ADD sequence supplied by the user
as the first composition test. Preserve its operand and execution order; the
table's numbering typo does not define execution semantics. Cover all 16 input
pairs. This is a fixed fixture, not an alternative adder or an ADD generator.

Construct the request sequence using the **existing request types**, including:

```text
multi-destination RowCopy
MAJ3
NOT_COPY
MAJ5
```

Initialize the example's bitsliced input/data/temporary/constant rows, execute the request sequence through the functional simulator, decode the result, and compare against an independent host-side integer ADD oracle.

This test should verify at least:

- final result;
- carry/result rows;
- source preservation where the sequence requires it;
- destructive compute-row updates at selected intermediate points.

Do not implement a general INT ADD generator in this task. The test may construct the known 2-bit sequence directly.

### 9.3 Existing timing tests remain independent

Do not add functional checks into the existing timing microbenchmarks unless a tiny shared test helper is clearly appropriate.

The existing Ramulator2 tests continue to validate:

```text
request -> command sequence -> timing/state
```

The new tests validate:

```text
request -> data transformation
```

---

## 10. Repository Integration

Keep the functional simulator local to the PuD extension.

Follow existing repository layout and test conventions after inspection rather than forcing a new directory hierarchy.

The implementation should normally consist of only:

- a small functional memory component;
- a sequential request interpreter;
- bitslice test helpers;
- functional tests.

Do not modify generic Ramulator2 controller/DRAM behavior solely for this feature.

No normal Ramulator2 simulation path needs to invoke the functional simulator automatically.

---

## 11. Explicit Non-Goals

The first version must not add:

- INT8 ADD/MUL implementation;
- FP8 ADD/MUL implementation;
- GEMV/GEMM generation;
- allocator or scratch-row allocator;
- automatic bitslice transposition;
- command-level functional simulation;
- timing or energy modeling;
- scheduler/concurrency modeling;
- CPU/GPU execution;
- host completion;
- quantization/scales/zero-points;
- generalized FP8 semantics;
- symbolic execution;
- full DRAM-capacity storage.

Those are separate later tasks.

---

## 12. README Documentation

Add **one new top-level section at the very end of the repository `README.md`**.

Do not distribute functional-simulator documentation into existing README sections.

Suggested heading:

```markdown
## PuD Functional Simulator
```

The section should briefly state:

1. why the functional simulator exists;
2. that it is separate from Ramulator2 timing/energy simulation;
3. that it interprets the same existing request-level PuD operations;
4. the currently supported requests:
   `RowCopy`, `MAJ3`, `MAJ5`, `NOT`, `NOT_COPY`; note that movement timing exists but functional interpretation awaits an accepted mapping;
5. where the implementation/tests live;
6. the exact build/test command(s) that work after implementation;
7. that higher-level INT8/FP8/GEMV generation is not part of this component.

Keep this README section concise. The detailed design belongs in this document and code/tests, not in the README.

---

## 13. Acceptance Criteria

The task is complete when:

1. the functional simulator directly interprets the existing request representation, or the user has approved a minimal alternative after direct reuse proved unsuitable;
2. all five supported row-level PuD operations have functional semantics;
3. primitive-level functional tests pass;
4. the PRADA-style 2-bit ADD request sequence passes against a host reference;
5. LC-MOV/GB-MOV are rejected without a functional effect; movement mapping remains deferred;
6. existing PuD timing/movement tests still pass unchanged in behavior;
7. no generic Ramulator2 timing/controller architecture was redesigned for the functional simulator;
8. no higher-level INT8/FP8/GEMV implementation was added;
9. `README.md` has one concise `PuD Functional Simulator` section appended at the bottom with working usage/test instructions.

The intended result is **not another DRAM simulator**.

It is a small deterministic interpreter for the data effects of the PuD requests that the existing Ramulator2 PuD timing model already accepts.
