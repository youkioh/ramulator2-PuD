# PuD Operation Generator

This directory is a self-contained generator for symbolic processing-using-DRAM
(PuD) arithmetic traces and opt-in local physical-row lowering. It can be
copied into another repository without any sibling experiment directories.
Generation, lowering, and validation require only Python 3.10 or newer and the
standard library.

The package provides eight operation profiles:

| CLI profile | Inputs | Output | Symbolic primitives |
|---|---|---|---:|
| `uint8-add` | two UINT8 values | exact unsigned 9-bit sum | 50 |
| `uint8-mul` | two UINT8 values | exact UINT16 product | 608 |
| `int8-add` | two INT8 values | exact signed 9-bit sum | 55 |
| `int8-mul` | two INT8 values | exact INT16 product | 628 |
| `fp8-e5m2-add` | two E5M2 bytes | approximate E5M2 candidate | 1,053 |
| `fp8-e5m2-mul` | two E5M2 bytes | truncating E5M2 result | 334 |
| `fp8-e4m3-add` | two E4M3 bytes | approximate E4M3 candidate | 1,339 |
| `fp8-e4m3-mul` | two E4M3 bytes | truncating E4M3 result | 326 |

No round-to-nearest-even (RNE) extension is included.

The symbolic `Builder` trace remains the golden arithmetic program. Physical
lowering preserves its arithmetic-core order, removes only validated terminal
output-export RowCopies, and maps all remaining identities to integer local
physical rows.

## Algorithm provenance

The UINT8 and FP8 arithmetic structures are based on PRADA:

