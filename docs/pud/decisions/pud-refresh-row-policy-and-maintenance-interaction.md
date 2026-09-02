Status: Accepted

Question

How do refresh, row policy, priority maintenance, and controller plugins
interact with an active PuD request?

Decision

Use the accepted Gate 9 eligibility rule as the sole mechanism for protecting
an active PuD sequence from conflicting maintenance and controller-generated
work. Before prerequisite resolution, a request or command is ineligible when
its scope intersects a bank containing an active PuD request unless it is the
continuation of that retained active PuD request.

Conflicting `PREpb`, `PREab`, `REFab`, row-policy work, and plugin-generated
maintenance remain queued until the active PuD request issues its final
`PREpb`. Do not preempt, abort, or resume a PuD sequence. Do not add
refresh-aware PuD admission or scope-aware bypass of a blocked priority-buffer
head.

Preserve the existing controller ordering: active-buffer candidates precede
the FIFO priority-buffer head, and a nonempty priority buffer prevents new
read/write scheduling. Already-active requests whose scopes do not intersect
the PuD-owned bank continue to use existing scheduling behavior. Preserve the
existing row-policy and plugin hook ordering.

`Open` requires no special handling. `ClosedCAP` may retain its existing hooks
and queued-work behavior, but no precharge that it generates may interrupt an
active PuD request. Observational plugin hooks may remain unchanged and see
issued PuD commands. Do not claim validated behavior for plugins whose
semantics depend on conventional activation or maintenance behavior; any
plugin-generated command remains subject to the same pre-prerequisite
eligibility rule.

Recognizing the `DDR4_PuD` standard name at rank scope in `AllBankRefresh` is a
Phase 6 implementation detail, not a separate modeling decision.

Rationale

The retained active PuD request already supplies continuation identity and
bank-scoped ownership under Gate 9. Applying one eligibility rule to every
candidate source prevents premature precharge, refresh, and plugin maintenance
without adding another ownership or interruption mechanism.

Leaving conflicting work queued and retaining FIFO-head blocking preserves the
existing Ramulator2 priority policy. Bypassing blocked priority work would add
a new scheduling policy, while refresh-aware admission or preemption would
require unsupported deadline, abort, and restoration semantics.

Evidence

The GenericDDR controller selects active-buffer work before the FIFO priority
head and only considers new read/write work when the priority buffer is empty.
Refresh managers and `ClosedCAP` enqueue maintenance through the priority
buffer. DDR4 `REFab` requests a rank-wide `PREab` prerequisite when a targeted
bank is not closed. Controller plugins run around scheduling and may enqueue
priority work. Gate 9 retains the PuD request in the active buffer through its
final `PREpb` and requires intersecting non-owner candidates to be rejected
before prerequisite resolution.

Open issues

- An arbitrarily long RowCopy may postpone refresh beyond normal refresh
  expectations.
- No refresh postponement limit, credit model, retention guarantee, or
  queue-overflow policy is modeled.
- This is a simulator policy, not a claim that physical DDR4 permits unbounded
  refresh postponement.
- The interaction between PuD activations and RowHammer-sensitive or other
  behavior-changing plugins is not physically validated.
