# AGENTS.md

## Generated copies
- `skills/*/references/guide.md` and `skills/*/scripts/scan_agents_md.py` are copies. Edit
  `shared/guide.md` and `shared/scan_agents_md.py`, then run `python scripts/sync_shared.py`
  from the repo root.

## Rules
- Each folder under `skills/` must work when installed alone. A SKILL.md may only reference
  files inside its own folder.
- `shared/guide.md` restates https://aaif.io/blog/writing-an-effective-agents-md as criteria.
  Do not paste text from the post; paraphrase and keep the link.
- `shared/scan_agents_md.py` is standard library only and must run on Windows and Linux.
- Rubric points, blockers and verdict names in `shared/guide.md` are referenced by all three
  SKILL.md files and by `skills/agents-md-audit/references/report-template.md`. Rename in all
  of them together.

## Done means
- `python scripts/sync_shared.py --check` exits 0.
- `python shared/scan_agents_md.py . --format md` reports no blocker hints for this repo.
