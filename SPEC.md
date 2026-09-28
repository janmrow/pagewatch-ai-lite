# PageWatch AI Lite — v0.1

## Goal

Build a small, reliable personal page watcher that runs on a VPS and answers one question:

> Did a configured page change in a way that matters to the user's intent?

The initial use case is monitoring a few postgraduate-study pages for changes such as new recruitment, additional groups, available places, or reopened registration.

This is a personal automation, not a monitoring platform.

The project should remain small enough to understand end-to-end and simple enough to build and deploy in one evening.

---

## Principle

Use **Just Enough** complexity.

Add complexity only when it materially improves:

- correctness,
- reliability,
- security,
- clarity,
- or usefulness.

Prefer the simpler solution when both approaches provide similar value.

Canonical reference: `janmrow/just-enough`.

---

## Flow

```text
cron
  ↓
load targets
  ↓
fetch page
  ↓
extract and normalize text
  ↓
compare with previous state
  ↓

first run
  → save baseline

no change
  → stop

change
  → create diff
  → send diff + intent to LLM
  ↓

IGNORE
  → save new state

NOTIFY
  → send email
  → save new state

REVIEW
  → send email
  → save new state

failure
  → log error
  → keep previous state
```

Each target is processed independently.

The watcher runs from cron at:

```text
09:00
11:00
13:00
15:00
```

Timezone:

```text
Europe/Warsaw
```

The process starts, checks all targets, and exits.

---

## Configuration

Targets live in `config.toml`.

Conceptually:

```toml
[[targets]]
id = "example-course"
url = "https://example.com/course"
intent = """
Notify me about meaningful changes related to recruitment,
new groups, available places, or registration.
"""
```

Add target-specific configuration only when a real page requires it.

Secrets live outside Git in environment variables or a local `.env`.

---

## State

Previous normalized page content is stored locally:

```text
.state/
  <target-id>.txt
```

The first successful run establishes the baseline and sends no notification.

State updates must be atomic.

Never replace known-good state after incomplete processing.

---

## LLM

The LLM is only a classifier.

It receives:

- user intent,
- target context,
- detected change.

Allowed decisions:

```text
NOTIFY
IGNORE
REVIEW
```

Model output must be validated before use.

Remote page content is untrusted data, not instructions.

The LLM receives no credentials and has no tools or direct side effects.

OpenCode Console is called directly over HTTP.

---

## Notifications

Email is the only notification channel in v0.1.

Use ordinary SMTP.

A notification should contain:

- target,
- URL,
- decision,
- short reason,
- relevant change.

---

## Invariants

1. **First run is quiet.**  
   It establishes the baseline without calling the LLM or sending a change notification.

2. **No change means no LLM.**  
   Unchanged pages cause no inference request.

3. **Failures do not advance state.**  
   Fetch, LLM, validation, or notification failures preserve the last known-good state.

4. **Targets fail independently.**  
   One broken target cannot prevent others from running.

5. **External input is untrusted.**  
   Validate model output and never execute instructions from monitored pages.

6. **Secrets stay outside Git.**

7. **Reliability is not optional simplification.**  
   Timeouts, validation, useful error handling, and atomic state writes stay.

---

## Out of scope

v0.1 does not need:

- a web application or API,
- a database,
- Docker,
- browser automation,
- background workers or queues,
- an agent runtime,
- generic plugin/provider architectures,
- dashboards or observability infrastructure.

If a real requirement later proves one of these necessary, reassess it then.

---

# Implementation steps

## Core watcher

Implement:

- configuration loading,
- HTTP fetch with timeout,
- text extraction and normalization,
- local baseline state,
- deterministic change detection,
- textual diff.

Expected behavior:

```text
first run → baseline
same content → nothing
changed content → diff
```

---

## LLM classification

Send the detected change and user intent directly to OpenCode Console.

Expected result:

```text
NOTIFY | IGNORE | REVIEW
```

Keep the contract small and strictly validated.

Do not introduce a multi-provider abstraction.

---

## Email notification

Send email for:

```text
NOTIFY
REVIEW
```

Keep notification content small and useful.

Do not build a generic notification subsystem.

---

## Failure safety

Add only the resilience required for reliable operation:

- network timeouts,
- invalid LLM response handling,
- SMTP failure handling,
- independent target failures,
- atomic state writes,
- useful logging.

Cron provides the next retry opportunity.

---

## Real configuration

Configure the initial real pages and intents.

Run the watcher manually against them and verify that normalization and diffs are useful.

Add a simple selector or other extraction rule only if a real page demonstrates the need.

Do not generalize a site-specific problem before it exists.

---

## Just Enough tests

Add a small pytest suite around critical behavior.

Prefer behavior-level tests with HTTP, LLM, and SMTP mocked at their boundaries.

Cover:

- first run creates baseline without notification,
- unchanged content does not call the LLM,
- `IGNORE` updates state without email,
- `NOTIFY` sends email and updates state,
- `REVIEW` sends email and updates state,
- fetch failure preserves previous state,
- LLM failure preserves previous state,
- notification failure preserves previous state,
- one target failure does not stop another.

Add small unit tests only where a pure function has meaningful failure modes, such as normalization.

Do not optimize for coverage percentage.

---

## Mikrus deployment

Deploy the finished watcher:

- clone repository,
- create virtual environment,
- install dependencies,
- configure secrets,
- verify `Europe/Warsaw`,
- perform a manual run,
- add cron entries,
- verify logs and one complete real flow.

No daemon or deployment platform is required.

---

# Definition of done

v0.1 is done when:

- configured real pages can be checked,
- first run safely creates a baseline,
- unchanged pages remain silent,
- meaningful changes can produce an email,
- ambiguous changes can be surfaced for review,
- temporary failures do not corrupt state,
- one failing target does not block others,
- secrets remain outside Git,
- automated tests protect the critical flow,
- the watcher runs unattended from cron on Mikrus.

When these conditions are satisfied, stop.

Further improvement is not part of v0.1 merely because it is possible.
