#!/usr/bin/env python3
"""Deterministic helpers for audit files and remediation runs. Standard library only.

Subcommands:
    hashes     <repo>                     instruction files with line count and sha256 (JSON)
    validate   <audit.json>               structural and arithmetic check of an audit file
    stale      <audit.json> <repo>        exit 1 if instruction files changed since the audit
    init       <repo>                     create .oatrta/remediate/run-<timestamp>/, snapshot, write baseline
    scope      <repo> <run_dir>           files changed since the baseline; non-AGENTS.md changes are violations
    diff       <repo> <run_dir>           unified diff of instruction files, snapshot vs now
    keep-check <audit.json> <repo> <run_dir>  KEEP lines from the audit that no longer exist anywhere
    restore    <repo> <run_dir>           put snapshot back and remove AGENTS.md files created by the run
    audit-dir  <repo>                     create .oatrta/audit/audit-<timestamp>/ and print it
    latest-audit <repo>                   newest .oatrta/audit/audit-*/audit.json (exit 1 if none)
    publish    <repo> <run_dir>           record a run's re-audit and comparison as a new .oatrta/audit/ entry

Exit codes: 0 ok, 1 check failed, 2 usage or input error.
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ next to installed skills
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_agents_md import OTHER_INSTRUCTION_FILES, rel, walk  # noqa: E402

# Everything oatrta writes in a target repo lives under OATRTA_ROOT/<skill>/, and the whole
# OATRTA_ROOT is kept out of git locally through .git/info/exclude (see ensure_excluded).
OATRTA_ROOT = ".oatrta"
AUDIT_ROOT = f"{OATRTA_ROOT}/audit"          # audit history
REMEDIATE_ROOT = f"{OATRTA_ROOT}/remediate"  # run evidence
AUDIT_PREFIX = "audit-"
RUN_PREFIX = "run-"
DIMENSION_MAX = {"A": 20, "B": 15, "C": 15, "D": 15, "E": 10, "F": 15, "G": 10}
VERDICTS = {"KEEP", "SHARPEN", "FIX", "MOVE:nested", "MOVE:root", "MOVE:link", "MOVE:tooling", "CUT", "REDACT"}
CATEGORIES = {
    "secret", "stale_command", "stale_path", "contradiction", "generic_advice", "discoverable_fact",
    "directory_listing", "overview_prose", "duplicated_doc", "empty_heading", "vague_rule", "missing_cwd",
    "undocumented_tooling", "missing_boundary", "missing_validation", "misplaced_scope",
    "tooling_enforceable", "other",
}


# ---------- helpers ----------

def out(obj) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def instruction_files(root: Path) -> list[str]:
    found = set()
    for d, _, filenames in walk(root):
        if OATRTA_ROOT in d.relative_to(root).parts:
            continue
        if "AGENTS.md" in filenames:
            found.add(rel(root, d / "AGENTS.md"))
    for name in OTHER_INSTRUCTION_FILES:
        if (root / name).is_file():
            found.add(name)
    return sorted(found)


def file_entry(root: Path, path: str) -> dict:
    p = root / path
    return {"path": path, "lines": len(p.read_text(encoding="utf-8", errors="replace").splitlines()), "sha256": sha256(p)}


def git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        return r.stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def git_dirty(root: Path) -> dict[str, str | None] | None:
    """Paths that differ from HEAD (modified, added, untracked, deleted) -> sha256 or None if absent."""
    raw = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if raw is None:
        return None
    dirty: dict[str, str | None] = {}
    entries = raw.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        status, path = e[:2], e[3:]
        if status[0] in "RC":  # rename/copy: next entry is the source path
            src = entries[i] if i < len(entries) else ""
            i += 1
            if src:
                dirty[src] = None
        if path.startswith(OATRTA_ROOT + "/"):
            continue
        p = root / path
        dirty[path] = sha256(p) if p.is_file() else None
    return dirty


def load_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"cannot read {path}: {e}", file=sys.stderr)
        sys.exit(2)


def norm(line: str) -> str:
    return " ".join(line.strip().split())


def expected_grade(total: int, has_blockers: bool) -> str:
    g = "A" if total >= 85 else "B" if total >= 70 else "C" if total >= 50 else "D"
    return "C" if has_blockers and g in ("A", "B") else g


# ---------- subcommands ----------

def cmd_hashes(root: Path) -> int:
    out([file_entry(root, p) for p in instruction_files(root)])
    return 0


def cmd_validate(audit_path: str) -> int:
    a = load_json(audit_path)
    errors: list[str] = []

    def need(obj, key, typ, where):
        if key not in obj:
            errors.append(f"{where}: missing '{key}'")
            return None
        if typ and not isinstance(obj[key], typ):
            errors.append(f"{where}.{key}: expected {typ.__name__ if isinstance(typ, type) else typ}")
            return None
        return obj[key]

    if a.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    for k, t in (("repo_root", str), ("created_at", str), ("files", list), ("score", dict), ("blockers", list),
                 ("findings", list), ("dispositions", list), ("gaps", list), ("questions", list)):
        need(a, k, t, "root")

    for i, f in enumerate(a.get("files") or []):
        for k, t in (("path", str), ("lines", int), ("sha256", str)):
            need(f, k, t, f"files[{i}]")

    score = a.get("score") or {}
    dims = score.get("dimensions") or {}
    earned = possible = 0.0
    for d, mx in DIMENSION_MAX.items():
        dim = dims.get(d)
        if not isinstance(dim, dict):
            errors.append(f"score.dimensions.{d}: missing")
            continue
        if dim.get("max") != mx:
            errors.append(f"score.dimensions.{d}.max must be {mx}")
        if dim.get("na"):
            if not dim.get("reason"):
                errors.append(f"score.dimensions.{d}: N/A needs a reason")
            continue
        pts = dim.get("points")
        if not isinstance(pts, (int, float)) or not 0 <= pts <= mx:
            errors.append(f"score.dimensions.{d}.points must be between 0 and {mx}")
            continue
        earned += pts
        possible += mx
    total = score.get("total")
    if possible and isinstance(total, int):
        computed = round(earned / possible * 100)
        if abs(computed - total) > 1:
            errors.append(f"score.total is {total} but dimensions add up to {computed}")
    blockers = a.get("blockers") or []
    if isinstance(total, int) and score.get("grade") != expected_grade(total, bool(blockers)):
        errors.append(f"score.grade is {score.get('grade')}, expected {expected_grade(total, bool(blockers))}"
                      + (" (blockers cap the grade at C)" if blockers else ""))

    for i, b in enumerate(blockers):
        if b.get("id") not in ("B1", "B2", "B3", "B4"):
            errors.append(f"blockers[{i}].id invalid")
        need(b, "key", str, f"blockers[{i}]")
    ids = set()
    for i, f in enumerate(a.get("findings") or []):
        for k in ("id", "key", "category", "severity", "dimension", "file", "summary", "evidence", "fix"):
            need(f, k, None, f"findings[{i}]")
        if f.get("id") in ids:
            errors.append(f"findings[{i}].id duplicated: {f.get('id')}")
        ids.add(f.get("id"))
        if f.get("category") not in CATEGORIES:
            errors.append(f"findings[{i}].category invalid: {f.get('category')}")
        if f.get("severity") not in ("high", "medium", "low"):
            errors.append(f"findings[{i}].severity invalid")
        key = f.get("key") or ""
        if key.count(":") < 2 or not key.startswith(str(f.get("category")) + ":"):
            errors.append(f"findings[{i}].key must be '<category>:<file>:<subject>'")
    audited = {f.get("path") for f in a.get("files") or []}
    for i, d in enumerate(a.get("dispositions") or []):
        if d.get("verdict") not in VERDICTS:
            errors.append(f"dispositions[{i}].verdict invalid: {d.get('verdict')}")
        s, e = d.get("start"), d.get("end")
        if not (isinstance(s, int) and isinstance(e, int) and 1 <= s <= e):
            errors.append(f"dispositions[{i}]: need 1 <= start <= end")
        if d.get("file") not in audited:
            errors.append(f"dispositions[{i}].file not in files[]: {d.get('file')}")
    for i, g in enumerate(a.get("gaps") or []):
        for k in ("key", "summary", "evidence", "target_file"):
            need(g, k, str, f"gaps[{i}]")

    out({"valid": not errors, "errors": errors})
    return 0 if not errors else 1


def cmd_stale(audit_path: str, root: Path) -> int:
    a = load_json(audit_path)
    then = {f["path"]: f["sha256"] for f in a.get("files", [])}
    now = {p: sha256(root / p) for p in instruction_files(root)}
    changed = sorted(p for p in then if p in now and now[p] != then[p])
    removed = sorted(p for p in then if p not in now)
    added = sorted(p for p in now if p not in then)
    stale = bool(changed or removed or added)
    out({"stale": stale, "changed": changed, "removed": removed, "added": added})
    return 1 if stale else 0


def ensure_excluded(root: Path) -> str | None:
    """Keep all of .oatrta/ out of git, locally, through .git/info/exclude. Returns a note if changed."""
    git_dir = (git(root, "rev-parse", "--git-dir") or "").strip()
    if not git_dir:
        return None
    excl = Path(git_dir) / "info" / "exclude" if Path(git_dir).is_absolute() else root / git_dir / "info" / "exclude"
    lines = (excl.read_text(encoding="utf-8") if excl.is_file() else "").splitlines()
    wanted = f"/{OATRTA_ROOT}/"
    narrower = [l for l in lines if l.startswith(wanted) and l != wanted]  # e.g. /.oatrta/remediate/
    if wanted in lines and not narrower:
        return None
    lines = [l for l in lines if l not in narrower]
    if wanted not in lines:
        lines.append(wanted)
    excl.parent.mkdir(parents=True, exist_ok=True)
    excl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"{rel(root, excl)} ignores {wanted}"


def cmd_init(root: Path) -> int:
    run_id = RUN_PREFIX + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / REMEDIATE_ROOT / run_id
    (run_dir / "before").mkdir(parents=True, exist_ok=False)
    (run_dir / "evidence").mkdir()
    files = instruction_files(root)
    for p in files:
        dst = run_dir / "before" / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / p, dst)
    exclude_note = ensure_excluded(root)  # before the baseline, so later checks see the same files
    head = (git(root, "rev-parse", "HEAD") or "").strip() or None
    dirty = git_dirty(root)
    baseline = {
        "run_id": run_id, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "repo_root": str(root), "git": dirty is not None, "git_head": head,
        "instruction_files": [file_entry(root, p) for p in files], "dirty": dirty or {},
    }
    (run_dir / "baseline.json").write_text(json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8")
    dirty_instr = sorted(p for p in (dirty or {}) if p in files)
    out({"run_dir": str(run_dir), "snapshot": files, "git": dirty is not None,
         "uncommitted_instruction_files": dirty_instr, "note": exclude_note})
    return 0


def cmd_scope(root: Path, run_dir: Path) -> int:
    base = load_json(str(run_dir / "baseline.json"))
    if not base.get("git"):
        result = {"checked": False, "reason": "not a git repository; scope check needs git", "violations": []}
        (run_dir / "evidence" / "scope.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        out(result)
        return 0
    before = base.get("dirty", {})
    now = git_dirty(root) or {}
    changed = set()
    for p, h in now.items():
        if p not in before or before[p] != h:
            changed.add(p)
    for p in before:
        if p not in now:
            changed.add(p)  # was dirty, now back to HEAD
    changed = sorted(c for c in changed if not c.startswith(OATRTA_ROOT + "/"))
    allowed = [c for c in changed if Path(c).name == "AGENTS.md"]
    violations = [c for c in changed if Path(c).name != "AGENTS.md"]
    result = {"checked": True, "changed": changed, "allowed": allowed, "violations": violations}
    (run_dir / "evidence" / "scope.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    out(result)
    return 1 if violations else 0


def cmd_diff(root: Path, run_dir: Path) -> int:
    before_dir = run_dir / "before"
    old = {rel(before_dir, p): p for p in before_dir.rglob("*") if p.is_file()}
    new = {p: root / p for p in instruction_files(root)}
    chunks, modified = [], []
    for path in sorted(set(old) | set(new)):
        a = old[path].read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if path in old else []
        b = new[path].read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if path in new else []
        if a != b:
            if path in old and path in new:
                modified.append(path)
            chunks.append("".join(difflib.unified_diff(
                a, b, fromfile=f"a/{path}" if path in old else "/dev/null",
                tofile=f"b/{path}" if path in new else "/dev/null")))
    patch = "\n".join(chunks)
    (run_dir / "evidence" / "diff.patch").write_text(patch, encoding="utf-8")
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    out({"patch": str(run_dir / "evidence" / "diff.patch"), "added": added, "removed": removed,
         "modified": modified, "changed": bool(chunks)})
    return 0


def cmd_keep_check(audit_path: str, root: Path, run_dir: Path) -> int:
    a = load_json(audit_path)
    corpus = set()
    for p in instruction_files(root):
        corpus.update(n for n in (norm(l) for l in (root / p).read_text(encoding="utf-8", errors="replace").splitlines()) if n)
    missing, checked = [], 0
    for d in a.get("dispositions", []):
        if d.get("verdict") != "KEEP":
            continue
        src = run_dir / "before" / d["file"]
        if not src.is_file():
            missing.append({"file": d["file"], "start": d["start"], "end": d["end"], "reason": "file not in snapshot"})
            continue
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        for n in range(d["start"], min(d["end"], len(lines)) + 1):
            text = norm(lines[n - 1])
            if not text or set(text) <= set("`~-#*|: "):
                continue
            checked += 1
            if text not in corpus:
                missing.append({"file": d["file"], "line": n, "text": lines[n - 1].strip()[:200],
                                "unverified": bool(d.get("unverified"))})
    result = {"keep_lines_checked": checked, "missing": missing}
    (run_dir / "evidence" / "keep-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    out(result)
    return 1 if missing else 0


def cmd_restore(root: Path, run_dir: Path) -> int:
    before_dir = run_dir / "before"
    old = {rel(before_dir, p) for p in before_dir.rglob("*") if p.is_file()}
    restored, removed, failed = [], [], []
    for p in sorted(old):
        dst = root / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(before_dir / p, dst)
        restored.append(p)
    for p in instruction_files(root):
        if p not in old and Path(p).name == "AGENTS.md":
            try:
                (root / p).unlink()
                removed.append(p)
            except OSError as e:
                failed.append({"path": p, "error": str(e)})
    out({"restored": restored, "removed": removed, "failed": failed})
    return 1 if failed else 0


def new_audit_dir(root: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = root / AUDIT_ROOT
    d, n = base / f"{AUDIT_PREFIX}{stamp}", 2
    while d.exists():
        d, n = base / f"{AUDIT_PREFIX}{stamp}-{n}", n + 1
    d.mkdir(parents=True)
    return d


def cmd_audit_dir(root: Path) -> int:
    note = ensure_excluded(root)
    d = new_audit_dir(root)
    out({"audit_dir": str(d), "audit_json": str(d / "audit.json"), "audit_md": str(d / "audit.md"),
         "note": note})
    return 0


def cmd_latest_audit(root: Path) -> int:
    base = root / AUDIT_ROOT
    entries = sorted((p for p in base.iterdir()
                      if p.name.startswith(AUDIT_PREFIX) and (p / "audit.json").is_file()),
                     key=lambda p: p.name) if base.is_dir() else []
    if not entries:
        out({"audit_json": None, "history": 0})
        return 1
    last = entries[-1]
    md = last / "audit.md"
    out({"audit_json": str(last / "audit.json"), "audit_md": str(md) if md.is_file() else None,
         "history": len(entries)})
    return 0


def cmd_publish(root: Path, run_dir: Path) -> int:
    src = {"audit-2.json": "audit.json", "audit-2.md": "audit.md", "comparison.md": "remediation.md"}
    if not (run_dir / "audit-2.json").is_file():
        print(f"no audit-2.json in {run_dir}", file=sys.stderr)
        return 2
    ensure_excluded(root)
    d = new_audit_dir(root)
    copied = []
    for s, t in src.items():
        if (run_dir / s).is_file():
            shutil.copy2(run_dir / s, d / t)
            copied.append(t)
    out({"audit_dir": str(d), "files": copied})
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd, args = argv[0], argv[1:]
    spec = {
        "hashes": (1, lambda: cmd_hashes(Path(args[0]).resolve())),
        "validate": (1, lambda: cmd_validate(args[0])),
        "stale": (2, lambda: cmd_stale(args[0], Path(args[1]).resolve())),
        "init": (1, lambda: cmd_init(Path(args[0]).resolve())),
        "scope": (2, lambda: cmd_scope(Path(args[0]).resolve(), Path(args[1]).resolve())),
        "diff": (2, lambda: cmd_diff(Path(args[0]).resolve(), Path(args[1]).resolve())),
        "keep-check": (3, lambda: cmd_keep_check(args[0], Path(args[1]).resolve(), Path(args[2]).resolve())),
        "restore": (2, lambda: cmd_restore(Path(args[0]).resolve(), Path(args[1]).resolve())),
        "audit-dir": (1, lambda: cmd_audit_dir(Path(args[0]).resolve())),
        "latest-audit": (1, lambda: cmd_latest_audit(Path(args[0]).resolve())),
        "publish": (2, lambda: cmd_publish(Path(args[0]).resolve(), Path(args[1]).resolve())),
    }
    if cmd not in spec or len(args) != spec[cmd][0]:
        print(__doc__, file=sys.stderr)
        return 2
    return spec[cmd][1]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
