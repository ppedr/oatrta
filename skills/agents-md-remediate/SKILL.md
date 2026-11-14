---
name: agents-md-remediate
description: Apply an AGENTS.md audit end to end and prove the result, using three isolated subagents in sequence - a fixer applies the audit, a fresh auditor re-audits from scratch without seeing the first audit, and a comparator diffs the two audits and checks nothing was lost or changed out of scope. Use when the user asks to apply, remediate, fix or act on an AGENTS.md audit ("aplicar o audit"), to fix AGENTS.md and verify the fix, or to run an audit, fix and re-audit loop.
---

# AGENTS.md remediate

Orchestrate one remediation run: **fix → re-audit → compare**. You are the orchestrator. You do
not edit AGENTS.md yourself, you do not audit and you do not compare. Each of those is a
separate subagent with a fresh context, so no phase grades its own work.

```
audit-1.json ──▶ [fixer] ──▶ AGENTS.md edits + fix-report.md
                                   │
                    [auditor] ◀────┘   fresh context, never sees audit-1 or fix-report
                        │
                   audit-2.json
                        │
audit-1 + audit-2 ──▶ [comparator] ──▶ comparison.json + comparison.md
```

Everything oatrta writes in a repository lives under `.oatrta/<skill>/`:

- `.oatrta/audit/audit-<timestamp>/`: audit history, committed. Read from here, add to it
  with `publish`.
- `.oatrta/remediate/run-<timestamp>/`: one folder per run, git-ignored locally through
  `.git/info/exclude`:

```
baseline.json        git state and hashes before the run
before/              snapshot of every instruction file
answers.md           maintainer answers to the audit's questions
audit-1.json/.md     the audit being applied
fix-report.md        written by the fixer
audit-2.json/.md     written by the auditor
evidence/            diff.patch, scope.json, keep-check.json (comparator)
comparison.json/.md  written by the comparator
```

