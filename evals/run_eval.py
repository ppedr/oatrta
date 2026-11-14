#!/usr/bin/env python3
"""Run the skill evals end to end, without a person at the keyboard.

    python evals/run_eval.py                         # all four stages
    python evals/run_eval.py --stages audit,create   # some of them
    python evals/run_eval.py --out C:/temp/oatrta-evals --jobs 2 --model claude-opus-5-5

For every stage it:
  1. makes a fresh sample repository with evals/make_sample_repo.py;
  2. runs the skill in headless Claude Code (`claude -p`) with this checkout as the only plugin
     (`--plugin-dir`, `--setting-sources project`, so an installed copy of oatrta is not loaded);
  3. when the skill stops to ask the maintainer, resumes the same session with MAINTAINER_ANSWERS;
  4. runs evals/check_sample.py for the stage;
  5. asks a second, read-only session to judge the result against the stage's section of
     evals/expected.md (skip with --no-judge).

Everything lands in <out>/<timestamp>/<stage>/: the sample in repo/, prompts, replies,
transcripts, diff.patch, check.txt, judgment.md and result.json. <out>/<timestamp>/report.md
sums up. Exit 0 when every check and every judge passed.

Needs the `claude` CLI, logged in. Standard library only.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
STAGES = ("audit", "refactor", "create", "remediate")

# What a maintainer would answer. One set for every stage; the skill uses what applies.
MAINTAINER_ANSWERS = """Answers from the maintainer. Use what applies to your questions; for anything not covered here
the answer is "I don't know".

- Canonical example for new HTTP handlers: `services/api/internal/http/orders_handler.go`.
- `scripts/release.sh`: I don't know what replaced it.
- `npm run test:unit`: it was meant to be `npm test` in `web`.
- Go version: `services/api/go.mod` is right; there is no separate version rule.
- Approvals: changes under `migrations/` need approval first. Ask first before editing CI
  configuration, deploy configuration or upgrading dependencies.
- Never: delete, skip or weaken a failing test to get a green run; push; open a pull request.
  Commit only when asked.
- Reviewers do not repeat any particular correction. No layer rule beyond what lint checks.

Continue the skill with these answers."""

FIRST_PROMPT = """Run the oatrta:agents-md-{stage} skill on this repository (the current directory).

Nobody can see tool dialogs in this session. When the skill says to ask the maintainer
something, write the questions in your reply and end your turn; the answers come in the next
message."""

CONTINUE_PROMPT = "Continue the skill to the end."

JUDGE_PROMPT = """You judge one run of the oatrta skill `agents-md-{stage}` on a generated sample repository.
The criteria are in `{expected}`: the defect tables at the top and the section
`## agents-md-{stage}`.

Evidence, all in the current directory:
- `repo/`: the sample repository after the run. `repo/.oatrta/` holds the audit and run files.
  Read only; change nothing there.
- `prompt-<n>.md` and `reply-<n>.md`: what the user sent and what the skill answered, in order.
  `prompt-2.md`, when present, holds the maintainer answers.
- `diff.patch`: changes to tracked files and new files, against the sample's initial commit.
- `check.txt`: the deterministic checks from evals/check_sample.py.

For every "Must" and "Must not" bullet of the section, give PASS, FAIL or UNCLEAR, with one line
of evidence (path:line or a short quote). Judge only what the evidence shows; questions the skill
was never asked to put to the maintainer are not its fault. Then list other problems the section
does not cover, if any, most serious first. Never copy a token or secret value.

