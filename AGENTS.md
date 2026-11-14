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
  on Windows and Linux. `run_tools.py` imports from `scan_agents_md.py`; keep them side by side.
- Rubric points, blockers, verdict names and finding categories are defined in
  `shared/guide.md` and repeated in `shared/audit-schema.json`, `shared/run_tools.py`
  (`DIMENSION_MAX`, `VERDICTS`, `CATEGORIES`), every SKILL.md and
  `skills/agents-md-audit/references/report-template.md`. Rename in all of them together.
- Everything the skills write in a target repo goes under `.oatrta/<skill>/` (`audit`,
  `remediate`). The paths are constants at the top of `shared/run_tools.py`; skills get them from
  its subcommands and never build them by hand.
- Changing a field in `shared/audit-schema.json` means updating `cmd_validate` in
  `shared/run_tools.py` and the briefs in `skills/agents-md-remediate/references/`.

## Done means
- `python scripts/sync_shared.py --check` exits 0.
- `python shared/scan_agents_md.py . --format md` reports no blocker hints for this repo.