Bundled files (paths relative to this skill's folder, called `SKILL_DIR` below):

- `references/fixer-brief.md`, `references/auditor-brief.md`, `references/comparator-brief.md`:
  what each subagent does.
- `references/audit-procedure.md`, `references/refactor-procedure.md`: copies of the audit and
  refactor skills, used by the subagents.
- `references/guide.md`, `references/audit-schema.json`, `references/report-template.md`.
- `scripts/run_tools.py`, `scripts/scan_agents_md.py`: deterministic checks. Python 3, stdlib.

## Spawning subagents

Run the three phases strictly one after another and wait for each to finish. Use the
platform's subagent mechanism with a general-purpose agent:

- Claude Code: the Agent (Task) tool.
- GitHub Copilot CLI: the task tool (delegate to a subagent).
- VS Code Copilot: the `runSubagent` tool (it has to be enabled in the tool picker).

Prompt every subagent with **absolute paths only** and the brief to follow. Do not paste audit
content into the prompt. Never give the auditor anything from the run directory.

If the platform has no subagent mechanism, stop and tell the user: running the phases inline
would let the re-audit see the first audit and the fixer's reasoning, which defeats the check.
Offer to run `agents-md-refactor` and `agents-md-audit` as two separate sessions instead.

## Workflow

### 1. Locate and check the audit

The input is an `audit.json` written by `agents-md-audit`. Audits live in the repository history
under `.oatrta/audit/audit-<timestamp>/`. Resolve the input in this order:

1. A path from the user: an `audit.json`, or a `.oatrta/audit/audit-<timestamp>/` folder (use its
   `audit.json`).
2. Otherwise the newest entry: `python SKILL_DIR/scripts/run_tools.py latest-audit <repo>`.

A chat-only audit report cannot be consumed reliably. If there is no audit file, or the one
found fails the checks below, create a fresh one first: run
`python SKILL_DIR/scripts/run_tools.py audit-dir <repo>` and spawn the auditor subagent (step 5
prompt) with `OUT_JSON` and `OUT_MD` set to the paths it prints. That audit becomes the input
and is already part of the history.

```
python SKILL_DIR/scripts/run_tools.py validate <audit.json>
python SKILL_DIR/scripts/run_tools.py stale <audit.json> <repo>
```

- `validate` fails: the file is not usable. Re-run the audit as above.
- `stale` exits 1: AGENTS.md changed since the audit. Line references are wrong. Re-run the
  audit as above.
- No AGENTS.md at all: stop and hand over to `agents-md-create`.
- Grade A and no finding above `low`: tell the user there is nothing worth fixing and stop.

### 2. Start the run

```
python SKILL_DIR/scripts/run_tools.py init <repo>
```

It creates the run directory, snapshots every instruction file and records the git baseline.
Copy the audit to `RUN_DIR/audit-1.json` (and its `.md` next to it if there is one).

If `init` reports `uncommitted_instruction_files`, tell the user: the run can still be reverted
from the snapshot, but `git diff` will mix their edits with the fixer's. Proceed unless they
object. Without git, the scope check is skipped; say so in the final report.

### 3. Collect maintainer answers

Subagents cannot ask the user. Take `questions` from the audit (five at most, most valuable
first) and ask them in one batch now. Write `RUN_DIR/answers.md` as numbered question and
answer pairs. Unanswered or unattended: write `unanswered` for each; the fixer then applies only
evidence-backed changes.

### 4. Phase 1: fixer

Prompt:

> You are the fixer in an oatrta AGENTS.md remediation run. Read and follow
> `SKILL_DIR/references/fixer-brief.md`. REPO=`<repo>` RUN_DIR=`<run dir>` SKILL_DIR=`<skill dir>`.
> Do not ask the user anything. Finish by writing `RUN_DIR/fix-report.md`.

When it returns, check that `fix-report.md` exists and its last line is `STATUS: done`. On
`STATUS: blocked` or a missing report, stop and report why; the snapshot is intact.

### 5. Phase 2: independent auditor

A **new** subagent, not the fixer. Prompt:

> You are an independent auditor of AGENTS.md files. Read and follow
> `SKILL_DIR/references/auditor-brief.md`. REPO=`<repo>` SKILL_DIR=`<skill dir>`
> OUT_JSON=`<run dir>/audit-2.json` OUT_MD=`<run dir>/audit-2.md`.

Do not mention that a fix happened, what changed or what the previous score was.

When it returns, run `run_tools.py validate RUN_DIR/audit-2.json`. If invalid, send the errors
back to the same auditor once; if still invalid, stop and report.

### 6. Phase 3: comparator

A third subagent. Prompt:

> You compare two AGENTS.md audits of the same repository, before and after a fix. Read and
> follow `SKILL_DIR/references/comparator-brief.md`. REPO=`<repo>` RUN_DIR=`<run dir>`
> SKILL_DIR=`<skill dir>`.

When it returns, check that `comparison.json` and `comparison.md` exist.

### 7. Report to the user

First record the result in the audit history, unless the verdict is `regressed` (see below):

```
python SKILL_DIR/scripts/run_tools.py publish <repo> RUN_DIR
```

It creates a new `.oatrta/audit/audit-<timestamp>/` with the re-audit as `audit.json` and `audit.md`, and
the comparison as `remediation.md`. That entry describes the files as they are now, so the next
run starts from it.

Then read `comparison.json` and give, in this order:

1. Verdict (`improved`, `mixed`, `no_change`, `regressed`) and score before → after.
2. Blockers resolved and remaining.
3. Regressions, if any: lost KEEP lines, out-of-scope changes, findings the fix introduced.
4. Files changed, and where the diff is (`RUN_DIR/evidence/diff.patch`).
5. Next step:
   - `improved`: review the diff, then commit. Nothing is committed by this skill.
   - `mixed`: review the listed regressions; offer another round.
   - `no_change`: the score moved within audit noise; say what blocked progress (usually
     unanswered maintainer questions).
   - `regressed`: offer to restore. Restore only after the user agrees:
     `python SKILL_DIR/scripts/run_tools.py restore <repo> RUN_DIR`. After a restore the
     input audit describes the files again; do not publish. If the user keeps the changes,
     publish as above.
6. The new `.oatrta/audit/` entry, to commit together with the AGENTS.md changes.

### Rounds

Default is one round. If the user asked to iterate ("until it's an A"), start a new run with the
previous `audit-2.json` as the new `audit-1.json` and repeat steps 2 to 7. Stop at grade A, at a
`regressed` or `no_change` verdict, or after 3 rounds, whichever comes first.

## Rules

- Never commit, stash, reset or check out. The user reviews and commits.
- Never edit or delete existing entries in `.oatrta/audit/`; only `publish` adds new ones.
- Write only under `.oatrta/remediate/` (the run) and, through `publish`, `.oatrta/audit/`.
- Never edit AGENTS.md from the orchestrator, even to fix a small leftover. Leftovers go to the
  next round.
- Never pass audit-1, fix-report or the diff to the auditor.
- The run directory is evidence. Do not delete it; tell the user where it is.
