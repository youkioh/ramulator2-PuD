Status: Accepted

Question

How should the in-scope PuD operations and their ordered row operands be
represented in a request?

Decision

Use four explicit request types: RowCopy, MAJ3, MAJ5, and NOT. Store operands
in a request-owned ordered std::vector<AddrVec_t>. For RowCopy, operand 0 is
the source and operands 1 through N are the destinations.

Rationale

Explicit request types make operation-specific validation and dispatch direct.
Owned storage remains valid as requests are copied through controller queues,
preserves operand order, and supports an unbounded nonempty RowCopy destination
list.

Evidence

Ramulator2 requests are copied into controller buffers and already use
AddrVec_t for hierarchy addresses. The PuD primitive reference defines four
distinct operations and ordered row operands.

Open issues

Column semantics and size_bytes semantics remain unresolved. Operand placement,
routing, and placement validation are governed by the accepted Decision Gate 3
decision in `pud-operand-placement-and-routing.md`.
