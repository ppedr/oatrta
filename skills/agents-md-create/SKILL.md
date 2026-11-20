---
name: agents-md-create
description: Create AGENTS.md files for a repository that has none, or add nested AGENTS.md files where a monorepo or multi-language repo needs them, grounded in repository evidence and maintainer answers instead of generic boilerplate. Use when the user asks to create, write, generate, bootstrap, add or scaffold an AGENTS.md ("criar AGENTS.md"), asks whether a repo needs more AGENTS.md files, wants agent instructions for a service or package, or when an audit reports missing files.
---

# AGENTS.md create

Write new AGENTS.md files that follow `references/guide.md`. Read the guide first, in
particular section 6: generated context files tend to underperform files written by developers,
and they mostly fail by restating what the agent can already discover. This skill exists to
avoid that failure.

So the job is **not** to describe the repository. The job is to find the few facts that change
what an agent does here, verify them, get the rest from a maintainer, and write only that.

## Hard rules

1. **Evidence or answer.** Every line traces to a repository file or to something the user said.
   Keep the trace; it goes in the report.
2. **Pass the one test.** If the agent would do the same without the line, the line is not
   written.
3. **Small is a valid result.** If the repository yields eight useful lines, deliver eight lines.
   Never pad with overview, stack description, directory tree or generic advice.
4. **No file without content.** A nested file is created only when it has area-specific
   instructions. "No AGENTS.md needed here" is a legitimate answer; say it.
5. **Never overwrite.** If the target AGENTS.md exists, switch to `agents-md-audit` and
   `agents-md-refactor` for that file.
6. **No secrets, no private operational details.**

## Workflow

### 1. Scan

```
python <skill-dir>/scripts/scan_agents_md.py <repo-root> --format json
```

Use: existing AGENTS.md files, other instruction files, manifest directories,
`nested_candidates`, tooling present.

If other instruction files exist (CLAUDE.md, GEMINI.md, Copilot instructions or custom agents,
Cursor rules), read them. They are prior maintainer knowledge: mine them with the same filter as
everything else, and plan for AGENTS.md to become the single source they point to (guide section
12.1). Do not edit them unless asked. Tool-specific lines stay in the tool's file.

### 2. Decide the topology

- Start from one root file.
- Add a nested file for a directory only when both are true:
  1. it sits on a real boundary: different language, build system, validation process,
     architecture or ownership (CODEOWNERS helps);
  2. it has rules that differ from the root: its own commands, version, migration rules.
- Root gets repository-wide rules. Nested files get area rules and never repeat the root.
- When asked "does this repo need more files?", answer per candidate with the reason, including
  the candidates that do not qualify.

State the planned file list before writing when it is more than one file.

### 3. Mine evidence

In order of trust:

1. **CI config.** The commands and directories that gate a merge are the ground truth for
   validation.
2. **Task runners and manifests.** Makefile, justfile, package scripts, Maven or Gradle setup.
   Look for targets that wrap raw tools with flags, environment or ordering: that is exactly the
   non-obvious tooling choice worth writing down.
3. **Generation and restricted paths.** Codegen configs, `.gitattributes`, "DO NOT EDIT"
   headers, vendored directories, lockfiles with special handling.
4. **Lint and static-analysis configs.** What is already enforced needs at most a pointer.
5. **CONTRIBUTING, README, architecture docs, ADRs.** Link to them. Extract only rules an agent
   must have in context, such as a compatibility policy.
6. **Layout and imports.** Only to confirm ownership or dependency direction that names do not
   reveal.
7. **History, if available and cheap.** Recent reverts, "fix lint" or "fix CI" follow-up commits
   and repeated review comments point at instructions that would have prevented them.

Produce a candidate list. For each candidate keep: the instruction, its evidence, and which
guide category it fills (layout, commands, tooling choice, boundary, definition of done,
convention).

### 4. Filter

Drop every candidate that an agent would infer in seconds from a manifest or the tree, that is
generic advice, or that duplicates a doc (keep a one-line pointer if the doc matters). What
remains is usually short. That is correct.

### 5. Interview the maintainer

The highest-value content is not in the repository. Ask up to five questions in one batch,
phrased against what you found.

Always ask question 1, and name in it every item the repository does not settle, adapted to
what exists here. Do not shorten the list: each item left out is a rule the file cannot have.

1. Which actions need human approval first, and which must an agent never do? Name: migrations,
   dependency upgrades, public API or schema changes, releases, CI configuration, deploy or
   production configuration, deleting, skipping or weakening a failing test, committing,
   pushing, opening pull requests.

The other four are examples:

2. Which mistakes do reviewers correct again and again?
3. For `<pattern found>`, which file is the canonical example to copy?
4. Is there a dependency direction or layer rule not enforced by tooling?
5. Anything that looks editable but must not be edited, or looks dead but is not?

Skip questions the repository already answered. Any item of question 1 left unanswered goes
under "Open questions for maintainers" in the report, by name. If nobody can answer (unattended
run), write only the evidence-backed lines and list the questions in the report. Do not put TODO
placeholders in the file.

### 6. Verify commands

For every command going into the file:

- confirm it resolves (script, target, wrapper exists in the stated directory);
- run it when it is cheap and non-destructive and the environment allows (lint, a scoped unit
  test, a dry run);
- otherwise mark it "not executed" in the report. Never present an untested command as tested.

### 7. Write

Start from `references/template.md`. Delete every section with nothing consequential to say.
The remaining sections keep the template's English headings and order (guide section 13), in
root and nested files alike; never rename, translate, reorder or add a `##` section.

- Exact commands with the working directory, under `## Commands`.
- Name files and paths; no "follow existing patterns".
- Keep "ask first" apart from "never" when the maintainer gave both.
- No toolchain version a manifest already pins (guide section 12.3).
- One instruction per bullet. Add the reason when it prevents a wrong workaround.
- Definition of done separates quick iteration checks from the full pre-finish check and scales
  with the change.
- Link instead of copying.
- Write the content in the language the user asked for, else the one they write to you in
  (guide section 13). Headings stay in English.

### 8. Self-audit

Run the scanner again and score the new files with the rubric (guide section 8). Required before
delivery: no blockers, `section_order.ok` true for every new file, no generic-phrase or overview
hits that survive a second look, grade A.
If it falls short because knowledge is missing, deliver the smaller accurate file and say what
is missing; do not fill the gap with guesses.

### 9. Report

```markdown
# AGENTS.md created: <repo>

## Files
| File | Lines | Scope |

## Why these files (topology)
<candidates accepted and rejected, with reasons>

## Evidence
| Instruction (short) | Source |
| "From services/api, run make test-unit" | .github/workflows/ci.yml:31, executed OK |
| "Schema changes need approval" | maintainer answer |

## Commands not executed
## Open questions for maintainers
## Suggested follow-ups
<rules better enforced by tooling; for each other instruction file, the bridge text from guide
section 12.1 to replace it with, keeping its tool-specific lines>
```

Close with the evaluation advice: try representative tasks with the agents the team uses, with
and without the file, and check how each agent discovers nested files. Update the file when
agents repeat a mistake; delete lines that stop changing behavior.
