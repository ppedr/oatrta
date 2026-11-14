# Expected results on the sample repository

Check a skill workflow by hand after changing its SKILL.md or its `references/`:

```
python evals/make_sample_repo.py <empty dir>     # add --without-agents-md for agents-md-create
# open <empty dir> in Claude Code or Copilot CLI with oatrta installed, run the skill
python evals/check_sample.py <empty dir> --stage <audit|refactor|create|remediate>
```

`check_sample.py` covers what code can check. Then read the skill's output against this file:
it is the part only a person can judge. Use a fresh sample repo for every run.

## What the sample repository contains

A monorepo: a Go service in `services/api` with its own Makefile, a web app in `web`, protobuf
sources in `proto/` generated into `gen/`, append-only `migrations/`, a CI workflow and a
CONTRIBUTING.md. The planted defects in its AGENTS.md:

| Id | Line in AGENTS.md | Defect | Correct verdict |
|---|---|---|---|
| D1 | "This project is a monorepo built with Go and React..." | Overview prose, discoverable | CUT |
| D2 | The `├──` tree under "Structure" | Directory listing | CUT |
| D3 | "Run the unit tests with `npm run test:unit`." | Stale command: `web/package.json` has no such script | FIX, blocker B2 |
| D4 | "Run the tests." | No command, no directory; CI runs `make test` in `services/api` and `npm test` in `web` | SHARPEN |
| D5 | "Write clean code and follow best practices." | Generic advice | CUT |
| D6 | "Deploy token: ghp_..." | Secret (fake) | REDACT, blocker B1 |
| D7 | "Ask before changing files under `migrations/`; merged migrations are append-only." | None: maintainer knowledge the repo cannot prove | KEEP, unverified |
| D8 | "Release with `scripts/release.sh`." | Stale path | FIX or CUT, blocker B3 |
| D9 | The three "Commits" bullets | Copy of CONTRIBUTING.md | MOVE:link |
| D10 | "## Security" | Empty heading | CUT |
| D11 | "Go code in `services/api` must be built with `make build`..." | Correct and useful, but Go-only | KEEP or MOVE:nested to `services/api/AGENTS.md` |
| D12 | "Follow existing patterns for new HTTP handlers." | Vague; `services/api/internal/http/orders_handler.go` exists, but only a maintainer can say it is canonical | SHARPEN after a maintainer answer, otherwise a question |
| OK | "From `web`, run `npm test`." | None | KEEP |

Gaps the repository proves:

| Id | Gap | Evidence |
|---|---|---|
| G1 | `gen/` is generated; edit `proto/` and run `make generate` in `services/api` | `gen/orders.pb.go` header, `.gitattributes`, `buf.gen.yaml`, Makefile `generate` |
| G2 | CI runs `make lint` in `services/api`; the file never mentions lint | `.github/workflows/ci.yml` |
| G3 | `services/api` is a real boundary (Go, own Makefile) with no nested file | `services/api/go.mod`, `services/api/Makefile` |

## agents-md-audit

Must:
- Report blockers B1 (D6), B2 (D3), B3 (D8) and cap the grade at C or lower.
- Never print the token value, in chat or in `.oatrta/audit/`; say it must be rotated.
- Classify D1, D2, D5, D10 as CUT, D4 as SHARPEN, D9 as MOVE:link, D7 as KEEP with
  `"unverified": true`, OK as KEEP.
- Report G1 and G2 as gaps and `services/api` as a nested candidate (G3).
- Ask about D12 (which handler is canonical) and about actions that need approval.
- Write `.oatrta/audit/audit-<timestamp>/audit.json` and `audit.md`, and change no other file.

Must not:
- Call a missing section a finding ("no testing section"), or suggest adding an overview.
- Treat D7 as a finding because it cannot be verified.
- Quote more than one short line per finding.

## agents-md-refactor

Must:
- Ask the D12 question (and others) in one batch before editing.
- Leave D7 and OK byte for byte.
- Fix D3 from evidence (`npm test` in `web`), sharpen D4 with the directories from CI, replace D9
  with a link to CONTRIBUTING.md, remove D1, D2, D5, D10, remove D6 and tell you to rotate it.
- Add G1 and G2 as instructions; handle D8 as "removed pending confirmation" unless you answer.
- Change only AGENTS.md files; show every removed line verbatim in the report.

Must not:
- Invent a canonical handler for D12 without your answer.
- Rewrite KEEP lines for style.

## agents-md-create (sample made with `--without-agents-md`)

Must:
- Propose a root file and decide on `services/api/AGENTS.md` with a reason (G3).
- Take commands from CI with their directories (`make lint`, `make test` in `services/api`;
  `npm test` in `web`) and say which ones it ran.
- Document G1 (edit `proto/`, run `make generate`, do not edit `gen/`).
- Ask about approvals, D7-like rules and the canonical handler instead of guessing.
- Self-audit to grade A, or deliver a smaller file and say what is missing.

Must not:
- Add an overview, a tree, a stack description or generic advice.

## agents-md-remediate

Must:
- Ask the audit's questions before spawning the fixer.
- Spawn three separate subagents in order; the auditor prompt contains no audit-1 content.
- End with verdict `improved` (or `mixed` with the regressions listed), no scope violations, no
  lost KEEP line.
- Add a new `.oatrta/audit/` entry with `remediation.md`; commit nothing.

Must not:
- Edit AGENTS.md from the orchestrator.
- Publish the re-audit after a `regressed` verdict that you chose to restore.
