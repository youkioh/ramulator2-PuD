# MIMDRAM Inter-Column Data Movement Technical Reference

## Purpose and evidence policy

This document is the project's curated technical reference for MIMDRAM
inter-column data movement. It records reference-backed architectural facts,
clearly labeled architectural inferences, and unresolved questions.

It is **not** an implementation plan, scope document, or accepted simulator
design specification. A physical mechanism described by a source does not, by
itself, determine how Ramulator2 must represent that mechanism.

This document uses the following evidence classes:

1. **MIMDRAM source fact** — directly stated or shown by Oliveira et al.
2. **Other primary-source fact** — directly supported by FIGARO or another
   primary source.
3. **Architectural inference** — follows from the published organization or
   datapath, but is not directly stated as a requirement by the source.
4. **Unresolved reference/architecture question** — the primary sources do
   not specify enough detail to close the issue.
5. **Unresolved Ramulator representation question** — the physical behavior is
   known well enough to discuss, but its simulator representation remains a
   later project decision.

Two examples are especially important:

- MIMDRAM states that `GB-MOV` activates its source and destination rows in
  different mats concurrently. This is a physical/source fact. It does **not**
  imply that Ramulator2 must explicitly store two active-mat states.
- MIMDRAM states that `LC-MOV` keeps the source data in the mat's HFFs across
  the source `PRE`. This is a physical/source fact. It does **not** imply that
  Ramulator2 must expose a persistent HFF state.

---

## 1. MIMDRAM source facts

### 1.1 Physical mat, subarray, and logical mat terminology

#### Physical mat

MIMDRAM describes a DRAM mat as a two-dimensional array of DRAM cells with
multiple rows and columns. Each mat contains:

- a local row decoder that drives local wordlines;
- local bitlines;
- a row of local sense amplifiers, also called the local row buffer;
- helper flip-flops (`HFFs`) that drive a portion of local-row-buffer data to
  the global bitlines.

The architectural description gives typical mat dimensions of
512–1024 rows by 512–1024 columns.

**Source:** MIMDRAM §2.1, Fig. 1.

#### Subarray

MIMDRAM's architectural description states that a bank contains multiple
DRAM mats and that several mats, e.g. 8–16, are grouped into a DRAM subarray.
A row access to a conventional subarray addresses columns across multiple mats
together; fine-grained DRAM modifies the access circuitry so that smaller mat
segments can be addressed.

**Source:** MIMDRAM §1 and §2.1, Fig. 1.

#### Logical mat ID and logical mat range

For fine-grained PUD execution, the memory controller communicates the first
and last logical mats targeted by an operation as a logical mat range
`[mat_begin, mat_end]`. MIMDRAM restricts a PUD operation to a physically
contiguous set of logical mats. Each DRAM chip determines whether the logical
range includes mats in that chip and translates the logical range into a
physical mat range for its mat selector.

For the logical encoding described in §4.2, MIMDRAM uses 14 bits for a logical
mat range, with 7 bits for `mat_begin` and 7 bits for `mat_end`. Each 7-bit
logical mat identifier is divided as follows:

- the three most-significant bits identify the DRAM chip;
- the four least-significant bits identify individual mats.

MIMDRAM's evaluated configuration separately reports:

- 8 DRAM chips;
- 16 mats/chip;
- 1K rows/mat;
- 512 columns/mat;
- 4 HFFs/mat.

**Sources:** MIMDRAM §4.2, "Encoding MAT Information"; MIMDRAM Table 2.

These two descriptions are recorded separately here. MIMDRAM §2.1 describes a
physical hierarchy in which a bank contains many mats and several mats form a
subarray, while §4.2/Table 2 use an 8-chip × 16-mat/chip logical/evaluated
organization. The paper does not fully explain how these descriptions map onto
one another; that ambiguity is preserved in §4.

### 1.2 Fine-grained mat access structures

MIMDRAM adds three structures for fine-grained PUD execution:

- **mat isolation transistor** — segments the global wordline connection to
  the local row decoder in each mat;
- **row decoder latch** — stores the address bits used by a mat's local row
  decoder;
- **mat selector** — asserts the isolation transistors for the selected
  physical mat range.

