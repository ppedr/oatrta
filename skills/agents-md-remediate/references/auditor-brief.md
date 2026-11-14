# Auditor brief

You audit the AGENTS.md files of a repository from scratch, as they are now. Your audit will be
compared with an earlier one, so it is only useful if it is independent.

## Inputs

Given in your prompt as absolute paths: `REPO`, `SKILL_DIR`, `OUT_JSON`, `OUT_MD`.

## Independence rules

- Do not read anything under `REPO/.oatrta/`, except to write your two output files. It holds
  earlier audits and reports that would bias you.
- Do not look at the history of instruction files: no `git log -p`, `git diff`, `git show` or
  blame on AGENTS.md or other instruction files. Judge the files as they stand.
- Do not try to guess an earlier score. Score what you see.

## Procedure

Follow `SKILL_DIR/references/audit-procedure.md` in **file output mode**, writing `OUT_JSON` and
`OUT_MD`. Where it says `<skill-dir>`, use `SKILL_DIR`. You cannot ask anyone: put what only a
maintainer knows into `questions`.

Two things matter more than usual because a comparator will match your findings with the
earlier audit:

- Give every finding, blocker and gap a stable `key` exactly as the procedure defines it:
  `<category>:<file>:<subject>`, where the subject is the command, path or heading involved, or
  a short kebab-case slug. Never a line number.
- Classify every instruction in `dispositions`, including the KEEP ones.

## Before you finish

```
python SKILL_DIR/scripts/run_tools.py validate OUT_JSON
```

Fix the file until it exits 0. Reply to the orchestrator in two lines: grade, score, number of
blockers and findings.
