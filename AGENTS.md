# AGENTS.md

## Mission

Build and maintain the small personal page watcher defined in `SPEC.md`.

Read `SPEC.md` before making implementation decisions.

`SPEC.md` defines what the product must do. This file defines how to work on it.

---

## Source of truth

Priority order:

1. `SPEC.md`
2. this file
3. existing implementation
4. implementation convenience

Existing code is not automatically correct because it already exists.

Previous effort is not a reason to preserve unnecessary structure.

If implementation and `SPEC.md` disagree, follow the specification unless the task explicitly changes it.

---

## Primary engineering rule: Just Enough

Use the reasoning principles from `janmrow/just-enough`.

Complexity must earn its place.

Before adding a non-trivial abstraction, dependency, component, or mechanism, ask:

1. What concrete problem does this solve now?
2. What materially breaks without it?
3. Does it improve correctness, reliability, security, clarity, or usefulness?
4. Is there a simpler solution with similar value?
5. If starting from zero today, would we still add it?

Prefer the simpler option when additional complexity provides little additional value.

Do not simplify away correctness, security, reliability, validation, meaningful error handling, or useful tests.

The goal is proportional complexity, not minimum code.

---

## Work one step at a time

Follow the implementation steps in `SPEC.md`.

For the current step:

- implement what is required,
- verify it,
- stop.

Do not pre-build future requirements or infrastructure for hypothetical needs.

---

## Keep the implementation obvious

Prefer direct functions, explicit data flow, and standard Python constructs.

Introduce abstractions only when the current code demonstrates a real need for them.

In particular, do not introduce classes, provider layers, repositories, factories, dependency injection, or plugin systems merely because they could make the design more extensible.

A small amount of obvious duplication can be cheaper than a premature abstraction.

Prefer:

1. the Python standard library,
2. a small established dependency when it materially simplifies the solution,
3. custom machinery only when necessary.

Every runtime dependency should solve a concrete current problem.

---

## Preserve product invariants

The reliability and security rules in `SPEC.md` are requirements, not optional polish.

When changing the implementation, make sure that:

- failures cannot corrupt known-good state,
- targets remain independent,
- external input remains untrusted,
- secrets remain outside the repository,
- model output is validated before use,
- deterministic work stays in ordinary code when practical.

Do not weaken these properties merely to reduce line count.

---

## Scope and refactoring

Preserve working structure by default.

Change only what the current requirement or a demonstrated problem makes necessary.

Before adding something outside the current requirement, ask:

> Is this necessary for the watcher to be correct, secure, reliable, or clearly understandable now?

If not, leave it out.

Refactor when there is a demonstrated problem with:

- readability,
- correctness,
- testability,
- or maintenance.

Do not refactor merely because a more abstract design is possible.

When a real requirement makes the simple solution inadequate, solve that concrete problem with the smallest mechanism that handles it well.

Do not generalize one local problem into a framework without evidence that the generalization is needed.

---

## Testing

Follow the test scope defined in `SPEC.md`.

Prefer a small number of behavior-level tests that protect critical flows and invariants.

Add narrower unit tests when a pure function has a meaningful failure mode.

Do not optimize for coverage percentage or test incidental implementation details.

---

## Change discipline

Keep changes:

- small,
- local,
- understandable,
- reversible.

Avoid unrelated cleanup during feature work.

Do not reorganize, rename, or generalize code without a concrete benefit to the current task.

Work with the repository's existing workflow.

Do not introduce branching, release, or process conventions unless explicitly requested.

---

## Before finishing a task

Check:

```text
Does this satisfy the current step in SPEC.md?
Did this add complexity?
If so, what concrete value does it buy?
Did I accidentally implement a future requirement?
Could a simpler version provide similar value?
Are the product invariants still preserved?
Do the relevant tests pass?
```

If the current requirement is satisfied, stop.

Do not continue improving the project merely because further improvement is possible.
