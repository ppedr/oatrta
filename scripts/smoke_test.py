#!/usr/bin/env python3
"""Smoke test for shared/*.py. Standard library only.

Runs the scanner and every run_tools.py subcommand as an agent would (as a CLI, through the
copies inside skills/), against throwaway fixture repositories. Run it on every OS you claim to
support; CI runs it on Linux and Windows.

    python scripts/smoke_test.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "skills" / "agents-md-remediate" / "scripts" / "scan_agents_md.py"
TOOLS = ROOT / "skills" / "agents-md-remediate" / "scripts" / "run_tools.py"
HAS_GIT = shutil.which("git") is not None

BAD_AGENTS_MD = """# AGENTS.md

## Overview
This project is a monorepo built with Go and React.

## Commands
Run the tests with `npm run test:unit`.
From `services/api`, run `make test-unit`.
From `services/api`, run `make integration`.

## Style
- Ask before changing files under `migrations/`.
- Write clean code and follow best practices.
- See `services/api/internal/handler.go`.
- token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"

## Security
"""


def run(script: Path, *args: str, cwd: Path | None = None) -> tuple[int, dict | str]:
    r = subprocess.run([sys.executable, "-I", str(script), *args], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8")
    try:
        return r.returncode, json.loads(r.stdout)
    except ValueError:
        return r.returncode, r.stdout + r.stderr


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "core.autocrlf=false", *args], check=True, capture_output=True)


def write(path: Path, text: str) -> None:
    """Write exact bytes: Path.write_text would turn \\n into \\r\\n on Windows."""
    path.write_bytes(text.encode("utf-8"))


def make_repo(base: Path, newline: str = "\n") -> Path:
    repo = base / "repo"
    (repo / "services" / "api").mkdir(parents=True)
    (repo / "web").mkdir()
    write(repo / "services" / "api" / "go.mod", "module x\n")
    write(repo / "services" / "api" / "Makefile", "test-unit:\n\tgo test ./...\n")
    write(repo / "web" / "package.json", '{"scripts": {"test": "jest"}}')
    write(repo / "main.go", "package main\n")
    (repo / "migrations").mkdir()
    write(repo / "migrations" / "001_init.sql", "select 1;\n")
    (repo / "AGENTS.md").write_bytes(BAD_AGENTS_MD.replace("\n", newline).encode("utf-8"))
    if HAS_GIT:
        git(repo, "init", "-q")
        # Repo-local, so the scripts' own git calls ignore a global core.autocrlf (true on Windows runners).
        git(repo, "config", "core.autocrlf", "false")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "init")
    return repo


def make_audit(repo: Path) -> dict:
    code, files = run(TOOLS, "hashes", str(repo))
    assert code == 0, files
    dims = {k: {"points": p, "max": m, "na": False}
            for k, p, m in (("A", 8, 20), ("B", 4, 15), ("C", 9, 15), ("D", 4, 15), ("E", 4, 10),
                            ("F", 6, 15), ("G", 5, 10))}
    return {
        "schema_version": 1, "repo_root": ".", "git_head": None, "created_at": "2026-11-14T00:00:00Z",
        "files": files,
        "score": {"total": 40, "grade": "D", "dimensions": dims},
        "blockers": [{"id": "B1", "key": "secret:AGENTS.md:github-token", "file": "AGENTS.md", "line": 15,
                      "summary": "GitHub token"}],
        "findings": [{"id": "F1", "key": "missing_cwd:AGENTS.md:npm-run-test-unit", "category": "missing_cwd",
                      "severity": "high", "dimension": "B", "file": "AGENTS.md", "line": 7,
                      "summary": "no directory", "evidence": "web/package.json:1", "fix": "From web, run npm test"},
                     {"id": "F2", "key": "instruction_drift:CLAUDE.md:agents-md", "category": "instruction_drift",
                      "severity": "medium", "dimension": "G", "file": "CLAUDE.md", "line": None,
                      "summary": "copies AGENTS.md", "evidence": "CLAUDE.md:3", "fix": "replace with @AGENTS.md"}],
        "dispositions": [
            {"file": "AGENTS.md", "start": 12, "end": 12, "verdict": "KEEP", "unverified": True},
            {"file": "AGENTS.md", "start": 13, "end": 13, "verdict": "CUT"},
        ],
        "gaps": [], "questions": ["Which actions need approval?"],
    }


class Scanner(unittest.TestCase):
    def check_bad_repo(self, newline: str) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = make_repo(Path(tmp).resolve(), newline)
            code, r = run(SCAN, str(repo))
            self.assertEqual(code, 0, r)
            f = r["agents_md_files"][0]
            self.assertEqual(f["path"], "AGENTS.md")
            self.assertEqual(r["blocker_hints"]["B1_secret"], 1)
            unresolved = {c["command"] for c in f["unresolved_commands"]}
            self.assertIn("npm run test:unit", unresolved)
            self.assertIn("make integration", unresolved)
            self.assertNotIn("make test-unit", unresolved, "working directory from prose was ignored")
            self.assertEqual([m["path"] for m in f["missing_paths"]], ["services/api/internal/handler.go"])
            self.assertTrue(f["generic_phrases"])
            self.assertTrue(f["overview_prose"])
            self.assertEqual([h["heading"] for h in f["empty_headings"]], ["Security"])
            self.assertIn("services/api", r["nested_candidates"])

    def test_lf(self) -> None:
        self.check_bad_repo("\n")

    def test_crlf(self) -> None:
        self.check_bad_repo("\r\n")

    def test_other_instruction_files(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = make_repo(Path(tmp).resolve())
            copied = "- Ask before changing files under `migrations/`.\n- Write clean code and follow best practices.\n"
            write(repo / "CLAUDE.md", "# CLAUDE.md\n\n" + copied)
            write(repo / "GEMINI.md", "AGENTS.md")  # symlink checked out as text
            write(repo / "services" / "api" / "CLAUDE.md", "@../../AGENTS.md\n\n- Use plan mode.\n")
            (repo / "web" / "sub").mkdir()
            write(repo / "web" / "sub" / "CLAUDE.md", "- Use pnpm here.\n")
            (repo / ".github" / "agents").mkdir(parents=True)
            write(repo / ".github" / "agents" / "test-agent.md", "---\nname: test\n---\n" + copied)
            code, r = run(SCAN, str(repo))
            self.assertEqual(code, 0, r)
            others = {o["path"]: o for o in r["other_instruction_files"]}
            self.assertEqual(sorted(others), [".github/agents/", "CLAUDE.md", "GEMINI.md",
                                              "services/api/CLAUDE.md", "web/sub/CLAUDE.md"])
            self.assertEqual(others["CLAUDE.md"]["lines_copied_from_agents_md"], 2)
            self.assertTrue(others["CLAUDE.md"]["drift_risk"])
            self.assertTrue(others["GEMINI.md"]["symlink_checked_out_as_text"])
            self.assertFalse(others["GEMINI.md"]["drift_risk"])
            self.assertEqual(others["services/api/CLAUDE.md"]["agents_md"], "AGENTS.md")
            self.assertFalse(others["services/api/CLAUDE.md"]["drift_risk"], "an import is a bridge")
            self.assertTrue(others["web/sub/CLAUDE.md"]["drift_risk"], "never mentions AGENTS.md")
            self.assertEqual(others[".github/agents/"]["files"], ["test-agent.md"])
            self.assertEqual(others[".github/agents/"]["lines_copied_from_agents_md"], 2)
            self.assertEqual(sorted(r["drift_candidates"]),
                             [".github/agents/", "CLAUDE.md", "GEMINI.md", "web/sub/CLAUDE.md"])
            code, md = run(SCAN, str(repo), "--format", "md")
            self.assertIn("2 line(s) copied from AGENTS.md", md)
            self.assertIn("symlink checked out", md)

            code, files = run(TOOLS, "hashes", str(repo))
            self.assertEqual(code, 0, files)
            self.assertIn("services/api/CLAUDE.md", [f["path"] for f in files])

    def test_markdown_output(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = make_repo(Path(tmp).resolve())
            code, r = run(SCAN, str(repo), "--format", "md")
            self.assertEqual(code, 0)
            self.assertIn("Possible secrets", r)
            self.assertNotIn("ghp_", r, "scanner must not echo secret values")


class Validate(unittest.TestCase):
    def test_valid_and_invalid(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = make_repo(Path(tmp).resolve())
            audit = make_audit(repo)
            path = Path(tmp).resolve() / "audit.json"
            path.write_text(json.dumps(audit), encoding="utf-8")
            code, r = run(TOOLS, "validate", str(path))
            self.assertEqual(code, 0, r)

            audit["score"].update(total=90, grade="A")
            audit["findings"][0]["key"] = "AGENTS.md:7"
            audit["dispositions"].append({"file": "README.md", "start": 1, "end": 1, "verdict": "DROP"})
            path.write_text(json.dumps(audit), encoding="utf-8")
            code, r = run(TOOLS, "validate", str(path))
            self.assertEqual(code, 1)
            text = " ".join(r["errors"])
            for expected in ("add up to 40", "blockers cap", "key must be", "verdict invalid", "not in files"):
                self.assertIn(expected, text)


@unittest.skipUnless(HAS_GIT, "git not installed")
class RemediationRun(unittest.TestCase):
    def test_full_cycle(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = make_repo(Path(tmp).resolve())
            original = (repo / "AGENTS.md").read_bytes()

            code, r = run(TOOLS, "latest-audit", str(repo))
            self.assertEqual(code, 1)

            code, d = run(TOOLS, "audit-dir", str(repo))
            self.assertEqual(code, 0, d)
            audit_json = Path(d["audit_json"]).resolve()
            self.assertEqual(audit_json.parent.parent, (repo / ".oatrta" / "audit").resolve())
            audit_json.write_text(json.dumps(make_audit(repo)), encoding="utf-8")
            exclude = (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
            self.assertIn("/.oatrta/", exclude)

            code, r = run(TOOLS, "latest-audit", str(repo))
            self.assertEqual((code, Path(r["audit_json"]).resolve()), (0, audit_json.resolve()))
            code, r = run(TOOLS, "stale", str(audit_json), str(repo))
            self.assertEqual(code, 0, r)

            code, init = run(TOOLS, "init", str(repo))
            self.assertEqual(code, 0, init)
            run_dir = Path(init["run_dir"]).resolve()
            self.assertEqual(run_dir.parent, (repo / ".oatrta" / "remediate").resolve())
            self.assertTrue((run_dir / "before" / "AGENTS.md").is_file())

            # A misbehaving fixer: drops the KEEP line, adds a nested file, edits code.
            write(repo / "AGENTS.md", "# AGENTS.md\n\n- From `web`, run `npm test`.\n")
            write(repo / "services" / "api" / "AGENTS.md", "# api\n\n- Go only.\n")
            write(repo / "main.go", "package main\n// edit\n")

            code, r = run(TOOLS, "stale", str(audit_json), str(repo))
            self.assertEqual(code, 1)
            self.assertEqual(r["added"], ["services/api/AGENTS.md"])

            code, r = run(TOOLS, "scope", str(repo), str(run_dir))
            self.assertEqual(code, 1, r)
            self.assertEqual(r["violations"], ["main.go"])
            self.assertEqual(sorted(r["allowed"]), ["AGENTS.md", "services/api/AGENTS.md"])

            code, r = run(TOOLS, "diff", str(repo), str(run_dir))
            self.assertEqual(code, 0, r)
            self.assertEqual((r["added"], r["modified"]), (["services/api/AGENTS.md"], ["AGENTS.md"]))
            patch = (run_dir / "evidence" / "diff.patch").read_text(encoding="utf-8")
            self.assertIn("-- Ask before changing files under `migrations/`.", patch)

            code, r = run(TOOLS, "keep-check", str(audit_json), str(repo), str(run_dir))
            self.assertEqual(code, 1, r)
            self.assertEqual([m["line"] for m in r["missing"]], [12])

            (run_dir / "audit-2.json").write_text(audit_json.read_text(encoding="utf-8"), encoding="utf-8")
            (run_dir / "comparison.md").write_text("# comparison\n", encoding="utf-8")
            code, r = run(TOOLS, "publish", str(repo), str(run_dir))
            self.assertEqual(code, 0, r)
            self.assertIn("remediation.md", r["files"])
            code, latest = run(TOOLS, "latest-audit", str(repo))
            self.assertEqual(latest["history"], 2)

            code, r = run(TOOLS, "restore", str(repo), str(run_dir))
            self.assertEqual(code, 0, r)
            self.assertEqual((repo / "AGENTS.md").read_bytes(), original)
            self.assertFalse((repo / "services" / "api" / "AGENTS.md").exists())

            status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
                                    capture_output=True, text=True, check=True).stdout
            self.assertNotIn(".oatrta", status, ".oatrta/ must stay out of git")
            self.assertEqual(status.strip(), "M main.go")

    def test_legacy_exclude_is_widened(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = make_repo(Path(tmp).resolve())
            excl = repo / ".git" / "info" / "exclude"
            excl.write_text("/.oatrta/remediate/\n", encoding="utf-8")
            run(TOOLS, "audit-dir", str(repo))
            lines = excl.read_text(encoding="utf-8").splitlines()
            self.assertIn("/.oatrta/", lines)
            self.assertNotIn("/.oatrta/remediate/", lines)


@unittest.skipUnless(HAS_GIT, "git not installed")
class Evals(unittest.TestCase):
    """Keeps evals/ honest: the sample still contains its planted defects and the checker still bites."""

    def test_sample_repo(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            sample = Path(tmp).resolve() / "sample"
            r = subprocess.run([sys.executable, str(ROOT / "evals" / "make_sample_repo.py"), str(sample)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            code, scan = run(SCAN, str(sample))
            self.assertEqual(scan["blocker_hints"], {"B1_secret": 1, "B2_stale_command": 1, "B3_stale_path": 1})
            self.assertIn("services/api", scan["nested_candidates"])
            self.assertEqual(scan["drift_candidates"], ["CLAUDE.md"])
            claude = next(o for o in scan["other_instruction_files"] if o["path"] == "CLAUDE.md")
            self.assertEqual(claude["lines_copied_from_agents_md"], 3)
            r = subprocess.run([sys.executable, str(ROOT / "evals" / "check_sample.py"), str(sample),
                                "--stage", "refactor"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, "an untouched sample must fail the refactor checks")
            self.assertIn("FAIL  D6 token removed", r.stdout)


@unittest.skipUnless(HAS_GIT, "git not installed")
class EvalRunner(unittest.TestCase):
    """evals/run_eval.py needs a model to run; this covers the parts that do not."""

    def test_cli_and_stage_detection(self) -> None:
        r = subprocess.run([sys.executable, str(ROOT / "evals" / "run_eval.py"), "--stages", "nope"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown stage", r.stderr)
        sys.path.insert(0, str(ROOT / "evals"))
        import run_eval  # noqa: E402
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            sample = Path(tmp).resolve() / "sample"
            subprocess.run([sys.executable, str(ROOT / "evals" / "make_sample_repo.py"), str(sample)],
                           check=True, capture_output=True)
            for stage in run_eval.STAGES:
                self.assertEqual(run_eval.stage_done(stage, sample), stage == "create", stage)
            write(sample / "AGENTS.md", "# AGENTS.md\n")
            self.assertTrue(run_eval.stage_done("refactor", sample))
            write(sample / "web" / "NEW.md", "new\n")
            run_eval.write_diff(sample, Path(tmp) / "diff.patch")
            patch = (Path(tmp) / "diff.patch").read_text(encoding="utf-8")
            self.assertIn("-## Overview", patch)
            self.assertIn("=== new file: web/NEW.md ===", patch)


class Repo(unittest.TestCase):
    def test_sync_check(self) -> None:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_shared.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_no_bytecode_written(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = make_repo(Path(tmp).resolve())
            run(TOOLS, "hashes", str(repo))
            self.assertFalse((TOOLS.parent / "__pycache__").exists() and
                             any((TOOLS.parent / "__pycache__").glob("run_tools*")),
                             "run_tools.py must not write __pycache__ next to the skill")


if __name__ == "__main__":
    unittest.main(verbosity=2)
