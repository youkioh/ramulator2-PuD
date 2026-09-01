Status: Accepted

Question

How are PuD operands routed and validated for legal placement?

Decision

All operands must belong to the same logical DRAM subarray and therefore share
channel, rank, bank group, and bank. Route using operand 0's channel; do not
orchestrate across controllers. The memory system validates primitive operand
counts, channel coordinates, and same-channel routing. The controller validates
operand address-vector shape and hierarchy bounds, shared rank/bank-group/bank,
and shared derived subarray identity.

For DDR4_PuD, derive placement from the final device-visible row using
`subarray_id = row / 1024` and `local_row = row % 1024`. Contiguous groups of
1024 rows form one logical subarray. This is a simulator modeling assumption,
not a verified physical DDR4 address mapping. Individual chips are not an
independently addressable placement level.

Preserve each operand's column coordinate without assigning it operation
semantics. Do not assign new PuD semantics to `size_bytes`.

Rationale

The memory system owns controller selection, while the controller owns the
device hierarchy and DDR4_PuD geometry needed for placement-legality checks.
Derived geometry keeps the external DDR4 address hierarchy unchanged and can
be extended with internal mat identity later.

Evidence

The project MIMDRAM geometry reference records 1K rows per mat and the accepted
contiguous-row modeling assumption. Ramulator2 routes one request to one
controller by channel, while each controller owns its DRAM specification and
address mapping.

Open issues

Mat-level identity and interleaving are not defined.
