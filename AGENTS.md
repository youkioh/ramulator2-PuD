## Project

This repository extends Ramulator2 for research on
Processing-using-DRAM (PuD).

The project develops and evaluates simulator support for PuD,
including DRAM-level operations and the system mechanisms required
to execute them.

The exact PuD command structure, state representation, timing model,
request interface, data placement policy, energy model, and other
modeling choices are research decisions.

Do not assume unresolved research or modeling decisions unless they
have been explicitly decided.

## Working Rules

- Understand the existing Ramulator2 implementation before modifying it.
- Preserve existing behavior unless a PuD feature explicitly requires a change.
- Prefer minimal changes over unrelated refactoring.
- Do not guess undocumented Ramulator2 behavior.
- Do not silently resolve an open research or modeling question.
- Clearly distinguish verified facts, assumptions, and project decisions.
- If required information is missing, ask the user rather than inventing it.
- Implement only the agreed scope.
- After a code change, run the smallest relevant build or test available.
- Compilation alone does not establish that the modeled DRAM behavior is correct.

Before making a non-trivial design choice:
1. identify the question,
2. inspect the relevant code and available references,
3. explain the alternatives and trade-offs,
4. ask the user before committing to one.

## Communication

- Keep responses concise and focused on the current decision or task.
- Do not repeat information already available in project documents or prior responses unless needed for context.
- When asking for user approval, present only the decision to make, the relevant alternatives, and their key trade-offs.
- Summarize completed work briefly and state the next action.
- Provide detailed explanations only when the user asks for them or when they are necessary to avoid an incorrect decision.
- Prefer referencing an existing plan or decision document over reproducing its contents in the response.

## Evidence and Project Decisions

Use the current Ramulator2 source code as the basis for claims about
how Ramulator2 works.

For design decisions that depend on external DRAM or PuD knowledge,
use reference material provided in this repository.

If the required information is not available, tell the user exactly
what information or source is needed rather than making an assumption.

A project modeling choice is not a fact about Ramulator2 or DRAM.
Treat it as a project decision.

## Project Documents

Persistent project documents belong under `docs/pud/`.

```text
docs/pud/
├── references/
├── decisions/
└── plans/
```
### docs/pud/references/

Contains technical material provided for this research, such as
summaries or excerpts from papers, specifications, and prior study.

Reference material may contain incomplete or uncertain information.
Do not silently promote it to a project decision.

### docs/pud/decisions/

Contains modeling or design decisions explicitly accepted by the user.

Prefer a small set of canonical Accepted decision documents organized around
stable, coherent modeling boundaries. Keep meaningful architectural
boundaries separate; this does not require one giant decision document.

Do not create a new decision file for every investigation, Decision Gate,
implementation-plan gate, or small refinement. When a newly accepted choice
naturally belongs to an existing canonical decision, update that document and
preserve its relevant rationale, evidence boundary, assumptions, fidelity
limitations, and genuinely live open issues. Create a new decision document
only when the choice is genuinely independent and does not fit cleanly in an
existing canonical authority.

Each decision should contain only:

Status: Proposed | Accepted | Superseded
Question
Decision
Rationale
Evidence
Open issues

Do not record an unresolved question as an accepted decision.

Decisions with `Status: Accepted` are current project authority. Prefer that
actively evolving authority to use the canonical organization above.
Decisions with `Status: Superseded` are historical provenance, not current
authority. The `docs/pud/decisions/` directory may contain both.

If an Accepted decision changes or is consolidated into another canonical
decision, preserve the old file, mark it Superseded, add a clear successor
pointer, and retain its historical rationale. A separate `superseded/` or
`archive/` subdirectory is not required; do not move Superseded files merely
to make the directory visually cleaner.
Prefer stable paths and successor links unless there is a concrete
maintenance reason to reorganize files.

External and source facts remain primarily in `docs/pud/references/`.
Canonical decisions should contain enough local context to understand the
project choice, but should reference the technical source instead of
duplicating long physical explanations.

### docs/pud/plans/

Contains implementation plans only when a task is large enough that
the plan must persist across sessions.

Small plans should remain in the current conversation.

Completed implementation plans may remain as historical phase and
implementation artifacts. Do not retroactively consolidate completed plans
solely to match the canonical-decision organization.

A Decision Gate encountered while executing a plan does not automatically
require a new decision file. Update an existing canonical decision when the
choice refines that authority; create a new decision file only for a
genuinely independent modeling boundary.

### Normal context recovery

For a normal planning or implementation task, recover current project state
in this order:

1. relevant technical references;
2. current Accepted canonical decisions;
3. the implementation plan, if one exists for the task;
4. Superseded decisions only when historical rationale or provenance is
   needed.

