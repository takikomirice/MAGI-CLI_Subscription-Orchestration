# MAGI Plan Style Guide

This document defines the formatting rules for Japanese `plan.md` files produced by MAGI's plan mode.
The goal is **implementation precision**: every task must be concrete enough that a different developer (or a different model) can pick it up and execute without asking clarifying questions.

---

## 1. Mandatory Sections (exact order)

```
# Plan: <short title>
## Objective
## Background
## Tasks
### Task N: <title>
## Open Questions
## Out of Scope
```

Every section is required. If a section has no content, write `None identified.` — never omit the heading.

---

## 2. Section Definitions

### `# Plan: <short title>`
One-line title. Maximum 80 characters.

### `## Objective`
1–3 sentences. State **what** will change and **why**.
Do not restate the user's request verbatim — distill the intent.

### `## Background`
Bullet list of facts that a reader needs before scanning the tasks:
- Current architecture relevant to this plan
- Key file paths
- Constraints (performance budget, backwards-compat, etc.)

### `## Tasks`
Ordered list of task blocks (see Task Template below).
Tasks are numbered starting at 1 and must be in execution order.
If two tasks can run in parallel, note it explicitly: `(parallel with Task N)`.

### `## Open Questions`
Bullet list of unresolved items that block or may alter the plan.
Each item must name **who** can answer it or **what** investigation is needed.

### `## Out of Scope`
Bullet list of things this plan explicitly does **not** cover.
Prevents scope creep and sets expectations.

---

## 3. Task Template

Every task block under `## Tasks` must use this exact structure:

```markdown
### Task N: <imperative verb phrase>

**Scope**: What this task does, in 1–3 sentences.

**Non-goals**: What this task deliberately does NOT do (1–2 bullets).

**Files**:
- `path/to/file.py` — what changes
- `path/to/other.py` — what changes

**Risks**:
- <concrete risk and its mitigation>

**Done when**:
- [ ] <observable, testable acceptance criterion>
- [ ] <another criterion>

**Suggested provider**: `codex` | `claude` | `gemini` (with one-line rationale)

**Handoff prompt**:
> Quoted block containing the exact prompt to pass to the suggested provider
> in agent mode. Must be self-contained: include file paths, constraints,
> and acceptance criteria from this task.
```

### Field rules

| Field | Required | Rules |
|---|---|---|
| Scope | Yes | 1–3 sentences. No vague qualifiers. |
| Non-goals | Yes | At least 1 bullet. Write `None.` if truly empty. |
| Files | Yes | Relative paths from project root. At least 1 file. Use `(new file)` suffix for files that don't exist yet. |
| Risks | Yes | Each risk must pair with a mitigation. Write `None identified.` if truly empty. |
| Done when | Yes | Checkboxes. Each criterion must be **testable** (command to run, assertion to check, behavior to observe). Minimum 1. |
| Suggested provider | Yes | One of: `codex`, `claude`, `gemini`. Include rationale (e.g., "claude — strong at refactoring with type constraints"). |
| Handoff prompt | Yes | Markdown blockquote. Must be copy-pasteable as a standalone prompt. |

---

## 4. Acceptance Criteria Rules

Each `Done when` item must:
1. Start with a checkbox `- [ ]`
2. Describe an **observable outcome**, not a process ("tests pass" not "write tests")
3. Include the verification method when non-obvious (e.g., `python -m pytest tests/test_auth.py passes`)
4. Avoid subjective language ("works correctly", "looks good")

---

## 5. Provider Recommendation Rules

Choose the suggested provider based on task characteristics:

| Characteristic | Recommended provider |
|---|---|
| Large-scale refactoring, multi-file rename | `codex` |
| Nuanced design decisions, complex logic, type-heavy code | `claude` |
| Broad context gathering, documentation, translation | `gemini` |
| Simple mechanical changes | Any — pick the fastest available |

These are defaults. Override when you have task-specific reasons.
Always state the rationale in one line.

---

## 6. Handoff Prompt Rules

The handoff prompt must:
1. Be a self-contained instruction — do not reference "the plan" or "see above"
2. Name every file to touch with its relative path
3. State the acceptance criteria from `Done when` inline
4. Specify constraints (e.g., "do not modify the public API", "keep backwards-compat with v2")
5. Be wrapped in a Markdown blockquote (`>`)

---

## 7. Banned Phrases

The following phrases are **banned** from plan output. They introduce ambiguity and make implementation handoff unreliable.

| Banned phrase | Replace with |
|---|---|
| 適宜 (as appropriate) | State the exact condition and action |
| 必要に応じて (if needed) | State when it is needed and what to do |
| うまく (well / nicely) | State the measurable criterion |
| 柔軟に (flexibly) | State the specific options or boundaries |
| 場合によっては (depending on the case) | State each case and its handling |
| as appropriate | State the exact condition and action |
| if needed | State when it is needed and what to do |
| properly / correctly | State the specific expected behavior |
| various / etc. | Enumerate the items |
| TBD / TBA | Move to Open Questions with an owner |

---

## 8. Examples

### Good Example

```markdown
### Task 1: Add rate-limiting middleware to the /api/v2/upload endpoint

**Scope**: Add a token-bucket rate limiter that caps each authenticated user at 60 requests per minute on the upload endpoint. Unauthenticated requests are rejected before rate-limit evaluation.

**Non-goals**:
- Do not add rate limiting to any other endpoint.
- Do not implement distributed rate limiting (single-process is sufficient for now).

**Files**:
- `src/middleware/rate_limit.py` — new file, token-bucket implementation
- `src/routes/upload.py` — wire the middleware into the route
- `tests/test_rate_limit.py` — new file, unit tests

**Risks**:
- Memory growth if user-id buckets are never evicted. Mitigation: add a 10-minute TTL eviction on idle buckets.

**Done when**:
- [ ] `python -m pytest tests/test_rate_limit.py` passes
- [ ] 61st request within 60 seconds from the same user returns HTTP 429
- [ ] Unauthenticated request returns HTTP 401, not 429

**Suggested provider**: `claude` — logic-heavy middleware with edge cases around auth × rate-limit interaction.

**Handoff prompt**:
> Create `src/middleware/rate_limit.py` implementing a token-bucket rate limiter: 60 requests/minute per authenticated user. Wire it into the POST handler in `src/routes/upload.py`. Unauthenticated requests must be rejected with 401 before rate-limit evaluation. Add tests in `tests/test_rate_limit.py`. The 61st request in 60s must return 429. Evict idle buckets after 10 minutes to prevent memory growth.
```

### Bad Example

```markdown
### Task 1: Add rate limiting

**Scope**: Add rate limiting to the API as appropriate.

**Files**:
- Various files in src/

**Done when**:
- [ ] Rate limiting works correctly

**Suggested provider**: `claude`

**Handoff prompt**:
> Add rate limiting to the upload endpoint. Make sure it works properly.
```

**Why this is bad**: "as appropriate" is banned. "Various files" is vague. "works correctly" is not testable. Handoff prompt is not self-contained. Non-goals, Risks are missing.

---

## 9. Philosophy

- **Plan-first**: MAGI produces plans for humans and agents to execute. Plans are the primary artifact.
- **Multi-model comparison**: Plans may be generated by Codex, Claude, or Gemini. Strict formatting ensures all three produce comparable, mergeable output.
- **Agent-optional**: Plans must be useful even if no agent executes them. A human should be able to follow the plan with zero additional context.
- **Precision over prose**: Optimize for unambiguous implementation, not for readability as literature.
