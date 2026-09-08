# PuD Primitives

## Source

This document summarizes the PuD primitive behavior described in
`PuD primitives.pdf`.

The document is a project reference, not a record of simulator
design decisions.

## Activation Commands

- `A_S`: ACT with WL activation and BL sensing.
- `A`: ACT with WL activation only.
- `A_S*`: `A_S` with offset cancellation.
- `A*`: `A` with offset cancellation.

Sequential row activation (SRA) performs charge sharing across
multiple rows using consecutive `A` commands and performs sensing
with the final `A_S`.

Offset cancellation is applied only to the first activation in an
SRA sequence.

## MAJ3 / TRA

Operands:
- X
- Y
- Z

Command sequence:

    A*(X) -> A(Y) -> A_S(Z) -> P

The three activated rows participate in charge sharing, and the
final sensing operation produces the majority result.

## MAJ5 / 5RA

Operands:
- V
- W
- X
- Y
- Z

Command sequence:

    A*(V) -> A(W) -> A(X) -> A(Y) -> A_S(Z) -> P

The five activated rows participate in charge sharing, and the
final sensing operation produces the majority result.

## Row Copy

Single destination:

    A_S*(X) -> A(Y) -> P

where X is the source row and Y is the destination row.

Multiple destinations:

    A_S*(X) -> A(Y) -> A(Z) -> P

## NOT

For a temporal value that is already available in the source row, PRADA
performs NOT as:

    A_S*(X) -> N -> P

`N` operates after the sensed activation. During the NOT operation, the
source WL remains enabled, and the inverted value is sensed and restored
through the source row before the final precharge.

### NOT and Copy

PRADA's 2-bit ADD example also uses a combined NOT-and-copy sequence:

    A_S*(X) -> N -> A(Y) -> P

where X is the source row and Y is the copy destination.

The `N` step first produces the inverted value while the source activation
remains open. The following `A(Y)` copies that inverted value to Y before the
final precharge. Thus, the sequence avoids closing the bank and reactivating
the inverted source solely to copy it.

PRADA labels this step "NOT and Copy" in the 2-bit ADD command sequence. It
does not introduce a separate DRAM command for the combination: the sequence
uses the existing activation commands, `N`, and final `P`.

**Source:** Shin et al., ICCAD 2024, §4.1 and Table 2.

## Information Not Defined Here

This reference does not define:

- Ramulator2 request types for these primitives,
- how multiple row operands are represented in a request,
- how requests are translated into the command sequences above,
- Ramulator2 state representation,
- numeric timing parameters,
- timing constraints between the new commands,
- scheduler behavior,
- energy values,
- whether the source-described `NOT and Copy` sequence is exposed as a
  separate simulator request or represented in another way.

These are separate simulator modeling decisions or require
additional references.