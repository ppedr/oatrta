---
name: agents-md-refactor
description: Refactor existing AGENTS.md files so every line earns its place - cut noise, sharpen vague rules with repository evidence, fix stale commands and paths, split content between root and nested files, replace duplicated docs with links. Use when the user asks to refactor, improve, fix, clean up, tighten, shrink, reorganize, split or modernize an AGENTS.md ("refatorar/melhorar o AGENTS.md"), or to apply the results of an AGENTS.md audit. Requires an existing AGENTS.md; for a repo without one use agents-md-create.
---

# AGENTS.md refactor

Rewrite existing AGENTS.md files to follow `references/guide.md`, changing as little
maintainer-authored knowledge as possible. Read the guide first.

A refactor is successful when the file is **shorter or equal in noise, higher in signal, and
100% accurate**. It is not a rewrite in your own voice.

## Hard rules

1. **Never invent.** Every new or sharpened instruction is backed by repository evidence (cite
   the file) or by an answer from the user. If neither exists, ask or leave it out.
2. **Maintainer knowledge is protected.** Instructions you cannot verify but that plausibly
   encode experience (approval rules, warnings about a fragile subsystem) stay, word for word,
   unless they are provably stale.
3. **Nothing disappears silently.** Every cut or moved line appears in the change report with its
   original text.
4. **No secrets survive, none get echoed.** REDACT lines are removed, reported by line and type
   only, with a note that the credential must be rotated.
5. **Instruction files only.** Do not change linter configs, CI or code. Tooling changes are
   proposals in the report.
6. **Do not commit.** Leave changes in the working tree for review unless the user asks.

## Workflow

### 1. Get the audit

If an audit from `agents-md-audit` exists, in the conversation or as an `audit.json` file,
use its line dispositions, gaps and maintainer questions. An `audit.json` is only usable if the
AGENTS.md files have not changed since it was written (compare its `files[].sha256`); if they
changed, its line numbers are wrong, so re-audit. Otherwise run the audit workflow now,
including the scanner:

```
python <skill-dir>/scripts/scan_agents_md.py <repo-root> --format json
```

Record the **before** score.

If no AGENTS.md exists, stop and hand over to `agents-md-create`.

### 2. Ask what only a human knows

Before editing, collect the open questions that block a SHARPEN or FIX and ask them in one
batch, five at most, most valuable first. Typical ones:

- "Line 12 says 'follow existing patterns' for handlers. Which file is the canonical example?"
- "`scripts/release.sh` no longer exists. Was it replaced by the `release` workflow, or should
  the instruction go?"

If nobody can answer (unattended run), apply only evidence-backed changes and list the questions
in the report.

### 3. Plan

Turn the dispositions into a change plan grouped by file. Show it compactly before large edits
(more than about a third of a file removed, or any file created or deleted):

```
AGENTS.md            84 → ~35 lines   CUT 31, SHARPEN 6, FIX 2, MOVE 10, KEEP 35
services/api/AGENTS.md  new           receives 8 lines moved from root
```

Proceed directly when the user already asked for the refactor to be applied.

### 4. Apply, by verdict

| Verdict | What to do |
|---|---|
| KEEP | Do not touch, not even wording or formatting |
| SHARPEN | Replace the vague rule with the exact file, path, command or dependency direction. Keep the author's intent and tone. One instruction in, one instruction out |
| FIX | Correct the command or path from evidence (CI config beats README). If the right value is ambiguous and nobody answered, remove the line and report it under "Removed pending confirmation" |
| MOVE:nested | Move to the AGENTS.md of the area it governs. Create that file only on a real boundary (guide section 5) and only if it ends up with content that passes the one test |
| MOVE:root | Move a repository-wide rule out of a nested file into the root |
| MOVE:link | Replace the copied block with one line pointing to the existing doc. First confirm the doc really contains that content |
| MOVE:tooling | If the tool already enforces it: replace the rule with a pointer to the command that checks it. If not: keep the rule for now and propose the tooling change in the report |
| CUT | Delete. Delete headings left empty by the cuts |
| REDACT | Delete, report by line and type |

Then add **evidence-backed gaps** from the audit (missing working directories, undocumented CI
gate, generated paths). Add only what passes the one test. Do not add gaps that are guesses.

### 5. Restructure lightly

- Commands with working directories first or near the top; boundaries and definition of done
  easy to find. Keep the author's section names when they work.
- Commands in code blocks or inline code, copy-paste exact.
- Bullets over paragraphs. One instruction per bullet.
- State the reason when it prevents a wrong workaround ("the target injects build tags").
- No section exists only to look complete.
- Nested files do not repeat the root.

### 6. Other instruction files

If CLAUDE.md, GEMINI.md, Copilot instructions or custom agents, Cursor rules or similar
duplicate or contradict AGENTS.md (`instruction_drift`), do not edit them by default. Report the
overlap and, for each file, propose the bridge from guide section 12.1 written out in full: the
`@AGENTS.md` import or the pointer line, followed by the tool-specific lines worth keeping.
Recommend the import over a symlink when the team uses Windows. Apply only on request.

Before deleting a rule from AGENTS.md, check whether another tool's file copies it. If one does,
say in the report that the copy is now stale and that the bridge removes it.

Tool-specific content found in AGENTS.md (one agent's commands or settings) is not cut: move it
to the proposal for that tool's file.

### 7. Verify

- Rerun the scanner. Zero unresolved commands, zero missing paths, zero secrets, zero empty
  headings.
- Re-score with the rubric. Record the **after** score. If it did not improve, or a blocker
  remains, say why.
- Reread each changed file once as an agent with no context: is anything now ambiguous that was
  clear before?

### 8. Report

```markdown
# AGENTS.md refactor: <repo>

Score <before> → <after> (<grade> → <grade>). Lines <before> → <after>.

## Changed files
| File | Lines | Summary |

## Sharpened and fixed
- `AGENTS.md:22` "Run the tests." → "From `services/api`, run `make test-unit`."
  (evidence: `.github/workflows/ci.yml:31`)

## Removed
<verbatim original lines, grouped by reason: generic, discoverable, listing, duplicated doc>

## Removed pending confirmation
<stale lines whose correct replacement is unknown, verbatim, with the question>

## Kept unverified
<maintainer-knowledge lines kept as is>

## Proposed outside AGENTS.md
<tooling rules to add; for each other instruction file, the bridge text to replace it with>

## Open questions
```

Close by telling the user to try the refactored file on a couple of real tasks with their
agents; the score is a proxy.