In MIMDRAM's example, a TRA can target only `mat0`. The row decoder latch keeps
the local row address for the activation in `mat0`, allowing the memory
controller to issue a TRA to another mat while `mat0` is being activated.

MIMDRAM §4.2 also introduces a per-chip mat queue plus `ACT-enqueue`,
`PRE-enqueue`, and `ACT-dequeue` variants to communicate mat-range information
around the deterministic `ACT`/`PRE` sequence of a PUD μProgram. This is a
source fact about MIMDRAM's general mat-information transport mechanism. The
LC-MOV and GB-MOV walkthroughs do not separately spell out how each internal
activation uses these queueing variants.

MIMDRAM §4.2 describes its control unit as orchestrating independent PUD
operations concurrently across the mats of a DRAM subarray. Its mat scoreboard
tracks whether mats targeted by a PUD operation are available. MIMDRAM's §8.5
area analysis states that this scoreboard requires 128 bits, one bit per DRAM
mat per subarray. Separately, §8.4 evaluates MIMDRAM while varying the number of
DRAM subarrays used for PUD computation from 1 to 64 per bank.

These statements describe physical/control behavior in MIMDRAM. They do not
determine the simulator state or command representation.

**Sources:** MIMDRAM §4.1, "Fine-Grained PUD Execution", Fig. 4; MIMDRAM §4.2,
"Communicating MAT Information", "Timing of MAT Information", and control-unit
description; MIMDRAM §8.4; MIMDRAM §8.5.

### 1.3 High-level data-movement instruction

At the ISA level, MIMDRAM exposes:

```text
bbop_mov dst, dst_idx, src, src_idx, size, n
```

where `src` and `dst` identify arrays, `src_idx` and `dst_idx` identify the
first elements to move, `size` is the number of elements to move, and `n` is
the number of bits per element.

The MIMDRAM control unit derives the targeted mat range from the source and
destination array locations, indices, and movement size. The paper states that
the control unit translates the operation into `LC-MOV` when source and
destination mats are the same, and into `GB-MOV` otherwise.

This ISA-level statement does not, by itself, resolve the physical routing of
an arbitrary source/destination pair.

**Source:** MIMDRAM §6.1, Table 1, "Data Move".

### 1.4 LC-MOV: local I/O movement within a mat

#### Function and operands

`LC-MOV` is MIMDRAM's intra-mat inter-column movement command. The command
takes:

1. the logical mat range `[mat_begin, mat_end]` of the target row;
2. source row address `row_src` and source column address `column_src`;
3. destination row address `row_dst` and destination column address
   `column_dst`.

The worked mechanism moves four bits from `(row_src, column_src)` to
`(row_dst, column_dst)` within `mat_M`.

**Source:** MIMDRAM §4.1, "Local I/O Data Movement", Fig. 5.

#### Physical datapath and participating structures

MIMDRAM observes that the local bitlines of a mat already share a path through
the column select logic and the HFFs. `LC-MOV` uses that existing local path;
the paper states that no additional hardware modification is required for the
intra-mat interconnect.

The physical structures involved in the described operation include:

- target mat's local row decoder and wordlines;
- local bitlines;
- local sense amplifiers / local row buffer;
- column select logic;
- HFFs;
- the fine-grained mat-selection structures used to target the mat range.

The data-movement path described by Fig. 5 is local to the mat; it does not use
the added neighboring-global-SA datapath used by `GB-MOV`.

**Source:** MIMDRAM §4.1, "Local I/O Data Movement", Fig. 5.

#### Source phase

The memory controller performs:

```text
ACT(row_src) -> RD(column_src) -> PRE
```

on the source location.

1. `ACT` loads `row_src` into the mat's local sense amplifiers.
2. `RD` selects the four-bit `column_src` through the column select logic and
   moves those four bits into the HFFs.
3. The HFF enable signal transitions high so that the HFFs latch and amplify
   the selected data.
4. `PRE` closes the source row.

MIMDRAM states that this proceeds like a regular `ACT-RD-PRE` sequence up to
this point, except for the HFF-enable behavior described next.

**Source:** MIMDRAM §4.1, "Local I/O Data Movement", Fig. 5.

#### Persistent physical condition across source PRE

