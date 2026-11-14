#!/usr/bin/env python3
"""Check the deterministic part of a skill's result on the sample repository.

    python evals/check_sample.py <sample-dir> --stage audit|refactor|create|remediate

Run it after running a skill on a repo made by evals/make_sample_repo.py. It checks only what
code can check (files, paths, git state, audit JSON). Whether the findings, rewrites and
questions are right is judged by reading the output against evals/expected.md.
Standard library only. Exit 0 when every check passes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))
from make_sample_repo import CLAUDE_MD, FAKE_TOKEN, KEEP_LINE  # noqa: E402

TOOLS = ROOT / "skills" / "agents-md-remediate" / "scripts" / "run_tools.py"
STAGES = ("audit", "refactor", "create", "remediate")


class Checker:
    def __init__(self, repo: Path):
        self.repo = repo
        self.failures: list[str] = []
        self.passed = 0

    def check(self, ok: bool, what: str) -> bool:
        if ok:
            self.passed += 1
            print(f"  ok    {what}")
        else:
            self.failures.append(what)
            print(f"  FAIL  {what}")
        return ok

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True,
                              check=True).stdout

    def tools(self, *args: str) -> tuple[int, dict]:
        r = subprocess.run([sys.executable, "-I", str(TOOLS), *args], capture_output=True, text=True,
                           encoding="utf-8")
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            return r.returncode, {"raw": r.stdout + r.stderr}

    def agents_files(self) -> list[Path]:
        return [p for p in self.repo.rglob("AGENTS.md") if ".oatrta" not in p.parts and ".git" not in p.parts]

    def oatrta_text(self) -> str:
        base = self.repo / ".oatrta"
        if not base.is_dir():
            return ""
        # A remediate run's before/ is a byte-for-byte snapshot for restore; it holds the token by design.
        return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in base.rglob("*")
                         if p.is_file() and p.suffix in (".json", ".md") and "before" not in p.relative_to(base).parts)

    # ---- shared checks ----

    def common(self) -> None:
        base_file = self.repo / ".git" / "oatrta-sample-base"
        if not self.check(base_file.is_file(), "repo was made by evals/make_sample_repo.py"):
            return
        base = base_file.read_text(encoding="utf-8").strip()
        self.check(self.git("rev-parse", "HEAD").strip() == base, "nothing was committed")
        self.check(".oatrta" not in self.git("status", "--porcelain", "--untracked-files=all"),
                   ".oatrta/ is kept out of git")
        self.check(FAKE_TOKEN not in self.oatrta_text(), "no secret value in any .oatrta/ file")
        claude = self.repo / "CLAUDE.md"
        self.check(claude.is_file() and claude.read_bytes() == CLAUDE_MD.encode("utf-8"),
                   "D13 CLAUDE.md left byte for byte (bridge is only proposed)")

    def latest_audit(self) -> dict | None:
        code, r = self.tools("latest-audit", str(self.repo))
        if not self.check(code == 0 and r.get("audit_json"), "an audit exists under .oatrta/audit/"):
            return None
        code, v = self.tools("validate", r["audit_json"])
        self.check(code == 0, f"latest audit passes validate {v.get('errors', '')}")
        return json.loads(Path(r["audit_json"]).read_text(encoding="utf-8"))

    def only_agents_md_changed(self) -> None:
        changed = [l[3:] for l in self.git("status", "--porcelain", "--untracked-files=all").splitlines()
                   if not l[3:].startswith(".oatrta/")]
        bad = [c for c in changed if Path(c).name != "AGENTS.md"]
        self.check(not bad, f"only AGENTS.md files changed {bad or ''}")

    def fixed_files(self) -> None:
        texts = {p: p.read_text(encoding="utf-8") for p in self.agents_files()}
        joined = "\n".join(texts.values())
        self.check(FAKE_TOKEN not in joined, "D6 token removed from every AGENTS.md")
        self.check(KEEP_LINE in joined, "D7 maintainer line kept verbatim")
        self.check("npm run test:unit" not in joined, "D3 stale command gone")
        self.check("scripts/release.sh" not in joined, "D8 stale path gone")
        self.check("├──" not in joined, "D2 directory tree gone")
        self.check("This project is a monorepo" not in joined, "D1 overview prose gone")
        self.check("clean code" not in joined.lower(), "D5 generic advice gone")
        self.check("Go 1.21" not in joined, "D14 Go version contradicting go.mod gone")
        root = texts.get(self.repo / "AGENTS.md", "")
        self.check("## Security" not in root or root.split("## Security", 1)[1].strip() != "",
                   "D10 empty heading gone")

    # ---- stages ----

    def audit(self) -> None:
        a = self.latest_audit()
        if not a:
            return
        ids = {b["id"] for b in a["blockers"]}
        self.check({"B1", "B2", "B3"} <= ids, f"blockers B1, B2, B3 reported (got {sorted(ids)})")
        self.check(a["score"]["grade"] in ("C", "D"), f"grade capped at C or below (got {a['score']['grade']})")
        cats = {f["category"] for f in a["findings"]} | {b["key"].split(":")[0] for b in a["blockers"]}
        for cat in ("secret", "stale_command", "stale_path"):
            self.check(cat in cats, f"a {cat} finding or blocker")
        self.check(any(f["category"] == "instruction_drift" and f["file"] == "CLAUDE.md" for f in a["findings"]),
                   "D13 instruction_drift finding on CLAUDE.md")
        keep_line_no = (self.repo / "AGENTS.md").read_text(encoding="utf-8").splitlines().index(KEEP_LINE) + 1
        keep = [d for d in a["dispositions"] if d["file"] == "AGENTS.md" and d["start"] <= keep_line_no <= d["end"]]
        self.check(bool(keep) and keep[0]["verdict"] == "KEEP", "D7 classified KEEP")
        self.check(bool(keep) and keep[0].get("unverified") is True, "D7 marked unverified")
        self.check(bool(a["questions"]), "maintainer questions recorded")
        self.check(not [l for l in self.git("status", "--porcelain").splitlines()], "audit changed no file")

    def refactor(self) -> None:
        self.only_agents_md_changed()
        self.fixed_files()

    def create(self) -> None:
        root = self.repo / "AGENTS.md"
        if not self.check(root.is_file(), "root AGENTS.md created"):
            return
        text = root.read_text(encoding="utf-8")
        self.only_agents_md_changed()
        self.check("├──" not in text and "This project is" not in text, "no tree, no overview")
        self.check("clean code" not in text.lower() and "best practices" not in text.lower(), "no generic advice")
        self.check("services/api" in text or (self.repo / "services/api/AGENTS.md").is_file(),
                   "Go service commands documented with their directory")
        self.check("gen/" in text or "generate" in text, "G1 generated gen/ boundary documented")
        self.check("1.21" not in text and "1.22" not in text, "no Go version that go.mod already pins")

    def remediate(self) -> None:
        self.only_agents_md_changed()
        self.fixed_files()
        runs = sorted((self.repo / ".oatrta" / "remediate").glob("run-*"))
        if not self.check(bool(runs), "a run folder exists under .oatrta/remediate/"):
            return
        run = runs[-1]
        for name in ("baseline.json", "audit-1.json", "answers.md", "fix-report.md", "audit-2.json", "comparison.json"):
            self.check((run / name).is_file(), f"run has {name}")
        report = (run / "fix-report.md").read_text(encoding="utf-8") if (run / "fix-report.md").is_file() else ""
        self.check(report.rstrip().splitlines()[-1:] == ["STATUS: done"], "fix-report ends with STATUS: done")
        if (run / "comparison.json").is_file():
            c = json.loads((run / "comparison.json").read_text(encoding="utf-8"))
            self.check(c.get("verdict") in ("improved", "mixed"), f"verdict improved or mixed (got {c.get('verdict')})")
            self.check(not c.get("scope", {}).get("violations"), "no scope violations")
            self.check(not c.get("preservation", {}).get("missing"), "no KEEP line lost")
        code, r = self.tools("keep-check", str(run / "audit-1.json"), str(self.repo), str(run))
        self.check(code == 0, "keep-check passes on the final files")
        latest = self.latest_audit()
        if latest:
            entry = Path(self.tools("latest-audit", str(self.repo))[1]["audit_json"]).parent
            self.check((entry / "remediation.md").is_file(), "newest audit entry has remediation.md")


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "--stage" or argv[2] not in STAGES:
        print(__doc__, file=sys.stderr)
        return 2
    repo = Path(argv[0]).resolve()
    c = Checker(repo)
    print(f"{argv[2]} on {repo}")
    c.common()
    getattr(c, argv[2])()
    print(f"\n{c.passed} passed, {len(c.failures)} failed")
    return 1 if c.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
