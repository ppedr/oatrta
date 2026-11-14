# oatrta

A skill pack for `AGENTS.md` files: audit, refactor and create them, following the guide
[Writing an effective AGENTS.md](https://aaif.io/blog/writing-an-effective-agents-md) (AAIF).

| Skill | Service | Changes files? |
|---|---|---|
| `agents-md-audit` | 0 to 100 score, blockers, line-by-line verdicts, gaps proven by the repo | No |
| `agents-md-refactor` | Applies the audit: cuts noise, makes vague rules exact, fixes commands and paths, splits root and nested files | Yes, AGENTS.md only |
| `agents-md-create` | Creates the root file and any nested files needed, from repo evidence and maintainer questions | Yes, new files only |

Flow: `audit` decides the next step. A low score with salvageable content goes to `refactor`.
No file, or missing nested files, goes to `create`. Both `refactor` and `create` re-run the rubric
at the end.

## Principle

One test for every line: would the agent act differently because it read this? If not, it goes.
The guide cites evidence that LLM-generated files perform worse than developer-written ones, so
the skills never invent content: every line comes from a repo file or a maintainer answer.

## Layout

```
shared/                      single source of truth
  guide.md                   criteria, rubric (A to G), blockers (B1 to B4), verdicts
  scan_agents_md.py          deterministic scanner, standard library only
scripts/sync_shared.py       copies shared/ into every skill
skills/
  agents-md-audit/           SKILL.md, references/report-template.md
  agents-md-refactor/        SKILL.md
  agents-md-create/          SKILL.md, references/template.md
.claude-plugin/              plugin.json and marketplace.json (Claude Code and Copilot CLI)
```

Each skill carries its own copy of `guide.md` and the scanner so it works when installed alone.
Always edit in `shared/` and run `python scripts/sync_shared.py` (`--check` for CI).

## Installation

Claude Code:

```
/plugin marketplace add ppedr/oatrta
/plugin install oatrta@oatrta
```

GitHub Copilot CLI:

```
copilot plugin marketplace add ppedr/oatrta
copilot plugin install oatrta@oatrta
```

Both read the same `.claude-plugin/marketplace.json`.

Without the plugin: copy the folders under `skills/` into `.claude/skills/` (read by both
Claude Code and Copilot), `.github/skills/` (Copilot) or, for personal use, `~/.claude/skills/`
and `~/.copilot/skills/`.

The scanner requires Python 3.

## Scanner

```
python shared/scan_agents_md.py <repo> --format md
```

It collects facts and does not score: AGENTS.md files and their size, commands that do not
resolve (npm script, make target, wrapper), missing paths, generic phrases, overview prose, empty
headings, directory trees, possible secrets, other instruction files (CLAUDE.md, Copilot,
Cursor), directories with manifests and candidates for nested AGENTS.md files. The skill does the
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