Unlike a regular `ACT-RD-PRE`, `LC-MOV` does **not** lower the HFF enable signal
when the source `RD` finishes. Therefore the selected four-bit source value
remains in the HFFs after the source row is closed by `PRE`.

This HFF retention across `PRE` is a physical/source fact. It does not decide
whether a simulator must model an explicit persistent HFF state.

**Source:** MIMDRAM §4.1, "Local I/O Data Movement", Fig. 5.

#### Destination phase

The memory controller then performs:

```text
ACT(row_dst) -> WR(column_dst) -> PRE
```

on the destination location.

1. `ACT` loads `row_dst` into the mat's local row buffer.
2. `WR` asserts the column select logic for `column_dst`, creating a path
   between the HFFs and the local row buffer.
3. Because the HFF enable remains high, the HFFs do not latch the existing
   destination-column value. Instead, the retained source value overwrites the
   destination local sense-amplifier state.
4. The new value propagates through the local bitlines and is written to the
   destination cells.

**Source:** MIMDRAM §4.1, "Local I/O Data Movement", Fig. 5.

#### Transfer granularity

The worked MIMDRAM organization moves four bits per `LC-MOV`. MIMDRAM
explicitly ties the movement width to the number of HFFs already present in a
mat and assumes four HFFs per mat based on prior fine-grained-DRAM work.

Thus, "four bits" is the source-reported granularity for the evaluated
organization, not a technology-independent constant.

**Source:** MIMDRAM §4.1, footnote 5.

#### Source-reported latency

For the conservative worst case in which source and destination row addresses
differ, MIMDRAM reports:

```text
T_LC-MOV = 2 * (tRAS + tRP) + tRELOC + tWR
```

MIMDRAM uses:

- `tRAS` for row activation/restoration;
- `tRP` for precharge/recovery;
- `tWR` for the required interval between a write and precharge;
- `tRELOC` as the relocation/connection timing term cited to FIGARO.

The equation is a source fact. It does not specify how a cycle-accurate
simulator must decompose the aggregate interval into independently scheduled
commands or timing edges.

**Source:** MIMDRAM §4.1, "Local I/O Data Movement".

### 1.5 GB-MOV: global I/O movement across mats

#### Function and operands

`GB-MOV` is MIMDRAM's inter-mat inter-column movement command. The command
takes separate source and destination location information.

Source:

- logical mat range `[mat_begin, mat_end]`;
- source row address `row_src`;
- source column address `column_src`.

Destination:

- logical mat range `[mat_begin, mat_end]`;
- destination row address `row_dst`;
- destination column address `column_dst`.

The worked example moves four bits from `(row_src, column_src)` in
`mat_(M-2)` to `(row_dst, column_dst)` in `mat_(M-1)`.

**Source:** MIMDRAM §4.1, "Global I/O Data Movement", Fig. 4.

#### Added inter-mat datapath

MIMDRAM adds a 2:1 multiplexer to the input/output port of each set of four
one-bit sense amplifiers in the global row buffer. For a destination global-SA
set `SA_i`, the multiplexer selects whether its input comes from:

- the conventional I/O bus; or
- the neighboring global-SA set `SA_(i-1)`.

This is the hardware modification that creates the inter-mat path described by
MIMDRAM.

**Source:** MIMDRAM §4.1, "Global I/O Data Movement", Fig. 4.

#### Physical datapath and participating structures

The described `GB-MOV` datapath is:

```text
source cells
  -> source local bitlines
  -> source local sense amplifiers / local row buffer
  -> source column select logic
  -> source HFFs
  -> source global-SA set
  -> added neighboring-global-SA mux/path
  -> destination global-SA set
  -> destination HFFs
  -> destination local sense amplifiers / local row buffer
  -> destination local bitlines
  -> destination cells
```

The participating structures therefore include:

- fine-grained mat-selection structures for both locations;
- source and destination local row decoders / wordlines;
- source and destination local bitlines and local sense amplifiers;
- source and destination column-select/HFF paths;
- global bitlines / global row-buffer sense-amplifier sets;
- the added 2:1 multiplexer / neighboring global-SA path.

The transferred data stays inside the DRAM chip datapath described by MIMDRAM;
the destination `WR` selects the added global-SA path instead of the
conventional I/O-bus input.

**Source:** MIMDRAM §4.1, "Global I/O Data Movement", Fig. 4.

