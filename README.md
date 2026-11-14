# oatrta

A skill pack for `AGENTS.md` files: audit, refactor and create them, following the guide
[Writing an effective AGENTS.md](https://aaif.io/blog/writing-an-effective-agents-md) (AAIF).

| Skill | Service | Changes files? |
|---|---|---|
| `agents-md-audit` | 0 to 100 score, blockers, line-by-line verdicts, gaps proven by the repo | No |
| `agents-md-refactor` | Applies the audit: cuts noise, makes vague rules exact, fixes commands and paths, splits root and nested files | Yes, AGENTS.md only |
| `agents-md-create` | Creates the root file and any nested files needed, from repo evidence and maintainer questions | Yes, new files only |
| `agents-md-remediate` | Applies an audit and proves the result with three isolated subagents: fixer, independent re-auditor, comparator | Yes, AGENTS.md only |

Flow: `audit` decides the next step. A low score with salvageable content goes to `refactor`
(interactive) or `remediate` (verified). No file, or missing nested files, goes to `create`.

## Remediation run

`agents-md-remediate` consumes an `audit.json` and runs three subagents one after another, each
with a fresh context:

1. **Fixer** applies the audit to AGENTS.md files and writes a report of every change.
2. **Auditor** audits the result from scratch. It never sees the first audit or the fixer's
   report, so the fix is not graded by the agent that made it.
3. **Comparator** matches the two audits finding by finding, separates real regressions from
   audit-to-audit noise, checks that no KEEP line was lost, that only AGENTS.md files changed,
   and that the fixer's report matches the actual diff. Verdict: `improved`, `mixed`,
   `no_change` or `regressed`.

## Audit history

Everything oatrta writes in a repository lives under `.oatrta/<skill>/`, and the whole folder
is kept out of git:

```
.oatrta/
  audit/
    audit-20261114T025000Z/      audit.json, audit.md
    audit-20261114T031200Z/      audit.json, audit.md, remediation.md
  remediate/
    run-20261114T030500Z/        snapshot, both audits, diff, reports
```

Every audit is written to `.oatrta/audit/audit-<UTC timestamp>/` as `audit.json` (format:
`shared/audit-schema.json`) and `audit.md`, so the repo keeps a local history of how its
AGENTS.md files scored over time. Entries are never edited; each audit adds a folder.

The skills add `/.oatrta/` to `.git/info/exclude`, a local ignore file that is not versioned
and does not change any project file. Nothing under `.oatrta/` shows up in `git status` or
gets committed. To share the history with your team, delete that line and commit the folder.

`agents-md-remediate` uses the newest entry by default, or the one you name:

```
run agents-md-remediate with .oatrta/audit/audit-20261114T025000Z
```

After a run that is not reverted, it adds a new entry with the re-audit and a
`remediation.md` explaining what changed, so the newest entry always describes the current files.

## Run evidence

Each remediation run keeps its working evidence in `.oatrta/remediate/run-<UTC timestamp>/`
(snapshot, both audits, diff, reports). A regressed run can be restored from the snapshot.

## Principle

One test for every line: would the agent act differently because it read this? If not, it goes.
The guide cites evidence that LLM-generated files perform worse than developer-written ones, so
the skills never invent content: every line comes from a repo file or a maintainer answer.

## Layout

```
shared/                      single source of truth
  guide.md                   criteria, rubric (A to G), blockers (B1 to B4), verdicts
  audit-schema.json          format of audit.json
  scan_agents_md.py          deterministic scanner, standard library only
  run_tools.py               audit validation, staleness, run snapshot, scope, diff, restore
scripts/sync_shared.py       copies shared sources into the skills that need them
skills/
  agents-md-audit/           SKILL.md, references/report-template.md
  agents-md-refactor/        SKILL.md
  agents-md-create/          SKILL.md, references/template.md
  agents-md-remediate/       SKILL.md, references/{fixer,auditor,comparator}-brief.md
.claude-plugin/              plugin.json and marketplace.json (Claude Code and Copilot CLI)
```

Each skill carries its own copies of what it needs (guide, scanner, schema, and for
`remediate` the audit and refactor procedures) so it works when installed alone.
Always edit in `shared/` and run `python scripts/sync_shared.py` (`--check` for CI).

## Installation

From a terminal:

```
# Claude Code
claude plugin marketplace add ppedr/oatrta
claude plugin install oatrta@oatrta

# GitHub Copilot CLI
copilot plugin marketplace add ppedr/oatrta
copilot plugin install oatrta@oatrta
```

Inside a running session, the same commands work as `/plugin ...` (for example
`/plugin marketplace add ppedr/oatrta`). Both agents read the same
`.claude-plugin/marketplace.json`.

## Updating

```
# Claude Code
claude plugin marketplace update oatrta
claude plugin update oatrta@oatrta

# GitHub Copilot CLI
copilot plugin marketplace update oatrta
copilot plugin update oatrta
```

Start a new session afterwards (`/reload-plugins` in Claude Code, `/restart` in Copilot CLI).
Releases bump `version` in `.claude-plugin/plugin.json`, the only place it is set; without a
new version, installed copies are not updated.

Without the plugin: copy the folders under `skills/` into `.claude/skills/` (read by both
Claude Code and Copilot), `.github/skills/` (Copilot) or, for personal use, `~/.claude/skills/`
and `~/.copilot/skills/`.

The scanner and `run_tools.py` require Python 3. `agents-md-remediate` needs an agent that
can spawn subagents (Claude Code, Copilot CLI, VS Code Copilot with `runSubagent` enabled) and
works best in a git repository.

## Checking the skills

`scripts/smoke_test.py` (run in CI on Linux and Windows) covers the scripts. The skill
workflows need a model, so they run on a generated sample repository with planted defects:

```
python evals/run_eval.py                     # all four skills, in parallel
python evals/run_eval.py --stages audit      # one of them
```

For each skill it makes a fresh sample, runs the skill in headless Claude Code with this checkout
as the plugin, answers the maintainer questions, runs `evals/check_sample.py`, and has a second
session judge the result against `evals/expected.md`. Results go to
`<temp>/oatrta-evals/<timestamp>/report.md`. It needs the `claude` CLI, logged in, and costs
model usage.

`evals/expected.md` lists every planted defect and what each skill must and must not do with it.

## Scanner

```
python shared/scan_agents_md.py <repo> --format md
```

It collects facts and does not score: AGENTS.md files and their size, commands that do not
resolve (npm script, make target, wrapper), missing paths, generic phrases, overview prose, empty
headings, directory trees, possible secrets, other instruction files (CLAUDE.md and GEMINI.md at
any depth, Copilot instructions and custom agents, Cursor) with the lines they copy from
AGENTS.md, directories with manifests and candidates for nested AGENTS.md files. The skill does the
scoring with the rubric in `guide.md`.

## Rubric

| Dimension | Pts |
|---|---|
| A Signal density | 20 |
| B Commands | 15 |
| C Boundaries | 15 |
| D Definition of done | 15 |
| E Concrete conventions | 10 |
| F Accuracy | 15 |
| G Topology and enforcement | 10 |

Blockers (secret, stale command, stale path, contradiction) cap the grade at C.
