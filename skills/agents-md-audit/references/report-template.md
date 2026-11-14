# Audit report template

Fill every section that has content. Delete sections that would be empty.

```markdown
# AGENTS.md audit: <repository name>

**Grade <A|B|C|D>, <score>/100.** <n> file(s) audited, <n> blocker(s).
<Two or three sentences: is the file helping, what is the single most valuable change.>

## Scorecard

| Dimension | Score | Why |
|---|---|---|
| A Signal density | 14/20 | 9 of 31 instructions are generic or discoverable |
| B Commands | 6/15 | test command has no working directory; lint missing |
| C Boundaries | N/A | no generated code, single layer (renormalized) |
| D Definition of done | ... | ... |
| E Concrete conventions | ... | ... |
| F Accuracy | ... | ... |
| G Topology and enforcement | ... | ... |

## Blockers

- **B2 Stale command** `AGENTS.md:14` documents `npm run test:unit`; `package.json` has no such
  script (closest: `test`). Fix: replace or remove.

## Findings

Ordered by impact.

### F1 (high) Test command cannot be run as written
- Where: `AGENTS.md:22`
- Now: "Run the tests."
- Evidence: `.github/workflows/ci.yml:31` runs `make test-unit` from `services/api`.
- Fix: "From `services/api`, run `make test-unit`."

### F2 (medium) ...

## Line dispositions

### AGENTS.md

| Lines | Verdict | Note |
|---|---|---|
| 1-6 | CUT | project overview, visible in README |
| 8 | KEEP | approval rule for migrations (unverified, maintainer knowledge) |
| 10-12 | SHARPEN | "follow existing patterns" → name the canonical handler |
| 14 | FIX | stale script name |
| 20-48 | MOVE:link | copy of CONTRIBUTING.md section "Commits" |

Summary: <n> KEEP, <n> SHARPEN, <n> FIX, <n> MOVE, <n> CUT.

## Gaps proven by the repository

- `gen/` is produced by `buf generate` (`buf.gen.yaml`); nothing tells the agent to edit
  `proto/` instead.

## Topology

<Current placement, conflicts, duplicated instruction files, nested candidates and whether each
is justified.>

## Questions for maintainers

Things the repository cannot answer:

1. Which actions need human approval (migrations, dependency upgrades, public API changes)?
2. ...

## Next step

<One of: keep as is / run agents-md-refactor / run agents-md-create for <paths>.>
The score is a proxy. Confirm by running your agents on a few real tasks with and without the file.
```

Severity guide: **high** = agent will do the wrong thing or fail; **medium** = agent wastes
steps or guesses; **low** = noise that costs tokens.
