# AGENTS.md

## Generated copies
- Do not edit files that `scripts/sync_shared.py` writes:
  `skills/*/references/guide.md`, `skills/*/references/audit-schema.json`,
  `skills/*/scripts/scan_agents_md.py`, `skills/*/scripts/run_tools.py` and
  `skills/agents-md-remediate/references/*-procedure.md`,
  `skills/agents-md-remediate/references/report-template.md`. The mapping is at the top of the
  script. Edit the source, then run `python scripts/sync_shared.py` from the repo root.

## Rules
- Each folder under `skills/` must work when installed alone. A SKILL.md may only reference
  files inside its own folder; anything shared reaches it through the sync script.
- `shared/guide.md` restates https://aaif.io/blog/writing-an-effective-agents-md as criteria.
  Do not paste text from the post; paraphrase and keep the link.
- `shared/scan_agents_md.py` and `shared/run_tools.py` are standard library only and must run
  on Windows and Linux with Python 3.10 or later. Read and write text as UTF-8 explicitly, build
  paths with `pathlib`, and print repo paths with forward slashes (`rel()`). `run_tools.py` imports from `scan_agents_md.py`; keep them side by side.
- Rubric points, blockers, verdict names and finding categories are defined in
  `shared/guide.md` and repeated in `shared/audit-schema.json`, `shared/run_tools.py`
  (`DIMENSION_MAX`, `VERDICTS`, `CATEGORIES`), every SKILL.md and
  `skills/agents-md-audit/references/report-template.md`; finding categories appear only in the
  first three. Rename in all of them together.
- Everything the skills write in a target repo goes under `.oatrta/<skill>/` (`audit`,
  `remediate`). The paths are constants at the top of `shared/run_tools.py`; skills get them from
  its subcommands and never build them by hand. Every subcommand that creates something under
  `.oatrta/<skill>/` calls `ensure_excluded`, which keeps the whole folder out of git through
  `.git/info/exclude`.
- Changing a field in `shared/audit-schema.json` means updating `cmd_validate` in
  `shared/run_tools.py` and the briefs in `skills/agents-md-remediate/references/`.

## Versioning
- Installed copies only update when `version` changes, so a change that ships to users needs a
  bump: anything under `skills/` or `shared/`, or `.claude-plugin/`. README, this file,
  `scripts/`, `evals/`, `.github/`, `.gitignore` and `.gitattributes` do not: they change nothing an
  installed skill does.
- The version lives only in `.claude-plugin/plugin.json`; bump it there, in the same commit as
  the change. Do not add `version` to `marketplace.json`: Claude Code prefers `plugin.json`
  anyway, and a second copy drifts.
- Bump once per change set: if `git diff origin/main -- .claude-plugin/` already shows a bump,
  do not bump again.
- Until 1.0: minor (`0.4.1` → `0.5.0`) for a new skill, a new `run_tools.py` subcommand, a
  change to `shared/audit-schema.json`, or a changed path under `.oatrta/<skill>/`; patch (`0.4.1` →
  `0.4.2`) for anything else, such as wording or a bug fix.

## Done means
- `python scripts/sync_shared.py --check` exits 0 (copies in sync, no version in
  `marketplace.json`).
- `python scripts/smoke_test.py` passes. It covers the scanner and every `run_tools.py`
  subcommand; when you add a subcommand or change an output field, add an assertion there.
  You can only run it on your own OS: `.github/workflows/ci.yml` runs it on Linux and Windows,
  Python 3.10 and 3.13, so check CI before calling a change to `shared/*.py` done.
- `python shared/scan_agents_md.py . --format md` reports no blocker hints for this repo.
- Changed a SKILL.md or anything in `skills/*/references/`: before releasing, run the changed
  skill by hand on a fresh sample repo and judge the result against `evals/expected.md`:
  1. `python evals/make_sample_repo.py <empty dir>` (add `--without-agents-md` for create).
  2. Run the skill there in Claude Code or Copilot CLI, with the local plugin installed.
  3. `python evals/check_sample.py <dir> --stage <audit|refactor|create|remediate>` must pass.
  4. Read the output against the skill's section in `evals/expected.md`.
  CI cannot do this; it needs a model. If you change a planted defect, update
  `evals/make_sample_repo.py` and `evals/expected.md` together.