#### Physical command/phase sequence

MIMDRAM describes three main steps:

1. The memory controller issues an `ACT` to the source row and, concurrently,
   an `ACT` to the destination row in the other mat.
2. A source `RD(column_src)` loads the selected four-bit source column into the
   source HFFs, which drive the corresponding source global-SA set.
3. A destination `WR(column_dst)` selects the added neighboring-global-SA path.
   Data in the source global-SA set is loaded into the destination global-SA
   set, which drives the destination HFFs and local sense amplifiers. The local
   sense amplifiers restore the destination local bitlines and cells.

The source-reported latency equation also includes `tRP`, i.e. a final
precharge/recovery interval before the bank is ready for another row
activation.

**Source:** MIMDRAM §4.1, "Global I/O Data Movement", Fig. 4.

#### Persistent/intermediate physical conditions

During the described `GB-MOV` transfer, source and destination rows in
different mats are concurrently activated. After the source `RD`, the selected
source value is present in the source HFF/global-SA path and is then consumed
by the destination `WR`.

These are physical conditions of the described sequence. They do not decide
whether Ramulator2 must expose separate active-mat states, explicit
global-SA-held data, or any other persistent simulator state.

**Source:** MIMDRAM §4.1, "Global I/O Data Movement".

#### Transfer granularity

The worked organization moves four bits per `GB-MOV`, again because MIMDRAM
assumes four HFFs per mat. The paper states that the inter-mat transfer width
depends on the number of HFFs present in a mat.

**Source:** MIMDRAM §4.1, footnote 5.

#### Source-reported latency

For the conservative worst case in which source and destination row addresses
differ, MIMDRAM reports:

```text
T_GB-MOV = tRAS + tRELOC + tWR + tRP
```

The paper attributes the lower aggregate latency relative to `LC-MOV` to the
source and destination row activations occurring concurrently.

**MIMDRAM source fact:** GB-MOV physically overlaps, or concurrently performs,
source and destination row activation sufficiently for the source-reported
latency relation to contain one `tRAS` activation interval.

**Unresolved source detail:** MIMDRAM does not establish whether the
corresponding ACT commands occupy the same C/A cycle, successive C/A cycles,
or another exact issue relationship.

This equation is a source fact. It does not by itself determine a Ramulator
command graph or timing-resource model.

**Source:** MIMDRAM §4.1, "Global I/O Data Movement".

### 1.6 Relevance to vector reduction

MIMDRAM §4.1.1 uses both movement mechanisms for
`out += (A[i] + B[i])`.

In the paper's two-mat example:

1. MIMDRAM performs PUD addition in both mats and stores partial output
   `C = {C[0]_mat0, C[1]_mat1}`.
2. `GB-MOV` repeatedly copies the `C[0]` portion from `mat0` into a temporary
   row in `mat1`, four bits / four data elements at a time.
3. MIMDRAM performs `tmp + C[1]` in `mat1`, leaving the combined temporary
   output in one mat.

After this inter-mat stage, the paper states that the temporary output in one
mat contains as many data elements as there are columns in that mat, e.g.
512 elements. MIMDRAM then uses the intra-mat interconnect and `LC-MOV` to
implement an adder tree inside that mat, reducing the temporary vector to an
output vector with four data elements.

The number of `GB-MOV` and `LC-MOV` commands depends on operand bit precision.

**Source:** MIMDRAM §4.1.1, Fig. 6 and footnote 6.

The paper does not specify a subsequent `4 -> 1` mechanism in the described
adder-tree discussion; this remains an unresolved architecture question in
§4.

---

## 2. Facts supported by FIGARO or another primary source

### 2.1 FIGARO's global-row-buffer relocation mechanism

FIGARO operates at a different physical scope from MIMDRAM movement. FIGARO
moves one selected column from the local row buffer of one subarray to the
local row buffer of another subarray in the same bank through the shared
global row buffer.

For an x8 DRAM chip, FIGARO describes a 64-bit global row buffer. With eight x8
chips operating in lockstep, a rank-level `RELOC` moves one 64-byte cache
block.

**Source:** FIGARO §2 and §4.1, Fig. 3 and Fig. 4.

### 2.2 FIGARO RELOC datapath

