---
name: agents-md-audit
description: Audit the AGENTS.md files of a repository and report whether they are good, with a 0 to 100 score, blockers, line-by-line verdicts and evidence-backed gaps. Read-only. Use when the user asks to audit, review, evaluate, score, grade, lint or check an AGENTS.md (or "agent instructions", "context file"), asks "is my AGENTS.md good?", "avaliar/auditar o AGENTS.md", or before refactoring or creating one. Also use when an agent keeps making the same mistake in a repo and the user suspects the instructions.
---

# AGENTS.md audit

Judge whether a repository's AGENTS.md files make an agent act better in this repository.
The audit is **read-only**: it never edits instruction files. Fixes belong to
`agents-md-refactor`; missing files belong to `agents-md-create`.

Read `references/guide.md` before scoring. It holds the criteria, the rubric, the blockers and
the verdict vocabulary. Do not score from memory.

## Principles

- **Evidence over opinion.** Every finding cites a file and line in AGENTS.md plus the repository
  fact that proves it (a manifest, a CI workflow, a missing path). No finding without both.
- **Judge behavior change, not form.** Short is fine. Missing sections are fine when the repo has
  nothing non-obvious to say. Never recommend adding content to look complete.
- **A gap needs proof.** Report a missing instruction only when the repository shows a trap an
  agent would fall into (a Makefile target wrapping the raw command, a generated directory, a CI
  check with no local equivalent documented). "Could add a section about X" is not a finding.
- **Unknown is not wrong.** Instructions that encode maintainer knowledge you cannot verify
  ("never touch the billing migration without approval") are KEEP, flagged as unverified.

## Workflow

### 1. Scan

Run the bundled scanner from the repository root (Python 3, standard library only):

```
python <skill-dir>/scripts/scan_agents_md.py <repo-root> --format json
```

It returns: every AGENTS.md with size and headings, unresolved commands, missing paths, generic
phrases, overview prose, empty headings, directory listings, possible secrets, other instruction
files (CLAUDE.md, Copilot instructions, Cursor rules), manifest directories, nested candidates,
and the tooling present. If Python is unavailable, collect the same facts by hand with file
search.

Scanner hits are **leads**. Confirm each one by reading the line in context. A phrase match
inside a concrete instruction is not a finding. A "missing path" may be an example or a path the
instruction tells the agent to create.

If there is no AGENTS.md at all: stop scoring, report that, list the nested candidates and the
evidence sources found, and recommend `agents-md-create`.

### 2. Build the evidence base

Read what an agent would otherwise have to discover, in this order:

1. CI configuration: what actually gates a merge, with exact commands and directories.
2. Task runners and manifests: Makefile, justfile, package scripts, Maven or Gradle config.
3. Formatter, linter and static-analysis configs: which rules are already enforced.
4. Code generation and restricted paths: generator configs, `.gitattributes`, "DO NOT EDIT"
   headers, vendored code.
5. CONTRIBUTING, README, architecture docs: for duplication checks.
6. Module layout and import direction, only as far as needed to verify a boundary claim.

Keep it proportional. For a small repo this takes a handful of file reads.

### 3. Classify every instruction

Go through each AGENTS.md top to bottom. Give every instruction (bullet, sentence, command
block) one verdict from section 9 of the guide: KEEP, SHARPEN, FIX, MOVE:nested, MOVE:root,
MOVE:link, MOVE:tooling, CUT, REDACT. Apply the one test from section 1 honestly: would the
agent act differently having read this line?

Verify what can be verified:

- Paths exist. Commands resolve to a real script, target or wrapper, in the stated directory.
- Commands match what CI runs. A local command that differs from CI is a finding unless the file
  explains the difference.
- Claims about layering or ownership match the code.
- Run a command only if it is clearly cheap and non-destructive (a lint, a dry run, `--help`)
  and the environment allows it. Otherwise mark it "resolved, not executed".

### 4. Check topology

- Does each nested file sit on a real boundary (language, build system, validation,
  architecture, ownership)?
- Are repository-wide rules at the root and area rules next to the code?
- Do any two files give conflicting instructions for the same code?
- Do other instruction files duplicate or contradict AGENTS.md? Report it; one source of truth
  with pointers is the target.
- Does the scanner list nested candidates with area-specific rules currently crammed into the
  root (or documented nowhere)?

### 5. Find evidence-backed gaps

Compare the evidence base against the file. Typical proven gaps:

- CI runs a check the file never mentions.
- A task-runner target wraps the raw tool with flags; the file documents the raw tool or nothing.
- Generated or vendored directories exist with no "edit the source instead" instruction.
- A multi-project repo whose commands have no working directory.
- No statement of what to run before finishing, while CI has several distinct gates.

Things only a maintainer knows (approval rules, known traps, canonical examples) go under
"Questions for maintainers", not under findings.

### 6. Score

Score dimensions A to G from section 8 of the guide. Apply N/A with a stated reason and
renormalize. Apply blockers B1 to B4; any blocker caps the grade at C. With several files, score
the set as a whole and note per-file outliers.

### 7. Report

Use `references/report-template.md`. Rules:

- Lead with the verdict: grade, score, blockers, the one change that matters most.
- Order findings by impact on agent behavior, not by file position.
- Quote at most one short line per finding; reference the rest by line number.
- If a secret is present, do not repeat its value. Give the line and the type, and say it must be
  rotated, not just deleted.
- End with the next step: nothing (grade A), `agents-md-refactor` (fixable), or
  `agents-md-create` (missing files or grade D with little worth keeping).
- Remind the user once that a score is a proxy: the real test is running the agents they use on
  representative tasks with and without the file.

In chat, give the verdict and the top findings, and point to the files from step 8 for the rest.

### 8. Write the audit files

Every audit is recorded in the repository, so there is a history to compare and to hand to
`agents-md-remediate`. Create the folder:

```
python <skill-dir>/scripts/run_tools.py audit-dir <repo-root>
```

It creates `.audit/oatrta/audit-<UTC timestamp>/` (for example
`.audit/oatrta/audit-20261114T025000Z/`) and prints the paths. Other tools may also write
under `.audit/`; this skill only ever writes inside `.audit/oatrta/`. Write two files there:

- `audit.json`, following `references/audit-schema.json`.
- `audit.md`, the report from step 7.

If a caller passes explicit output paths (the remediate auditor does), write there instead and
do not create a folder under `.audit/`.

The folder is meant to be committed. Do not delete or edit earlier entries; each audit is a new
folder.

Rules for the JSON:

- `repo_root` is `"."`; every path in the file is relative to the repository root. No absolute
  paths, since the file is committed.
- Fill `files` from `python <skill-dir>/scripts/run_tools.py hashes <repo-root>`. The hashes let
  consumers detect that AGENTS.md changed after the audit.
- `git_head` from `git rev-parse HEAD`, or null outside git.
- Every finding, blocker and gap gets a stable `key`: `<category>:<file>:<subject>`. The
  subject is the command, path or heading involved, or a short kebab-case slug of the rule.
  Never a line number. The same issue must produce the same key in a later audit, even after
  lines moved; comparisons depend on it.
- `dispositions` covers every instruction, KEEP included, with line ranges in the file as it is
  now. Mark maintainer knowledge you kept without verifying as `"unverified": true`.
- Never put a secret value in either file. They are committed; a leaked value would land in
  git history.

Validate before finishing, and fix until it exits 0:

```
python <skill-dir>/scripts/run_tools.py validate <audit-dir>/audit.json
```

End the chat reply with the path of the folder, so the user can pass it to `agents-md-remediate`.
