Status: Accepted

Question

How should DDR4_PuD reuse the DDR4 baseline while keeping standard DDR4 unchanged?

Decision

Define DDR4_PuD as a separate generated DRAM standard. Reuse the DDR4 Python
definition through inheritance where appropriate, but independently copy all
mutable command, state, timing, request, and preset collections before later
DDR4_PuD extensions. Do not introduce a shared C++ or generator base.

Rationale

This creates a distinct C++ class and registration with the smallest change to
the existing generator, keeps PuD additions out of DDR4, and avoids unrelated
refactoring.

Evidence

The Python code generator emits a standalone DRAMSpec-derived C++ class and
factory registration for each registered DRAMStandard subclass.

Open issues

None for the Phase 1 substrate boundary.