FIGARO's source-backed sequence is:

1. `ACTIVATE` the source row, loading it into the source local row buffer.
2. Issue `RELOC`, which selects a source local-row-buffer column, loads it into
   the shared global row buffer, and connects the global row buffer to a
   destination local-row-buffer column.
3. `ACTIVATE` the destination row, overwriting only the column whose local
   sense amplifiers were driven by the relocated value.
4. `PRECHARGE` the bank.

FIGARO allows multiple `RELOC` commands while the source row remains active,
copying multiple columns before the destination activation.

**Source:** FIGARO §4.1, Fig. 4.

### 2.3 FIGARO's drive-strength observation

FIGARO relies on the global row buffer having higher drive strength than the
local row buffer. The global row buffer can therefore perturb a precharged
destination local bitline enough for the destination local sense amplifiers to
sense and amplify the transferred value.

MIMDRAM explicitly cites FIGARO for the same general observation when
motivating its global-I/O movement path.

**Sources:** FIGARO §4.1; MIMDRAM §4.1, footnote 4.

### 2.4 FIGARO RELOC timing

FIGARO performs SPICE-level analysis using a 22 nm DRAM model and reports:

```text
raw RELOC latency       = 0.57 ns
guardbanded tRELOC      = 1 ns
```

FIGARO adds a conservative 43% guardband to the worst-case simulated result.
Its reported total latency to relocate one column is 63.5 ns, corresponding to
two `ACTIVATE`s, one `RELOC`, and one `PRECHARGE`.

**Source:** FIGARO §4.2, Fig. 5.

The 63.5 ns FIGARO operation is not the latency equation MIMDRAM reports for
either `LC-MOV` or `GB-MOV`; MIMDRAM instead uses a `tRELOC` term in its own
movement equations.

---

## 3. Architectural inferences

The statements in this section are deliberately **not** classified as
MIMDRAM source facts.

### 3.1 FIGARO does not directly validate the exact MIMDRAM movement paths

FIGARO's SPICE-validated mechanism is an inter-subarray
`LRB -> GRB -> LRB` relocation. MIMDRAM `GB-MOV` uses an inter-mat path that
adds a neighboring connection between global-SA sets, while `LC-MOV` uses the
local HFF/column-select path inside one mat.

Therefore, FIGARO's `tRELOC` provides a primary-source timing basis for a
related global-row-buffer transfer mechanism, but FIGARO is not a direct
circuit validation of MIMDRAM's exact `GB-MOV` or `LC-MOV` datapath.

### 3.2 The depicted GB-MOV hardware does not provide a cross-chip datapath

The `GB-MOV` interconnect shown by MIMDRAM connects neighboring global-SA sets
inside a DRAM chip. The paper does not depict a corresponding data path
between separate DRAM chips.

Therefore, cross-chip `GB-MOV` is not supported by the described physical
interconnect. This conclusion follows from the depicted connectivity rather
than from an explicit sentence in MIMDRAM stating "GB-MOV cannot cross chips."

### 3.3 The direct GB-MOV connection shown is a neighboring connection

MIMDRAM explicitly describes the destination global-SA set `SA_i` as selecting
data from neighboring set `SA_(i-1)` and illustrates movement from
`mat_(M-2)` to `mat_(M-1)`.

It is therefore not justified to reinterpret the published datapath as an
arbitrary all-to-all mat crossbar. The paper does not establish whether an
arbitrary non-neighbor move is performed by repeated hops, by another
unreported path, or is disallowed.

### 3.4 Physical persistence does not imply simulator-visible persistence

Two important examples follow from the source descriptions:

- In `LC-MOV`, the HFF-held value physically survives the source `PRE`.
- In `GB-MOV`, source and destination rows are physically active
  concurrently for part of the operation.

These conditions may matter to legality or interference if internal phases are
made observable to other operations. They do not, by themselves, establish
the state granularity of a simulator that may instead treat a movement as a
compound operation.

### 3.5 The 128-entry control/scheduling mat set is better supported as subarray-scoped

MIMDRAM describes independent PUD operations as executing across mats within a
DRAM subarray, sizes the mat scoreboard as 128 bits with one bit per DRAM mat
per subarray, and separately evaluates multiple subarrays per bank.