A fresh task should not need to follow a long chain of Superseded decisions
to reconstruct current architecture. If current semantics cannot be recovered
from the canonical documents, clarify or consolidate the canonical
documentation before proceeding.

## Planning

Use an expand-then-consolidate workflow for uncertain research and modeling
work: decompose unresolved questions into focused investigations, validate
their results independently, and consolidate stable accepted results into
canonical decisions before implementation planning. Do not make
implementation reconstruct current authority from a chronological chain of
exploratory or Superseded decisions when it can be expressed canonically.

Define an implementation Phase by a meaningful, testable architectural or
integration invariant—not merely by files, subsystems, or separately listed
implementation concerns. Merge adjacent work when separation provides no
concrete dependency, debugging, rollback, risk-isolation, or regression
benefit. Do not leave a Phase boundary with knowingly provisional or unsafe
executable semantics when already-accepted work completes the invariant.

Keep these planning boundaries distinct:

- research or Decision investigation;
- Codex work unit or chat;
- implementation Phase;
- Decision Gate;
- independent audit;
- commit boundary.

They do not need to coincide. A cohesive Phase may span multiple focused work
units or fresh chats, and a small work unit does not automatically warrant its
own Phase or commit.

Do not minimize Phase count mechanically. Keep each Codex work unit narrow
enough for careful inspection, implementation, testing, and self-review. If a
cohesive Phase is too large for one context, split it into work units or fresh
chats rather than automatically splitting the Phase. Start a fresh context
when accumulated investigation or debugging would reduce reasoning or review
quality.

For every unresolved modeling choice, identify the first code consumer and
resolve its Decision Gate before that code is written. Resolve tightly coupled
Gates together when they share a first consumer. Recheck whether a Gate still
exists when reached; do not preserve an obsolete Gate only because it appeared
in an earlier plan. A Gate does not automatically require a new decision file;
follow the canonical-decision policy above, including user approval for
modeling choices.

Use risk-tiered verification:

- work-unit checks use focused new tests, directly affected regressions, and
  local diff review;
- Phase-exit checks use a complete Phase diff review, Phase-level regressions,
  and `git diff --check`;
- genuinely shared or cross-cutting changes require broader relevant suites;
- when warranted, final integration closure performs broad end-to-end and
  regression validation.

Do not repeatedly run the broadest suites after every small work unit without
a risk-based reason. Normal implementation includes full diff self-review and
appropriate tests. Use a separate fresh-context audit only when cross-cutting
risk gives it clear additional value, such as shared scheduler/controller
semantics, subtle completion or reentrancy behavior, or broad cross-standard
changes; do not require one after every Phase.

Keep implementation plans concise handoff documents, not duplicate
architecture references. Reference canonical decisions and technical sources,
repeat only exact contracts needed for implementation and testing, and avoid
duplicated Phase-exit boilerplate, Non-goals, and test matrices. A fresh
implementation chat should recover current work from `AGENTS.md`, canonical
authority, the plan, and current source/tests without requiring old plans,
Superseded decisions, or previous chat transcripts.

## Document Management

Do not create a new persistent document, directory, or documentation
category without asking the user first.

Before proposing a new document, check whether the information belongs
in an existing document.

Before creating a new decision file, first determine whether the accepted
choice belongs in an existing canonical decision.

Do not use documentation as a dump of conversation history.

Do not duplicate the same information across documents.

Documentation cleanup is not an independent goal. Do not broaden active
research, planning, or implementation work into retrospective cleanup of
stable project history. Consolidate documentation when fragmentation
materially harms recovery of current authority, planning or implementation
context, source-of-truth clarity, or maintenance of an actively evolving
design—not merely because a directory contains many files.

Canonical-document guidance is prospective and need-based. Do not
retroactively consolidate, rename, move, or rewrite existing decision sets
solely to make older documentation conform to the current organization
policy. Existing Accepted decisions remain valid according to their recorded
status and successor relationships. Completed or stable historical work may
retain its existing decision and plan structure unless a concrete task
requires normalization.

Do not modify AGENTS.md without explicit user approval.

## PuD Modeling

When modeling a PuD operation, do not assume that its physical DRAM
behavior maps directly to existing Ramulator2 commands or states.

Before implementation, determine what Ramulator2 should represent and
identify any limitations of the existing model.

If this requires a new modeling decision, discuss it with the user first.

## File Editing Constraints (for codex)

- If `apply_patch` fails because of a sandbox or tool-infrastructure error,
  retry it at most once with repository-relative paths. If the same error
  recurs, run `apply_patch` through an escalated command and provide the patch
  through standard input; do not use shell heredocs or another file-writing
  mechanism.
- For documentation-only tasks, collect all required edits before patching,
  apply them in one patch when practical, and validate with `git diff --check`.
  Do not broaden the edit into unrelated documentation cleanup.
