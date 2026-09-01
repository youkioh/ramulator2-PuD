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

Use one file for one independent decision.

Each decision should contain only:

Status: Proposed | Accepted | Superseded
Question
Decision
Rationale
Evidence
Open issues

Do not record an unresolved question as an accepted decision.

If an accepted decision changes, preserve the previous decision and
mark it as superseded.

### docs/pud/plans/

Contains implementation plans only when a task is large enough that
the plan must persist across sessions.

Small plans should remain in the current conversation.

## Document Management

Do not create a new persistent document, directory, or documentation
category without asking the user first.

Before proposing a new document, check whether the information belongs
in an existing document.

Do not use documentation as a dump of conversation history.

Do not duplicate the same information across documents.

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