Taken together, these source facts make a subarray-scoped interpretation of the
128-entry control/scheduling mat set better supported than one bank-wide
128-entry interpretation. This is an architectural inference, not a direct
source statement that the 7-bit logical mat namespace definitively enumerates
one physical subarray. It does not resolve the exact mapping from logical mat
IDs to physical mats, the complete relationship between the §2.1 physical
hierarchy and the logical/evaluated organization, or the physical DDR4
row-address-to-subarray mapping.

---

## 4. Unresolved reference / architecture questions

These questions are intentionally left unresolved because the cited primary
sources do not provide enough information to close them.

1. **How should the physical hierarchy in §2.1 be reconciled with the
   evaluated/logical organization?**
   - §2.1 says a bank contains many mats and several mats form a subarray.
   - §4.2/Table 2 use 8 chips and 16 mat identifiers per chip in the described
     logical/evaluated organization.
   - The paper does not fully specify the mapping between these two
     descriptions.

2. **What physical domain does the 7-bit logical mat namespace enumerate?**
   - The encoding includes chip bits and mat bits.
   - Subarray-scoped execution and the one-scoreboard-bit-per-mat-per-subarray
     evidence make a subarray-scoped control/scheduling interpretation better
     supported than a single bank-wide interpretation.
   - The exact relationship among logical mat ID, bank, subarray, and every
     physical mat in the full device is not completely specified.

3. **What are the exact semantics of an LC-MOV logical mat range containing
   more than one mat?**
   - The command accepts a logical mat range.
   - The detailed walkthrough explains a move inside a single `mat_M`.
   - The paper does not explicitly define whether the same local movement is
     performed in parallel in every mat in a multi-mat range.

4. **How are GB-MOV source and destination ranges paired?**
   - `GB-MOV` accepts separate logical source and destination ranges.
   - The detailed circuit example shows one neighboring pair.
   - The paper does not fully define the pairing rule for wider ranges.

5. **What is the supported reachability for non-neighbor GB-MOV targets?**
   - The physical connection shown is `SA_(i-1) -> SA_i`.
   - The paper does not specify a multi-hop protocol or another direct route
     for arbitrary non-neighbor source/destination mats.

6. **How does the high-level `bbop_mov` "same mat -> LC-MOV, otherwise ->
   GB-MOV" rule interact with physical reachability?**
   - The ISA description gives this translation rule.
   - The hardware description does not explain how every possible
     "otherwise" mapping is realized by the depicted neighboring interconnect.

7. **What exact precharge scope is intended for the internal movement
   sequences?**
   - MIMDRAM describes mat-selective activation and separately describes
     `ACT-enqueue`, `PRE-enqueue`, and `ACT-dequeue` for PUD μPrograms.
   - The LC/GB movement descriptions do not fully specify which physical
     structures a movement-related `PRE` closes when multiple mats or
     independent operations are active.

8. **How exactly are the general mat-queue command variants used by LC-MOV and
   GB-MOV?**
   - §4.2 defines `ACT-enqueue`, `PRE-enqueue`, and `ACT-dequeue` for
     deterministic PUD μPrograms.
   - §4.1 describes LC-MOV and GB-MOV using `ACT`, `RD`, `WR`, and `PRE`
     terminology without a separate movement-specific mat-queue walkthrough.

9. **How is the four-element output of the intra-mat reduction converted to a
   scalar?**
   - MIMDRAM describes the LC-MOV adder tree down to four data elements.
   - The cited vector-reduction description does not provide a further
     `4 -> 1` mechanism.

10. **How accurately does FIGARO-derived `tRELOC` model each MIMDRAM path?**
   - MIMDRAM reports equations containing `tRELOC`.
   - FIGARO provides SPICE evidence for a related, but physically different,
     inter-subarray relocation path.
   - MIMDRAM does not present an equivalent circuit-level validation of both
     its LC-MOV and GB-MOV paths in the cited sections.

---

## 5. Unresolved Ramulator representation questions

The questions below are simulator questions, not source facts and not accepted
project decisions.

1. **Geometry representation**
   - Should subarray and mat become explicit Ramulator hierarchy levels, be
     represented as substrate-internal resources, or be derived from another
     representation?

