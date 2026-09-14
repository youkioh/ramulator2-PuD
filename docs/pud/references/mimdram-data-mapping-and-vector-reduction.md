# MIMDRAM Data Mapping and Vector Reduction

## Purpose and evidence boundary

This is the source-of-truth reference for the MIMDRAM data organization,
compiler mapping, and vector-reduction mechanisms relevant to future PuD GEMV
functional generation. It is not an implementation plan or a simulator design
decision.

The document uses three evidence classes:

1. **MIMDRAM source fact** — stated or shown by Oliveira et al.
2. **Direct implication** — follows by combining stated MIMDRAM facts, but is
   not itself presented by the paper as a separate mechanism or schedule.
3. **Not specified by MIMDRAM** — information the cited source does not fix.

The one section headed **Existing accepted project policy** reports an already
Accepted repository decision only so that it cannot be mistaken for a source
fact. It introduces no new project choice.

## Primary and related sources

- Oliveira et al., [*MIMDRAM: An End-to-End Processing-Using-DRAM System for
  High-Throughput, Energy-Efficient and Programmer-Transparent
  Multiple-Instruction Multiple-Data Computing*](https://ghose.web.illinois.edu/papers/24hpca_mimdram.pdf),
  HPCA 2024. Relevant material: §§1, 2.1, 2.2, 4.1, 4.1.1, 4.2, 5,
  6.1, 6.2, and 6.3; Figures 1, 2, 4, 5, 6, 7, and 8; Tables 1 and 2.
- Oliveira et al., [arXiv extended version, v2](https://arxiv.org/abs/2402.19080).
  The functional mapping and reduction material uses the same section and
  figure numbering cited below.
- [MIMDRAM geometry](mimdram-geometry.md) curates the evaluated organization.
- [MIMDRAM inter-column data movement](mimdram-inter-column-data-movement.md)
  is the detailed authority for LC-MOV/GB-MOV circuitry, command phases,
  latency equations, and unresolved movement-interface questions. This
  reference repeats only the functional movement facts needed to understand
  mapping and reduction.

No MIMDRAM paper PDF is tracked in the current repository history. The
repository's Accepted geometry decision points to the official HPCA PDF above;
the facts below were cross-checked against that PDF and the arXiv extended
version rather than attributed to a nonexistent local copy.

---

## 1. Bit-serial vertical data organization

### MIMDRAM source facts

MIMDRAM builds on SIMDRAM's vertical data layout. All bits of one logical data
element are placed in one DRAM column. Each data element of a PUD operation is
therefore mapped to a column, and bit-serial operations execute the same step
over many column-resident elements in SIMD fashion. A DRAM subarray acts as a
wide PUD SIMD engine; MIMDRAM narrows the active SIMD extent by selecting only
the required mat or physically contiguous range of mats.

A physical mat is a two-dimensional array with its own row and column extent.
The general architectural description gives 512–1024 rows and 512–1024 columns
per mat. The evaluated configuration uses 1K rows and 512 columns per mat.

**Sources:** MIMDRAM §1; §2.1 and Fig. 1; §2.2 and Fig. 2; §4.1 and
Fig. 4; Table 2.

The concepts must remain distinct:

| Concept | Functional meaning in the source |
| --- | --- |
| Logical vector element | One scalar SIMD lane value. |
| DRAM column | Holds all bits of one vertically laid-out element; columns supply the SIMD lanes. |
| DRAM row | Holds one horizontal slice of bits across many column-resident elements and may also be used for operands, outputs, or computation state. A row is not a vector element. |
| Physical mat | A local two-dimensional row/column array. Its column count bounds the mat-local SIMD width. |
| Logical mat range | The first and last logical mat identifiers supplied for one fine-grained operation; the selected physical mats are contiguous. |
| HFF-width movement unit | The selected physical bits transferred at once through a mat's helper flip-flops; this is not a DRAM row, a mat, or four complete arbitrary-precision elements. |

### Direct implications

- In the evaluated 512-column mat, a mat-local bit-serial operation has up to
  512 element lanes. A selected multi-mat range supplies more lanes by
  composing the columns of its mats; it does not turn a mat into a row or an
  element.
- Because every bit of an element is vertical in one column, different bit
  positions of that element occupy different rows. A PUD arithmetic program
  processes those bit positions serially while operating across columns in
  parallel.
- In the evaluated four-HFF design, one movement transfer carries four
  physical bits. In the vertical layout these can be one current bit position
  from four elements. Moving four complete `n`-bit elements requires work
  across their represented bit positions; MIMDRAM footnote 6 correspondingly
  says that the number of LC-MOV and GB-MOV commands depends on operand
  precision.

### Not specified by MIMDRAM

MIMDRAM does not provide the complete physical mapping from every program
element bit to a vendor DDR4 row, mat, local column, HFF position, DQ, and
burst beat. It also does not prescribe the row allocation of a future
project-specific arithmetic generator.

---

## 2. Fine-grained mat execution

### MIMDRAM source facts

- A fine-grained PUD operation names a logical range
  `[mat_begin, mat_end]`. MIMDRAM permits one operation to address only a
  physically contiguous set of mats. Each chip determines whether the logical
  range intersects that chip and translates the applicable part to a physical
  range for its mat selector.
- All mats in one operation's selected range execute the same ACT–PRE sequence
  and share the operation's control state.
- Independent PUD operations can execute concurrently in different available,
  nonoverlapping mat ranges of one subarray. MIMDRAM's control unit uses the
  mat ranges, scoreboard, and µProgram engines to allocate such work.
- PUD is in situ: memory objects belonging to the same bbop, and objects used
  across dependent instructions, must be placed together and aligned in the
  DRAM mats that perform the computation. The compiler and `pim_malloc`
  machinery described in §3 provide that relationship.

**Sources:** MIMDRAM §4.1, "Fine-Grained PUD Execution," and Fig. 4; §4.2,
"Encoding MAT Information" and Fig. 7; §5; §6.3, "Data Allocation &
Alignment."

### Direct implication

Mat-range selection is the functional execution scope; it is not a statement
that every selected mat contains an independent operation. One dependent bbop
uses aligned operands in its selected range, while distinct independent bbops
may occupy disjoint ranges.

### Not specified by MIMDRAM

The paper does not completely reconcile the physical bank/subarray/mat
hierarchy in §2.1 with the module-wide logical-mat encoding and evaluated
organization in §4.2/Table 2. See the existing [movement reference's logical
mat discussion](mimdram-inter-column-data-movement.md#11-physical-mat-subarray-and-logical-mat-terminology).

---

## 3. Compiler data mapping and allocation

### MIMDRAM source facts

MIMDRAM's LLVM flow has three passes. The mapping behavior relevant here is
mainly in Pass 2 and Pass 3.

**Pass 2: code scheduling and data mapping**

1. The pass receives the bbop instructions produced after code identification
   and builds a data-dependency graph (DDG) for the vectorized instructions.
   Each node is a bbop; incoming edges represent its inputs and outgoing edges
   represent its output.
2. The scheduler traverses the DDG in topological order with a depth-first
   search. It assigns one mat label `i` along the left path and a new label `j`
   along a right subtree.
3. This distributes independent instruction subtrees across mats so they can
   execute concurrently, while keeping dependent instructions on the same mat
   label where the traversal permits it and thereby avoiding unnecessary
   movement.
4. When a right subtree labelled `j` rejoins a parent on label `i`, the
   dependency crosses labels. The compiler inserts a data-movement bbop that
   moves the right-subtree result from `j` to `i` before the parent consumes
   it.

**Source:** MIMDRAM §5, "Pass 2: Code Scheduling & Data Mapping," and
Fig. 8.

**Pass 3 and system allocation**

- Code generation replaces allocation calls associated with bbop operands by
  `pim_malloc(size, mat_label)` and inserts `bbop_trsp_init` for those memory
  objects. The transposition initialization also receives the assigned mat
  label.
- The SIMDRAM-derived transposition unit converts an object's conventional
  horizontal cache-line layout to the vertical layout during LLC writeback and
  converts it back during an LLC read. MIMDRAM transposes only enough data to
  fill the row segment used by the bbop and records the object's mat range in
  the object tracker.
- `pim_malloc` communicates which objects must be placed in the same set of
  mats. Objects with the same label are placed together in a mat set large
  enough for the allocation, and later operands are aligned with an earlier
  allocation for that label.
- MIMDRAM associates each compiler mat label with the physical mat range
  chosen by the allocator in a mat translation table indexed using the label
  and process ID. At bbop dispatch, the CPU looks up and replaces the symbolic
  label with the allocated mat range.
- MIMDRAM's general execution rule requires the allocated range for a PUD
  operation to be physically contiguous.

**Sources:** MIMDRAM §5, "Pass 3: Code Generation," and Fig. 8; §6.2,
"MIMDRAM Transposition Unit"; §6.3, "Data Allocation & Alignment" and
"Mat Label Translation."

### Direct implications

- A **compiler mat label is not a physical mat identifier**. It is a symbolic
  colocation/scheduling label that is later mapped to an allocated physical
  mat range.
- "Same label" can mean a set or range of mats sized for the associated
  allocation, not necessarily one physical mat.
- Compiler-created `bbop_mov` is the explicit bridge when the chosen schedule
  separates a producer and consumer. Its existence does not itself specify a
  legal physical route between all possible source and destination ranges.

### Not specified by MIMDRAM

The paper does not give a complete lowering algorithm from every possible
compiler label pair or `bbop_mov` range to the neighboring physical GB-MOV
connections. It does not define arbitrary routing, reverse movement, or
cross-chip movement merely because the compiler inserted a move.

---

## 4. LC-MOV and GB-MOV functional semantics

This section separates payload movement from the detailed command and timing
sequences, which remain documented in the [inter-column movement
reference](mimdram-inter-column-data-movement.md#14-lc-mov-local-io-movement-within-a-mat).

### 4.1 LC-MOV

**MIMDRAM source facts**

- LC-MOV is intra-mat inter-column movement. Its interface supplies one target
  logical mat range, a source row/column, and a destination row/column.
- Functionally, its worked example copies the selected payload from
  `(row_src, column_src)` to `(row_dst, column_dst)` within the same mat.
- The payload uses the mat-local column-select/HFF/local-I/O path. MIMDRAM
  describes this intra-mat interconnect as using the existing local path rather
  than added inter-mat wiring.
- The evaluated design moves four bits at a time because it assumes four HFFs
  per mat. The width is HFF-dependent, not a universal four-bit constant.

**Source:** MIMDRAM §4.1, "Local I/O Data Movement," Fig. 5, and footnote 5.

### 4.2 GB-MOV

**MIMDRAM source facts**

- GB-MOV is inter-mat inter-column movement. Its interface supplies separate
  source and destination logical mat ranges and a row/column at each endpoint.
- Functionally, the worked example copies the selected payload from
  `(row_src, column_src)` in `mat_(M-2)` to `(row_dst, column_dst)` in
  `mat_(M-1)`.
- The payload traverses the global-I/O path through the source global sense
  amplifiers and the added path to the neighboring destination global-SA set.
  The shown multiplexer lets destination `SA_i` select neighboring
  `SA_(i-1)` instead of the conventional I/O bus.
- The evaluated design moves four bits at a time because it assumes four HFFs
  per mat. Again, the width depends on HFF count.

**Source:** MIMDRAM §4.1, "Global I/O Data Movement," Fig. 4, and footnote 5.

### Direct implications and source limits

- LC-MOV changes a location within a mat; GB-MOV changes a location across
  mats. Neither operation is itself an arithmetic reduction.
- The depicted GB connection directly supports a neighboring forward edge
  `SA_(i-1) -> SA_i`. The source does not depict a reverse edge, an all-to-all
  router, or a cross-chip payload path.
- Both published command interfaces include ranges, but their detailed worked
  examples show a singleton LC target and one neighboring GB pair. The paper
  does not fully specify multi-mat LC lockstep semantics, GB range pairing,
  non-neighbor routing, or arbitrary `bbop_mov` lowering.
- Under vertical layout, the four-bit transfer is one HFF-width physical
  payload, not four complete multi-bit values. Full-element movement repeats
  across the represented precision as required.

---

## 5. MIMDRAM vector reduction

### 5.1 Source-described two-mat example

**MIMDRAM source facts**

MIMDRAM §4.1.1 and Figure 6 explicitly assume that DRAM has **only two mats**
and that the input arrays are evenly distributed between them. The example is
`out += (A[i] + B[i])` and has three inter-mat stages:

1. Execute the vector addition independently over the data in both mats and
   store each partial vector where it was computed:

   ```text
   C = { C[0] @ mat0, C[1] @ mat1 }
   ```

2. Repeatedly issue GB-MOV to copy `C[0]` from `mat0` into temporary row
   `tmp` in `mat1`, four bits—described in this reduction example as four data
   elements—at a time. Repeat until all elements of `C[0]` have been copied.

3. After those moves finish, execute the final PUD arithmetic operation in
   `mat1` and store the result in `out` there:

   ```text
   out = tmp + C[1]
   ```

After the inter-mat stage, the one remaining temporary vector has as many
elements as the number of columns in a mat, e.g. 512. MIMDRAM then uses the
intra-mat interconnect and LC-MOV to implement an adder tree inside that mat,
reducing the mat-width vector toward the four-element movement granularity.
The number of LC-MOV and GB-MOV commands depends on operand precision.

**Source:** MIMDRAM §4.1.1, Fig. 6, and footnote 6.

**Not specified by MIMDRAM:** the cited description stops at four output
elements and does not give a further `4 -> 1` mechanism. It also does not give
the exact LC-MOV/ADD row program or command counts for the intra-mat tree.

### 5.2 More than two mats

#### Source facts

- MIMDRAM permits a PUD operation to target a physically contiguous mat range
  and permits independent operations in different available ranges.
- The depicted GB hardware connects a global-SA set to its neighboring set;
  the GB-MOV interface names source and destination ranges, while its worked
  hardware example shows one neighboring pair.
- `bbop_mov` names arrays, start indices, element count, and precision. The
  control unit derives ranges and chooses LC-MOV for same-mat endpoints or
  GB-MOV otherwise.
- Figure 6 specifies the reduction sequence only for two mats. Neither §4.1.1
  nor the paper's compiler, ISA, allocation, or control sections state an
  exact reduction schedule for `K > 2` contributing mats.

**Sources:** MIMDRAM §§4.1, 4.1.1, 4.2, 5, 6.1, and 6.3; Figs. 4, 6, and 8;
Table 1.

#### Derived mechanism, not a paper-reported schedule

Where a sequence of contributing mat-local fragments is connected by legal
GB-MOV edges, the two-mat primitive can be composed repeatedly:

```text
C0 @ mat0
C1 @ mat1
C2 @ mat2
...
CK-1 @ matK-1

move C0 to mat1
ADD  C0 + C1 -> Acc01 @ mat1

move Acc01 to mat2
ADD  Acc01 + C2 -> Acc012 @ mat2

...

one inter-mat accumulator remains in the last reachable mat
```

This is a derivation from repeated use of MIMDRAM's source-described
"GB-MOV partial vector into the next mat, then ADD" mechanism. It is not an
algorithm or fold order stated by MIMDRAM. It is valid only along actually
supported movement edges and does not imply reverse GB-MOV, arbitrary routing,
or a path across disconnected/chip-local domains.

#### Existing accepted project policy, not a MIMDRAM source fact

The current [reduction placement and movement-lowering
decision](../decisions/mimdram-reduction-placement-and-movement-lowering.md)
selects the derived composition above as a forward fold over consecutive,
reachable mats in each connected linear domain:

```text
GB-MOV C0    -> mat1
ADD C0 + C1  -> Acc01 @ mat1

GB-MOV Acc01     -> mat2
ADD Acc01 + C2   -> Acc012 @ mat2

...

final inter-mat accumulator @ matK-1
LC-MOV + ADD intra-mat tree @ matK-1
```

The exact `K`-mat fold order and sink are project orchestration choices.
MIMDRAM supplies the underlying GB-MOV plus PUD-arithmetic mechanism; this
policy adds no interconnect. The project topology/reduction decision determines
the sink, and consumers must not infer connectivity from numerically adjacent
logical IDs. In the diagram, `mat0` through `matK-1` name consecutive selected
positions in topology order; they need not be local mat IDs beginning at zero.

The accepted special cases and reachability boundary are:

- `K = 1`: perform no inter-mat reduction; use only the source-described
  LC-MOV + ADD intra-mat tree.
- `K = 2`: use the exact Figure 6 source example, with the second mat as sink.
- `K > 2`: repeat the accepted forward-fold composition through consecutive
  reachable mats, then use the source-described intra-mat tree in the sink.
- A chip or other connectivity boundary ends a reduction domain. Do not merge
  domains through an unsupported GB-MOV path, reverse edge, wraparound, or
  invented cross-chip route.
- If selected contributions span disconnected domains, each domain retains
  its own four residual elements after its intra-mat tree. The Accepted project
  policy requires a higher-level host combine; it does not present that combine
  as MIMDRAM GB-MOV behavior.

---

## 6. What MIMDRAM does not define for this use case

The paper does not define any of the following for this project:

- a PRADA INT8 or FP8 primitive sequence;
- an E4M3 FP8 GEMV arithmetic or reduction mapping;
- exact operand, carry, result, or temporary-row allocation for this project's
  generated ADD/MUL programs;
- exact Llama or other GEMV workload dimensions and placement;
- a project-specific host read/write amplification or traffic-accounting model;
- accumulator precision, rounding, overflow, or other INT8/FP8 numerical
  policy;
- an exact `K > 2` reduction schedule;
- an exact LC-MOV/ADD program for the intra-mat tree or a source-described
  final `4 -> 1` scalarization;
- arbitrary, reverse, non-neighbor, or cross-chip GB-MOV routing.

MIMDRAM describes a general SIMDRAM-derived µProgram framework, vertical
transposition, mat-aware allocation, and LC/GB movement. Those mechanisms do
not supply these application- and project-specific choices.

---

## 7. Derived applicability to a future GEMV layer

The source-backed mechanisms support the following high-level functional
shape for future investigation:

```text
per-mat independent arithmetic
    -> inter-mat partial-result movement/reduction with GB-MOV
    -> intra-mat reduction with LC-MOV
```

This applicability is a derivation, not a GEMV mapping selected by MIMDRAM or
by this reference. A later project decision and implementation plan must still
choose the exact GEMV dimensions, `W`/`X` row placement, reduction sink mat,
INT8 versus FP8 accumulation policy, and host-I/O treatment.
