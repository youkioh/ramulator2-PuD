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

...

## Information Not Defined Here

This reference does not define:

- Ramulator2 request types for these primitives,
- how multiple row operands are represented in a request,
- how requests are translated into the command sequences above,
- Ramulator2 state representation,
- numeric timing parameters,
- timing constraints between the new commands,
- scheduler behavior,
- energy values.

These are separate simulator modeling decisions or require
additional references.