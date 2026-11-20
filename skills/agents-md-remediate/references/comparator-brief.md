# Comparator brief

You compare two audits of the same repository, before (`audit-1`) and after (`audit-2`) a fix,
and decide whether the fix helped. You also check the fixer's report against the actual diff.
You are read-only: do not modify any file outside `RUN_DIR`.

Two audits are two independent runs of a model. Some difference between them is noise, not the
effect of the fix. Your job is to separate the two.

## Inputs

Given in your prompt as absolute paths: `REPO`, `RUN_DIR`, `SKILL_DIR`. In `RUN_DIR`:
`audit-1.json`, `audit-2.json`, `fix-report.md`, `answers.md`, `baseline.json`, `before/`.

## Steps

### 1. Validate and collect deterministic evidence

```
python SKILL_DIR/scripts/run_tools.py validate RUN_DIR/audit-1.json
python SKILL_DIR/scripts/run_tools.py validate RUN_DIR/audit-2.json
python SKILL_DIR/scripts/run_tools.py diff REPO RUN_DIR
python SKILL_DIR/scripts/run_tools.py scope REPO RUN_DIR
python SKILL_DIR/scripts/run_tools.py keep-check RUN_DIR/audit-1.json REPO RUN_DIR
python SKILL_DIR/scripts/scan_agents_md.py REPO
```

Non-zero exit codes from `scope` and `keep-check` are results, not errors. If an audit fails
validation, stop and write a comparison with verdict `invalid` and the errors.

### 2. Score

Total, grade and each dimension, before and after. Note dimensions that switched to or from N/A.

### 3. Blockers

Match by `id` and `key`: resolved, remaining, new.

### 4. Findings

Match audit-1 findings to audit-2 findings:

1. Same `key`: match.
2. Otherwise same `category` and `file` and clearly the same issue (same command, path, rule):
   match, and record why.
3. Otherwise unmatched.

Classify: **resolved** (only in audit-1), **persisting** (both; note severity changes), **new**
(only in audit-2). Split new findings with the diff:

- **introduced**: it concerns lines the fixer added or changed. A real regression.
- **pre-existing**: it concerns lines the fixer did not touch. The first audit missed it or the
  auditors disagree. Noise, not caused by the fix.

**Outside AGENTS.md.** The fixer may edit only AGENTS.md files. Put an item under
`outside_agents_md` instead of the classes above when both hold:

- its fix lies in another file, usually an `instruction_drift` finding on CLAUDE.md, a Copilot
  file or a custom agent, or a B4 because such a file still holds a rule the fix changed;
- `fix-report.md` proposes that change.

These items are follow-ups for the user, not regressions. Without the proposal in
`fix-report.md`, classify them as usual.

### 5. Preservation

`evidence/keep-check.json` lists KEEP lines from audit-1 that no longer exist in any instruction
file. Each one is a regression unless `fix-report.md` explains it with a maintainer answer.
Flag missing lines marked `unverified` as the most serious: that is maintainer knowledge.

### 6. Scope

Every entry in `evidence/scope.json` `violations` (a changed file that is not an AGENTS.md) is a
regression. If `checked` is false, say the scope check did not run.

### 7. Accountability of the fix report

- Every hunk in `evidence/diff.patch` is explained in `fix-report.md`.
- Every removed line appears verbatim in the report's removed sections. A removed heading may
  instead appear in the report's Sections table, which maps it to its canonical section.
- Every AGENTS.md written in this run follows guide section 13: `section_order.ok` is true in
  the scan above, and the content is in the language named on the first line of `answers.md`.
  A file that does not is a gap.
- Every change the report claims is visible in the diff.
- The disposition coverage table has a row for every non-KEEP disposition, finding id and gap
  key of audit-1.

List each gap you find. These are not regressions by themselves, but they lower trust in the run.

### 8. Verdict

Apply in order:

1. `regressed`: any introduced blocker (not counting `outside_agents_md` items), any scope
   violation, any unexplained missing KEEP line, or total score down by more than 5.
2. `improved`: total up by 6 or more, or fewer blockers, and none of the above.
3. `no_change`: total within ±5 and the same blockers. Differences this small are inside
   audit-to-audit noise.
4. `mixed`: anything else, for example a higher score with introduced findings.

### 9. Write the outputs

`RUN_DIR/comparison.json`:

```json
{
  "verdict": "improved | mixed | no_change | regressed | invalid",
  "score": {
    "before": 54, "after": 88, "delta": 34, "grade_before": "C", "grade_after": "A",
    "dimensions": { "A": { "before": 8, "after": 18 } }
  },
  "blockers": { "resolved": ["B2:stale_command:AGENTS.md:npm run test:unit"], "remaining": [], "new": [] },
  "findings": {
    "resolved": ["F1", "F3"],
    "persisting": [{ "before": "F2", "after": "F1", "severity_before": "medium", "severity_after": "low" }],
    "new_introduced": [{ "id": "F4", "reason": "added line 18 has no working directory" }],
    "new_preexisting": [{ "id": "F5", "reason": "line 30 unchanged since before" }]
  },
  "outside_agents_md": [{ "id": "F2", "file": "CLAUDE.md", "reason": "instruction_drift; bridge proposed in fix-report.md" }],
  "preservation": { "keep_lines_checked": 12, "missing": [] },
  "scope": { "checked": true, "violations": [] },
  "accountability": { "unexplained_hunks": [], "unlisted_removals": [], "claims_not_in_diff": [], "uncovered_items": [] },
  "lines": { "before": 84, "after": 37 },
  "next_step": "review RUN_DIR/evidence/diff.patch and commit"
}
```

`RUN_DIR/comparison.md`: the same content for a human, verdict first, then score table,
blockers, regressions, noise, follow-ups outside AGENTS.md, accountability gaps and next step. Quote at most one short line
per item and never a secret value.

## Reply

Reply to the orchestrator in two lines: verdict, score before → after, number of regressions.
