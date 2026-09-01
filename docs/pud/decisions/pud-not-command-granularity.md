Status: Accepted

Question

What is the minimum simulator command abstraction for the internal phases of
the PuD NOT operation `N`?

Decision

Represent `N` as one explicit lower-level DRAM command.

Keep the internal circuit phases described by the reference, including
separate BL/BL-bar precharge, BL-BL-bar charge sharing, and sensing, internal
to `N`. Do not expose them as independently schedulable Ramulator2 commands.

This decision defines only the command granularity of `N`. It does not define
its detailed state transition, numeric timing or resource occupancy, or
whether the surrounding NOT sequence can be interleaved or interrupted.

Rationale

The in-scope simulator model does not require the internal circuit phases to
be independently scheduled. A single explicit command provides the required
lower-level command identity without introducing unsupported phase-level
commands.

This is a simulator abstraction, not a claim that `N` is physically a single
indivisible circuit operation.

Evidence

The project reference describes the internal phases of `N`, while the current
scope requires a modeled NOT sequence and does not require those phases to be
independently schedulable Ramulator2 commands.

Open issues

The detailed state transition, numeric timing, resource occupancy, and
interleaving or interruptibility of the surrounding NOT sequence remain
unresolved for later decision gates.