2. **Logical mat metadata**
   - Should a logical mat ID/range live in request metadata, address vectors,
     command metadata, or be derived from a separately defined mapping?

3. **Movement operation boundary**
   - Should an externally visible movement correspond to `bbop_mov`,
     `LC-MOV`/`GB-MOV`, one four-bit physical transfer, or another abstraction?

4. **Internal command granularity**
   - Should `ACT`, `RD`, `PRE`, `ACT`, `WR`, `PRE` phases of `LC-MOV` be
     independently schedulable simulator commands or internal phases of a
     compound operation?
   - Should the two activations, source `RD`, destination `WR`, and recovery of
     `GB-MOV` be independently visible?

5. **LC-MOV HFF retention**
   - Does the chosen command abstraction require explicit HFF-held state
     across the source `PRE`, or can the retained value remain internal to a
     compound movement representation?

6. **GB-MOV concurrent activation**
   - Does the chosen abstraction require explicit source and destination
     active-row state for separate mats, or can concurrent activation remain
     internal to a compound movement representation?

7. **Intermediate I/O-path state**
   - Must HFF, global-SA, column-select, or neighboring-link occupancy be
     explicit simulator state/resources, and at what granularity?

8. **Mat-information transport**
   - Should MIMDRAM's mat queue and `ACT-enqueue`, `PRE-enqueue`,
     `ACT-dequeue` behavior be represented explicitly, abstracted into command
     metadata, or hidden inside a higher-level operation?

9. **Placement, timing/resource, and ownership scopes**
   - What source/destination placement is legal?
   - Which physical structures constrain concurrency?
   - What, if any, request-level isolation is needed?
   - These three scopes must not be inferred to be identical merely because
     the physical movement uses the same mats.

10. **Interleaving**
    - Which ordinary DRAM operations, existing PUD operations, or other
      movements may execute while an LC-MOV or GB-MOV is between physical
      phases?

11. **Precharge and refresh interaction**
    - How should ordinary precharge, refresh, and maintenance interact with
      movement phases and with any physical condition that remains live
      between phases?

12. **Timing representation**
    - How should the source-reported aggregate latency equations be translated
      into cycle-accurate timing constraints once the simulator command
      boundaries and target DRAM timing preset are chosen?

13. **GB-MOV routing representation**
    - If non-neighbor movement is later supported by an accepted
      interpretation, is it represented as repeated physical hops or as some
      other abstraction?
    - No answer should be assumed before the reference reachability question
      in §4 is resolved.

### Existing project mapping note

The current project documentation records an existing DDR4_PuD simulator
mapping such as:

```text
subarray_id = row / 1024
local_row   = row % 1024
```

That mapping is an existing simulator assumption, not a MIMDRAM source fact.
This technical reference does not establish that mapping as the representation
for MIMDRAM movement.

---

## References

### MIMDRAM

G. F. Oliveira, A. Olgun, A. G. Yaglikci, F. N. Bostanci,
J. Gomez-Luna, S. Ghose, and O. Mutlu,
**"MIMDRAM: An End-to-End Processing-Using-DRAM System for
High-Throughput, Energy-Efficient and Programmer-Transparent
Multiple-Instruction Multiple-Data Computing,"**
HPCA 2024.

Relevant sections used by this reference:

- §1 — fine-grained DRAM motivation and mat-level execution;
- §2.1 — DRAM organization and mat/subarray terminology;
- §4.1 — fine-grained PUD execution, `GB-MOV`, and `LC-MOV`;
- §4.1.1 — PUD vector reduction;
- §4.2 — logical mat encoding/ranges and mat-information communication;
- §6.1 — `bbop_mov`;
- §8.4 — evaluation across 1–64 DRAM subarrays per bank;
- §8.5 — mat-scoreboard storage and area;
- Table 2 — evaluated DRAM configuration.

### FIGARO

Y. Wang et al.,
**"FIGARO: Improving System Performance via Fine-Grained In-DRAM Data
Relocation and Caching,"**
MICRO 2020.

Relevant sections used by this reference:

- §2 — LRB/GRB organization and conventional column access;
- §4.1 — `RELOC` datapath and global-row-buffer drive-strength observation;
- §4.2 — SPICE methodology and `0.57 ns` / guardbanded `1 ns` `RELOC`
  timing.
