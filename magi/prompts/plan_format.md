FORMAT RULES — follow these exactly when producing a plan.

Output the plan as Japanese Markdown. Use this structure:

# Plan: <short title, max 80 chars>

## Objective
1–3 sentences. What changes and why.

## Background
- Bullet list of relevant facts: architecture, file paths, constraints.

## Tasks

Number tasks starting at 1 in execution order.
Each task block must contain ALL of the following fields:

### Task N: <imperative verb phrase>

**Scope**: 1–3 sentences. What this task does.

**Non-goals**: Bullet list of what this task does NOT do. Minimum 1 bullet.

**Files**:
- `relative/path/from/project/root` — what changes
Mark new files with `(new file)`.

**Risks**:
- Each risk paired with a mitigation. Write `None identified.` if empty.

**Done when**:
- [ ] Observable, testable criterion (include the command or assertion)
- [ ] Another criterion
Minimum 1 checkbox.

**Suggested provider**: `codex` | `claude` | `gemini` — one-line rationale.
Defaults: codex for large refactors, claude for complex logic, gemini for broad context.

**Handoff prompt**:
> Self-contained prompt for agent mode.
> Must include: file paths, constraints, acceptance criteria.
> Must NOT reference "the plan" or "see above".

## Open Questions
- Unresolved items. Each must name who can answer or what investigation is needed.
- Write `None identified.` if empty.

## Out of Scope
- What this plan does NOT cover.
- Write `None identified.` if empty.

BANNED PHRASES — do not use these anywhere in the plan:
- 適宜 / as appropriate → state the exact condition and action
- 必要に応じて / if needed → state when and what
- うまく / properly / correctly → state the measurable criterion
- 柔軟に / flexibly → state the specific options
- 場合によっては / depending on the case → state each case
- various / etc. → enumerate the items
- TBD / TBA → move to Open Questions with an owner

QUALITY CHECKS before returning:
1. Every task has all 7 fields (Scope, Non-goals, Files, Risks, Done when, Suggested provider, Handoff prompt).
2. Every Done when item starts with `- [ ]` and describes a testable outcome.
3. Every Handoff prompt is self-contained and copy-pasteable.
4. No banned phrases appear anywhere.
5. Files use relative paths from project root.