Write the result to `judgment.md` in the current directory. Its last line is exactly
`VERDICT: pass` (no FAIL) or `VERDICT: fail`."""

SESSION_TOOLS = "Bash,PowerShell,Read,Glob,Grep,Edit,Write,Skill,Task"
JUDGE_TOOLS = "Read,Glob,Grep,Write"
# Commands the skills run. Anything else is denied and reported in result.json.
ALLOWED = [
    "Skill", "Task", "Read", "Glob", "Grep",
    *(f"{shell}({cmd} *)" for shell in ("Bash", "PowerShell") for cmd in (
        "python", "python3", "py", "git status", "git rev-parse", "git ls-files", "git log", "git diff",
        "git show", "git check-ignore", "git cat-file", "ls", "cat", "head", "tail", "wc", "echo", "grep",
        "find", "sort", "uniq", "pwd", "cd", "mkdir", "cp", "test", "go build", "go vet", "go test",
        "go version", "go list", "make", "npm test", "npm run", "npm ci", "golangci-lint", "buf",
        "Get-Content", "Get-ChildItem", "Test-Path", "Select-String", "Copy-Item", "New-Item",
    )),
]


def find_claude() -> str:
    exe = shutil.which("claude")
    if not exe:
        sys.exit("claude CLI not found on PATH")
    return exe


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


class Session:
    """One headless Claude Code conversation, resumed turn by turn."""

    def __init__(self, cwd: Path, logdir: Path, opts, judge: bool = False, prefix: str = ""):
        self.cwd, self.logdir, self.opts, self.judge, self.prefix = cwd, logdir, opts, judge, prefix
        self.session_id: str | None = None
        self.turns = 0
        self.cost = 0.0
        self.denials: list = []
        self.events: list[dict] = []
        self.errors: list[str] = []

    def command(self) -> list[str]:
        cmd = [self.opts.claude, "-p", "--output-format", "stream-json", "--verbose",
               "--setting-sources", "project", "--strict-mcp-config",
               "--tools", JUDGE_TOOLS if self.judge else SESSION_TOOLS]
        if not self.judge:
            # --add-dir lets the skill read and run its own bundled files without a permission denial.
            cmd += ["--plugin-dir", str(ROOT), "--add-dir", str(ROOT)]
        if self.opts.model:
            cmd += ["--model", self.opts.model]
        if self.opts.budget:
            cmd += ["--max-budget-usd", str(self.opts.budget)]
        if self.session_id:
            cmd += ["--resume", self.session_id]
        if self.opts.skip_permissions and not self.judge:
            cmd += ["--dangerously-skip-permissions"]
        else:
            cmd += ["--permission-mode", "acceptEdits", "--allowedTools",
                    *(["Read", "Glob", "Grep"] if self.judge else ALLOWED)]
        return cmd

    def send(self, prompt: str) -> str:
        self.turns += 1
        n = self.turns
        name = "judge" if self.judge else ""
        (self.logdir / f"{name}prompt-{n}.md").write_text(prompt, encoding="utf-8")
        started = time.monotonic()
        try:
            r = subprocess.run(self.command(), cwd=self.cwd, input=prompt, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=self.opts.timeout * 60)
            out, err = r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = f"timeout after {self.opts.timeout} min"
            self.errors.append(err)
        (self.logdir / f"{name}transcript-{n}.jsonl").write_text(out, encoding="utf-8")
        if err.strip():
            (self.logdir / f"{name}stderr-{n}.txt").write_text(err, encoding="utf-8")
        reply = ""
        for line in out.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            self.events.append(e)
            if e.get("type") == "result":
                reply = e.get("result") or ""
                self.session_id = e.get("session_id") or self.session_id
                self.cost += e.get("total_cost_usd") or 0
                self.denials += e.get("permission_denials") or []
                if e.get("is_error"):
                    self.errors.append(f"turn {n}: {e.get('subtype')}")
            elif e.get("type") == "system" and e.get("subtype") == "init":
                self.session_id = e.get("session_id") or self.session_id
        (self.logdir / f"{name}reply-{n}.md").write_text(reply, encoding="utf-8")
        print(f"{self.prefix}{'judge ' if self.judge else ''}turn {n} done in "
              f"{(time.monotonic() - started) / 60:.1f} min, cost so far ${self.cost:.2f}", flush=True)
        return reply

    def init_event(self) -> dict:
        return next((e for e in self.events if e.get("type") == "system" and e.get("subtype") == "init"), {})

    def skills_invoked(self) -> list[str]:
        out = []
        for e in self.events:
            for c in (e.get("message") or {}).get("content") or [] if e.get("type") == "assistant" else []:
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Skill":
                    out.append(str((c.get("input") or {}).get("skill")))
        return out

    def skill_dirs(self) -> list[str]:
        found = set()
        for e in self.events:
            if e.get("type") != "user":
                continue
            for s in walk_strings(e):
                for m in re.finditer(r"Base directory for this skill:\s*(\S+)", s):
                    found.add(m.group(1))
        return sorted(found)


# ---------- stage helpers ----------

def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def stage_done(stage: str, repo: Path) -> bool:
    """Whether the skill got as far as writing its result. Decides if another turn is needed."""
    if stage == "audit":
        return any((repo / ".oatrta" / "audit").glob("audit-*/audit.json"))
    if stage == "refactor":
        return git(repo, "diff", "--quiet", "--", "AGENTS.md").returncode == 1
    if stage == "create":
        return (repo / "AGENTS.md").is_file()
    return any((repo / ".oatrta" / "remediate").glob("run-*/comparison.json"))


def write_diff(repo: Path, path: Path) -> None:
    base = (repo / ".git" / "oatrta-sample-base").read_text(encoding="utf-8").strip()
    parts = [git(repo, "diff", base).stdout]
    for f in git(repo, "ls-files", "--others", "--exclude-standard").stdout.splitlines():
        text = (repo / f).read_text(encoding="utf-8", errors="replace")
        parts.append(f"=== new file: {f} ===\n{text}")
    path.write_text("\n".join(p for p in parts if p), encoding="utf-8")


def run_stage(stage: str, base: Path, opts) -> dict:
    sdir = base / stage
    sdir.mkdir(parents=True)
    repo = sdir / "repo"
    prefix = f"[{stage}] "
    res: dict = {"stage": stage, "dir": str(sdir), "errors": []}
    started = time.monotonic()

    args = [sys.executable, str(EVALS / "make_sample_repo.py"), str(repo)]
    if stage == "create":
        args.append("--without-agents-md")
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        res["errors"].append("make_sample_repo failed: " + r.stderr.strip())
        return res
    print(f"{prefix}sample at {repo}", flush=True)

    s = Session(repo, sdir, opts, prefix=prefix)
    s.send(FIRST_PROMPT.format(stage=stage))
    init = s.init_event()
    plugin = next((p for p in init.get("plugins") or [] if p.get("name") == "oatrta"), {})
    res["plugin"] = plugin
    if Path(plugin.get("path") or "").resolve() != ROOT:
        res["errors"].append(f"local plugin not loaded: {plugin or 'no oatrta plugin'}")
    # The skill usually stops after asking the maintainer; answer, then nudge once if still unfinished.
    for prompt in (MAINTAINER_ANSWERS, CONTINUE_PROMPT):
        if stage_done(stage, repo) or s.turns >= opts.max_turns or s.errors:
            break
        s.send(prompt)
    res.update(turns=s.turns, session_cost_usd=round(s.cost, 2), skills_invoked=s.skills_invoked(),
               skill_dirs=s.skill_dirs(), permission_denials=s.denials, stage_done=stage_done(stage, repo))
    res["errors"] += s.errors
    wrong = [d for d in res["skill_dirs"] if not Path(d).resolve().is_relative_to(ROOT)]
    if wrong:
        res["errors"].append(f"skill loaded from outside this checkout: {wrong}")
    if f"oatrta:agents-md-{stage}" not in res["skills_invoked"]:
        res["errors"].append(f"skill oatrta:agents-md-{stage} was never invoked")

    r = subprocess.run([sys.executable, str(EVALS / "check_sample.py"), str(repo), "--stage", stage],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    (sdir / "check.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
    m = re.search(r"(\d+) passed, (\d+) failed", r.stdout)
    res["check"] = {"passed": int(m.group(1)), "failed": int(m.group(2))} if m else {"error": r.stderr[-500:]}
    res["check_failures"] = [l.strip()[6:] for l in r.stdout.splitlines() if l.strip().startswith("FAIL")]
    write_diff(repo, sdir / "diff.patch")
    print(f"{prefix}check: {res['check']}", flush=True)

    res["judge"] = None
    if not opts.no_judge:
        j = Session(sdir, sdir, opts, judge=True, prefix=prefix)
        j.send(JUDGE_PROMPT.format(stage=stage, expected=(EVALS / "expected.md").as_posix()))
        jm = sdir / "judgment.md"
        text = jm.read_text(encoding="utf-8") if jm.is_file() else ""
        v = re.findall(r"^VERDICT:\s*(pass|fail)\s*$", text, flags=re.M | re.I)
        res["judge"] = v[-1].lower() if v else "missing"
        res["judge_cost_usd"] = round(j.cost, 2)
        res["errors"] += [f"judge: {e}" for e in j.errors]
        print(f"{prefix}judge: {res['judge']}", flush=True)

    res["minutes"] = round((time.monotonic() - started) / 60, 1)
    res["ok"] = (not res["errors"] and res.get("check", {}).get("failed") == 0
                 and res["judge"] in (None, "pass"))
    (sdir / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return res


def report(base: Path, results: list[dict]) -> str:
    lines = [f"# oatrta eval run {base.name}", "",
             "| Stage | OK | Checks | Judge | Turns | Cost | Min | Denied tools | Errors |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        c = r.get("check") or {}
        checks = f"{c.get('passed', '?')} ok / {c.get('failed', '?')} fail" if "passed" in c else "error"
        cost = (r.get("session_cost_usd") or 0) + (r.get("judge_cost_usd") or 0)
        lines.append(f"| {r['stage']} | {'yes' if r.get('ok') else 'NO'} | {checks} | {r.get('judge') or '-'} | "
                     f"{r.get('turns', 0)} | ${cost:.2f} | {r.get('minutes', '-')} | "
                     f"{len(r.get('permission_denials') or [])} | {'; '.join(r.get('errors') or []) or '-'} |")
    for r in results:
        if r.get("check_failures"):
            lines += ["", f"## {r['stage']}: failed checks", *[f"- {f}" for f in r["check_failures"]]]
        if r.get("permission_denials"):
            names = sorted({json.dumps(d.get("tool_input") or d, ensure_ascii=False)[:160] for d in r["permission_denials"]})
            lines += ["", f"## {r['stage']}: denied tool calls", *[f"- `{n}`" for n in names]]
    lines += ["", "Each stage folder holds the sample (`repo/`), prompts, replies, transcripts, `diff.patch`, "
              "`check.txt` and `judgment.md`."]
    text = "\n".join(lines) + "\n"
    (base / "report.md").write_text(text, encoding="utf-8")
    return text


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stages", default=",".join(STAGES), help="comma-separated, default all")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "oatrta-evals"),
                    help="parent folder for the run (default: <temp>/oatrta-evals)")
    ap.add_argument("--jobs", type=int, default=4, help="stages run in parallel (default 4)")
    ap.add_argument("--model", help="model for the skill and judge sessions (default: CLI default)")
    ap.add_argument("--budget", type=float, help="max USD per claude invocation (--max-budget-usd)")
    ap.add_argument("--timeout", type=int, default=45, help="minutes per claude invocation (default 45)")
    ap.add_argument("--max-turns", type=int, default=3, help="skill turns per stage, answers included (default 3)")
    ap.add_argument("--no-judge", action="store_true", help="skip the judge session")
    ap.add_argument("--skip-permissions", action="store_true",
                    help="run the skill session with --dangerously-skip-permissions instead of the allowlist")
    opts = ap.parse_args(argv)
    stages = [s.strip() for s in opts.stages.split(",") if s.strip()]
    bad = [s for s in stages if s not in STAGES]
    if bad:
        ap.error(f"unknown stage(s): {bad}; choose from {STAGES}")
    opts.claude = find_claude()

    base = Path(opts.out).resolve() / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base.mkdir(parents=True)
    print(f"eval run in {base}", flush=True)
    # Skill sessions get --add-dir on this checkout so they can run their scripts; they must not change it.
    checkout_before = git(ROOT, "status", "--porcelain", "--untracked-files=all").stdout
    with cf.ThreadPoolExecutor(max_workers=max(1, opts.jobs)) as pool:
        futures = {pool.submit(run_stage, s, base, opts): s for s in stages}
        done = {}
        for f in cf.as_completed(futures):
            s = futures[f]
            try:
                done[s] = f.result()
            except Exception as e:  # keep the other stages going
                done[s] = {"stage": s, "errors": [f"{type(e).__name__}: {e}"]}
    results = [done[s] for s in stages]
    if git(ROOT, "status", "--porcelain", "--untracked-files=all").stdout != checkout_before:
        for r in results:
            r["ok"] = False
            r.setdefault("errors", []).append(f"the oatrta checkout changed during the run; see git status in {ROOT}")
    (base / "summary.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("\n" + report(base, results))
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
