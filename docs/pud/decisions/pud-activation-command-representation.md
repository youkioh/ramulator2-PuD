Status: Accepted

Question

How should the PuD activation variants be represented, and at which level
should the in-scope PuD operations exist?

Decision

Represent `A`, `A*`, `A_S`, and `A_S*` as four explicit lower-level DRAM
commands using the identifiers `ACT_PUD`, `ACT_PUD_OC`, `ACT_PUD_S`, and
`ACT_PUD_S_OC`, respectively.

Keep RowCopy, MAJ3, MAJ5, and NOT as request-level operations only. Do not
introduce device-level primitive commands for them.

This decision establishes command identity only.

Rationale

Distinct command identifiers fit Ramulator2's command-indexed representation
without adding variant metadata to generic command interfaces. Keeping the
primitives at request level matches their accepted controller-sequenced request
mapping and avoids multi-address or variable-length device commands.

Evidence

Ramulator2 represents lower-level DRAM operations with explicit command
identifiers and maps DDR4_PuD primitive requests to controller-sequenced
operations.

Open issues

State transitions, prerequisites, legality, and timing remain unresolved.