> Hoon Shin, Rihae Park, and Jae W. Lee, “A Processing-using-Memory
> Architecture for Commodity DRAM Devices with Enhanced Compatibility and
> Reliability,” ICCAD 2024, DOI
> [`10.1145/3676536.3676771`](https://doi.org/10.1145/3676536.3676771).

The relationship to PRADA is:

- UINT8 addition uses the majority-based sum/carry structure described in
  Section 5.2 and Table 2. The generator retains the final carry to produce an
  exact 9-bit unsigned result.
- UINT8 multiplication extends the partial-product and column-compression
  structure in Section 5.4 and Table 3 from the illustrated width to eight-bit
  operands.
- E5M2 addition follows the bounded exponent alignment, signed significand
  addition, and normalization flow in Figure 6.
- E5M2 multiplication follows the implicit-one significand product, exponent
  adjustment, and output field selection in Figure 7.
- E4M3 ADD and MUL are width adaptations made in this package. They apply the
  same PRADA dataflow to a three-bit fraction and four-bit exponent; they are
  not claimed to be E4M3 sequences printed by the paper.

Figure identifiers are used here for provenance only. Python identifiers,
trace stages, manifests, and generated filenames use operation-based names.

## How INT8 is derived

PRADA's unsigned arithmetic structure does not by itself specify the signed
microprogram used here. The INT8 profiles are explicit two's-complement
derivations built on the same Boolean primitives.

### INT8 addition

Each eight-bit operand is sign-extended to nine bits, then passed through the
same ripple adder as UINT8. The low nine result bits represent the exact range
`-256..254`; the carry beyond bit 8 is discarded.

For example, adding `-1 + 0` requires sign extension:

```text
A = 11111111 -> 111111111
B = 00000000 -> 000000000
R =             111111111  (-1 as signed 9-bit)
```

Using the unsigned carry as the signed result bit would incorrectly encode this
case as `+255`.

### INT8 multiplication

For two's-complement operands, a partial product has a negative coefficient
when it contains exactly one of the two sign bits. There are 14 such cross
terms: `A7 AND B0..B6` and `A0..A6 AND B7`. The generator:

1. Complements those 14 partial products.
2. Adds a constant one at bit positions 8 and 15.
3. Compresses the resulting columns with the same full-adder structure used by
   UINT8 multiplication.

For a Boolean partial product `p`, the identity `-p = (1 - p) - 1` explains the
complement. Complementing all cross terms adds the weighted offset
`2^15 - 2^8`; the two correction bits add `2^15 + 2^8`. Their total is `2^16`.
The transformed unsigned accumulation is therefore:

```text
transformed_sum = signed_product + 2^16
```

The low 16 bits are exactly the signed INT8 product, and the generated trace's
extra carry is exhaustively checked against this identity. This construction is
a derivation in this package, not a claim about an unpublished PRADA signed
sequence.

## FP8 formats and numerical scope

The field encodings follow the
[OCP 8-bit Floating Point Specification, revision 1.0](https://www.opencompute.org/documents/ocp-8-bit-floating-point-specification-ofp8-revision-1-0-2023-06-20-pdf):

| Format | Encoding | Bias | Minimum normal | Maximum normal | Special values |
|---|---|---:|---:|---:|---|
| E5M2 | `SEEEEEMM` | 15 | `2^-14` | 57,344 | infinities and NaNs |
| E4M3 | `SEEEEMMM` | 7 | `2^-6` | 448 | finite-only; `S.1111.111` is NaN |

The generators reproduce or adapt PRADA's bounded-alignment and truncating
arithmetic, not a complete OFP8 arithmetic unit:

- ADD aligns only as far as the stored fraction width: two positions for E5M2
  and three for E4M3. Smaller operands are discarded outside that window. The
  aligned signed significands are added and normalized without rounding.
- MUL multiplies the implicit-one significands, normalizes the product, adjusts
  the exponent, and truncates discarded fraction bits.
- ADD validation compares normal inputs whose output is normal or exact
  cancellation. Its row manifest includes a widened signed exponent diagnostic
  because an exported byte is only a candidate outside that domain.
- MUL validation compares normal inputs whose exact product remains between the
  format's minimum and maximum normal magnitudes.
- Subnormal arithmetic, complete infinity/NaN propagation, and every
  overflow/underflow policy are outside the contract.

Optional comparison with NumPy and `ml_dtypes.float8_e5m2` or
`ml_dtypes.float8_e4m3fn` is diagnostic only. Differences are expected because
these traces truncate and do not implement RNE.

## Generate and validate traces

Run the module from the Ramulator2 repository root:

```bash
python3 -m tools.pud_operation_generator
```

Generate selected profiles or choose another output directory:

```bash
python3 -m tools.pud_operation_generator \
  --only uint8-add int8-mul fp8-e4m3-add fp8-e4m3-mul \
  --out build/pud-operation-generator

python3 -m tools.pud_operation_generator --out build/pud-traces
```

### Opt-in physical lowering

Physical lowering has two opt-in layout paths. With `--physical-layout`, the
tool requires an explicit JSON layout for every selected profile and treats
the designated input, constant, and output rows as fixed caller constraints.
For example, `uint8-add-layout.json` can contain:

```json
{
  "uint8-add": {
    "local_row_count": 1024,
    "inputs": {
      "A0": 0, "A1": 1, "A2": 2, "A3": 3,
      "A4": 4, "A5": 5, "A6": 6, "A7": 7,
      "B0": 8, "B1": 9, "B2": 10, "B3": 11,
      "B4": 12, "B5": 13, "B6": 14, "B7": 15
    },
    "constants": {"CONST_ZERO": 16},
    "outputs": {
      "R0": 17, "R1": 18, "R2": 19, "R3": 20, "R4": 21,
      "R5": 22, "R6": 23, "R7": 24, "R8": 25
    }
  }
}
```

Run lowering and exhaustive symbolic/physical validation with:

```bash
python3 -m tools.pud_operation_generator \
  --only uint8-add \
  --physical-layout uint8-add-layout.json \
  --out build/pud-operation-generator
```

This additionally emits `<profile>.physical.json`. Its primitive operands are
integer local-row IDs, while provenance retains the symbolic names, original
indices, and stages. These IDs are local to a caller-selected execution
context. They are not complete canonical Ramulator addresses or request
fragments; a later resolver-aware adapter must combine them with the selected
Bank, subarray, and explicit `MatRange`.

Alternatively, generate deterministic default designations and lower with:

```bash
python3 -m tools.pud_operation_generator \
  --only uint8-add \
  --use-default-physical-layout \
  --out build/pud-operation-generator
```

For each profile, `--use-default-physical-layout` assigns inputs in existing
input order, then declared constants, then outputs in output order, using
consecutive local rows beginning at zero. It assigns no work rows; the existing
`lower_to_physical()` allocator still chooses all temporary rows. Its default
capacity of 1,024 local rows is the current DDR4/MIMDRAM model default, not a
universal DRAM property.

The generated `default-physical-layout.json` uses exactly the same reusable
per-profile `local_row_count`, `inputs`, `constants`, and `outputs` structure
shown above. Passing that file later through `--physical-layout` reproduces the
same fixed designations. Physical artifacts and validation results identify
the layout provenance as `default_generated` or `caller_provided`.

For an editable round trip, first run the default command above, edit only the
designated rows or capacity in its JSON, then reuse it directly:

```bash
python3 -m tools.pud_operation_generator \
  --only uint8-add \
  --physical-layout build/pud-operation-generator/default-physical-layout.json \
  --out build/pud-operation-generator-edited
```

A caller-provided JSON is the actual operation-level local physical-row
placement. The generated layout is only a built-in default placement for easy
validation and use. Both become the same `PhysicalRowLayout` and feed the same
`lower_to_physical()` implementation. Bank, subarray, and `MatRange` selection
remain outside this package, and local row IDs are not complete DRAM addresses.
A future GEMV layout planner may construct the same `PhysicalRowLayout` after
choosing its Bank, subarray, `MatRange`, and operand/result placement; that
planner is not implemented here.

If both physical-layout options are supplied,
`--use-default-physical-layout` takes precedence and `--physical-layout` is
ignored, including its file contents. Without either option, generation
remains symbolic-only.

The default output directory is `build/pud-operation-generator/`, following
the repository convention for untracked generated artifacts.

Every selected profile is checked over all 65,536 input pairs. A successful run
reports `reference/replay PASS`.

Each profile produces:

- `<profile>.primitives.txt`: ordered symbolic primitive trace
- `<profile>.rows.json`: input, constant, output, work-row, and cost metadata
- `<profile>.requests.inc`: symbolic C++ request fragment
- `validation.json`: reference and serialized-trace replay results

With either physical-layout option, each profile also gets
`<profile>.physical.json`, and its validation record gains a separately named
`physical_lowering` result.

FP8 ADD also produces `<profile>-domain-counts.csv`.

Rows in `.requests.inc` are symbolic. An integrating simulator or runtime must
map them to legal physical rows or operands. The primitive order must be
preserved because the trace models destructive row semantics.

## Python API

Copy this directory to another repository root and import it directly:

```python
from pud_operation_generator import (
    build_uint8_add,
    build_uint8_mul,
    build_int8_add,
    build_int8_mul,
    build_e5m2_add,
    build_e5m2_mul,
    build_e4m3_add,
    build_e4m3_mul,
)

program = build_e4m3_mul()
print(len(program.trace))
print(program.inputs)
print(program.outputs["R"])
```

The physical API accepts the same builder or a separately analyzed normalized
program:

```python
from pud_operation_generator import (
    PhysicalRowLayout,
    analyze_physical_lowering,
    execute_physical,
    extract_physical_results,
    lower_to_physical,
    make_default_physical_layout,
)

normalized = analyze_physical_lowering(program)
constant_base = len(program.inputs)
output_base = constant_base + len(program.constants)
layout = PhysicalRowLayout(
    local_row_count=1024,
    inputs={name: row for row, name in enumerate(program.inputs)},
    constants={
        name: constant_base + index
        for index, name in enumerate(program.constants)
    },
    outputs={
        name: output_base + bit
        for bit, name in enumerate(program.outputs["R"])
    },
)
lowered = lower_to_physical(normalized, layout)

# Or use consecutive model-default designations; work rows remain unassigned
# until lower_to_physical() runs.
default_layout = make_default_physical_layout(program)
default_lowered = lower_to_physical(program, default_layout)
```

`execute_physical(lowered, initial_physical_rows, lanes)` accepts and returns
integer-keyed local-row storage. Use
`extract_physical_results(lowered, final_physical_rows)` to read outputs from
their designated result rows.

The included interpreter can execute a generated trace for selected lanes:

```python
from pud_operation_generator import build_int8_add
from pud_operation_generator.core import execute, pack, signed_value, unpack

program = build_int8_add()
a = [-128, -7, 127]
b = [-1, 13, 127]
lanes = len(a)

initial = dict(zip(
    program.inputs,
    pack([value & 0xFF for value in a], 8)
    + pack([value & 0xFF for value in b], 8),
))
initial.update({
    row: (1 << lanes) - 1 if value else 0
    for row, value in program.constants.items()
})

rows = execute(program.trace, initial, lanes)
raw = unpack([rows[row] for row in program.outputs["R"]], lanes)
result = [signed_value(value, 9) for value in raw]
print(result)  # [-129, 6, 254]
```

## Optional library comparison

```bash
python3 -m pip install -r tools/pud_operation_generator/requirements-check.txt
python3 -m tools.pud_operation_generator --library-check
```

## Tests

From the Ramulator2 repository root:

```bash
python3 -m unittest discover -s tools/pud_operation_generator/tests -v
```

Or, from inside `tools/pud_operation_generator/`:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover the eight-profile public surface, primitive counts, selected
UINT8 and INT8 values, exhaustive reference validation, serialized replay, and
execution after copying the directory into an isolated temporary repository.

## Primitive semantics

- `RowCopy(src, dst, ...)` preserves the source and copies it to each destination.
- `NOT_COPY(src, dst, ...)` leaves the source and destinations with the inverted value.
- `NOT(row)` inverts a row in place.
- `TRA(a, b, c)` writes the majority of the previous values to all three rows.
- `5RA(a, b, c, d, e)` writes the majority of the previous values to all five rows.

Do not reorder requests or merge distinct symbolic rows without revalidating the
destructive dataflow.
