#!/usr/bin/env python3
"""Deterministic pre-scan for AGENTS.md work. Standard library only.

Collects the facts a model should not guess: which instruction files exist, how big
they are, which referenced paths and commands do not resolve, which lines match known
noise patterns, and where the repository has real boundaries.

The output is evidence, not a verdict. Scoring is done by the skill using guide.md.

Usage:
    python scan_agents_md.py [REPO_ROOT] [--format json|md]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "target", "build", "dist", "out",
    ".venv", "venv", "__pycache__", ".idea", ".vscode", ".gradle", ".next", ".nuxt",
    ".tox", ".mypy_cache", ".pytest_cache", "coverage", ".terraform", "bin", "obj",
    ".oatrta", ".audit",
}

MANIFESTS = {
    "package.json": "node", "pom.xml": "maven", "build.gradle": "gradle",
    "build.gradle.kts": "gradle", "go.mod": "go", "pyproject.toml": "python",
    "setup.py": "python", "requirements.txt": "python", "Cargo.toml": "rust",
    "Gemfile": "ruby", "composer.json": "php", "mix.exs": "elixir",
    "CMakeLists.txt": "cmake", "Package.swift": "swift",
}
MANIFEST_SUFFIXES = {".csproj": "dotnet", ".fsproj": "dotnet", ".sln": "dotnet"}

OTHER_INSTRUCTION_FILES = [
    "CLAUDE.md", "GEMINI.md", "CONVENTIONS.md", ".cursorrules", ".windsurfrules",
    ".github/copilot-instructions.md", ".junie/guidelines.md",
]

TOOLING_FILES = {
    "formatter_linter": [
        ".editorconfig", ".prettierrc", ".prettierrc.json", ".prettierrc.yml",
        "prettier.config.js", ".eslintrc", ".eslintrc.json", ".eslintrc.js",
        "eslint.config.js", "eslint.config.mjs", "biome.json", "checkstyle.xml",
        ".golangci.yml", ".golangci.yaml", "ruff.toml", ".ruff.toml", ".flake8",
        ".rubocop.yml", "rustfmt.toml", ".clang-format", "detekt.yml", "sonar-project.properties",
    ],
    "ci": [
        ".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", ".circleci/config.yml",
        "bitbucket-pipelines.yml", ".travis.yml",
    ],
    "task_runner": ["Makefile", "makefile", "justfile", "Justfile", "Taskfile.yml", "tox.ini", "noxfile.py"],
    "ownership": ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"],
    "docs": ["README.md", "CONTRIBUTING.md", "ARCHITECTURE.md", "docs/README.md"],
    "hooks": [".pre-commit-config.yaml", ".husky", "lefthook.yml"],
}

GENERIC_PATTERNS = [
    r"\bclean code\b", r"\bbest practices?\b", r"\bfollow (the )?existing (patterns?|conventions?|style)\b",
    r"\bfollow the (architecture|conventions|style guide)\b", r"\bhigh[- ]quality\b",
    r"\bmaintainable\b", r"\breadable code\b", r"\bself[- ]documenting\b", r"\bSOLID\b", r"\bDRY\b",
    r"\bKISS\b", r"\bmeaningful (variable |function )?names\b", r"\bwrite tests? for (all|every|new)\b",
    r"\bbe careful\b", r"\bmake sure (everything|all tests?) (works?|pass(es)?)\b",
    r"\bkeep (it|things|code) simple\b", r"\bwell[- ]documented\b", r"\byou are an? (expert|senior)\b",
    r"\bproper error handling\b", r"\bavoid (code )?duplication\b",
]

OVERVIEW_PATTERNS = [
    r"^\s*this (project|repository|repo|application|codebase) is (a|an|the)\b",
    r"\bis (built|written) (with|in|using)\b", r"\bwe use (react|java|python|go|typescript|spring|node)\b",
    r"\btech(nology)? stack\b",
]

SECRET_PATTERNS = [
    ("aws_access_key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    ("slack_token", r"\bxox[abpsr]-[A-Za-z0-9-]{10,}\b"),
    ("generic_api_key", r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ("bearer_token", r"\bBearer\s+[A-Za-z0-9._-]{25,}\b"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"),
    ("credential_assignment",
     r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"]?(?!<|\$|\{|your|xxx|\*|example|changeme)[^\s'\"`]{8,}"),
    ("url_with_credentials", r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]+@"),
]

COMMAND_TOOLS = (
    "npm", "pnpm", "yarn", "bun", "npx", "make", "mvn", "./mvnw", "gradle", "./gradlew", "go",
    "cargo", "pytest", "python", "python3", "uv", "poetry", "tox", "nox", "just", "task",
    "docker", "dotnet", "bazel", "ruff", "eslint", "tsc",
)
PKG_BUILTINS = {
    "install", "i", "ci", "add", "remove", "rm", "exec", "dlx", "create", "init", "update", "up",
    "outdated", "audit", "publish", "link", "why", "list", "ls", "config", "cache", "pack",
    "rebuild", "prune", "dedupe", "store", "workspace", "workspaces", "version", "login", "x",
    "help", "info", "view", "set", "get", "import", "patch", "upgrade", "global", "pm",
}
PATH_EXTENSIONS = (
    ".md", ".json", ".yml", ".yaml", ".toml", ".xml", ".java", ".kt", ".go", ".py", ".ts", ".tsx",
    ".js", ".jsx", ".mjs", ".rs", ".rb", ".php", ".cs", ".sh", ".sql", ".proto", ".gradle",
    ".properties", ".tf", ".xsl", ".xslt", ".xq", ".cfg", ".ini", ".lock", ".txt", ".html", ".css",
)

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
TREE_RE = re.compile(r"[├└│]──|^\s*\|--|^\s*\+--")
PROSE_CWD_RE = re.compile(r"(?i)\b(?:from|in|inside|within|under)\s+(?:the\s+)?`([^`\s]+)`")
CWD_HINT_RE = re.compile(r"(?i)\b(from|in|inside|within|under|at)\b[^.\n]*`[^`]+`|\bcd\s+\S+|\brepo(sitory)? root\b")


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        yield Path(dirpath), dirnames, filenames


def rel(root: Path, p: Path) -> str:
    try:
        r = p.relative_to(root).as_posix()
    except ValueError:
        r = p.as_posix()
    return r or "."


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def package_scripts(d: Path) -> set[str] | None:
    pj = d / "package.json"
    if not pj.is_file():
        return None
    try:
        return set((json.loads(read_text(pj)).get("scripts") or {}).keys())
    except (ValueError, AttributeError):
        return None


def make_targets(d: Path) -> set[str] | None:
    for name in ("Makefile", "makefile", "GNUmakefile"):
        mf = d / name
        if mf.is_file():
            targets: set[str] = set()
            for line in read_text(mf).splitlines():
                m = re.match(r"^([A-Za-z0-9_./%-]+(?:\s+[A-Za-z0-9_./%-]+)*)\s*:(?!=)", line)
                if m and not line.startswith("\t"):
                    targets.update(m.group(1).split())
            return targets
    return None


def split_command(cmd: str):
    """Return (cwd_from_cd, remaining_command)."""
    cwd = None
    m = re.match(r"^\s*cd\s+(\S+)\s*(?:&&|;)\s*(.+)$", cmd)
    if m:
        cwd, cmd = m.group(1).strip("'\""), m.group(2)
    return cwd, cmd.strip()


def prose_cwd(text: str) -> str | None:
    """Working directory stated in prose, e.g. "From `services/api`, run ..."."""
    m = None
    for m in PROSE_CWD_RE.finditer(text):
        pass
    return m.group(1).strip() if m else None


def check_command(cmd: str, file_dir: Path, root: Path, cwd_hint: str | None = None) -> dict | None:
    """Return a problem dict when the command provably does not resolve, else None."""
    cwd, body = split_command(cmd)
    if not cwd and cwd_hint and any((b / cwd_hint).is_dir() for b in (file_dir, root)):
        cwd = cwd_hint
    body = re.split(r"\s*(?:&&|\|\||;|\|)\s*", body)[0]
    tokens = body.split()
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return None
    tool, args = tokens[0], tokens[1:]

    dirs: list[Path] = []
    if cwd:
        for base in (file_dir, root):
            cand = (base / cwd).resolve()
            if cand.is_dir():
                dirs.append(cand)
        if not dirs:
            return {"problem": "cd target does not exist", "detail": cwd}
    else:
        dirs = [file_dir] if file_dir == root else [file_dir, root]

    if tool in ("npm", "pnpm", "yarn", "bun"):
        if not args or args[0].startswith("-"):
            return None
        script = None
        if args[0] == "run" and len(args) > 1 and not args[1].startswith("-"):
            script = args[1]
        elif tool in ("pnpm", "yarn", "bun") and args[0] not in PKG_BUILTINS and args[0] not in ("test", "start", "run"):
            script = args[0]
        elif tool == "npm" and args[0] in ("test", "start"):
            script = args[0]
        if not script:
            return None
        known = [s for s in (package_scripts(d) for d in dirs) if s is not None]
        if not known:
            return {"problem": "no package.json in the expected directory", "detail": script,
                    "looked_in": [rel(root, d) for d in dirs]}
        if not any(script in s for s in known):
            return {"problem": "package.json script not found", "detail": script,
                    "looked_in": [rel(root, d) for d in dirs]}
        return None

    if tool == "make":
        targets = [a for a in args if not a.startswith("-") and "=" not in a]
        if "-C" in args or "-f" in args or not targets:
            return None
        known = [t for t in (make_targets(d) for d in dirs) if t is not None]
        if not known:
            return {"problem": "no Makefile in the expected directory", "detail": targets[0],
                    "looked_in": [rel(root, d) for d in dirs]}
        missing = [t for t in targets if not any(t in k or any("%" in x for x in k) for k in known)]
        if missing:
            return {"problem": "make target not found", "detail": ", ".join(missing),
                    "looked_in": [rel(root, d) for d in dirs]}
        return None

    if tool in ("./mvnw", "./gradlew"):
        if not any((d / tool[2:]).is_file() for d in dirs):
            return {"problem": "wrapper script not found", "detail": tool,
                    "looked_in": [rel(root, d) for d in dirs]}
    return None


def looks_like_path(token: str) -> bool:
    if " " in token or len(token) < 3 or len(token) > 200:
        return False
    if re.search(r"[<>{}*$|=(),;]|://|^[@~\-#]|^\.\.?$", token):
        return False
    if token.startswith(("http", "www.")):
        return False
    return "/" in token or token.lower().endswith(PATH_EXTENSIONS)


def check_path(token: str, file_dir: Path, root: Path) -> str | None:
    """Return 'missing' when the path is credibly a repo path and does not exist."""
    clean = re.sub(r"(:\d+(-\d+)?|#L?\d+.*)$", "", token).rstrip(".,:")
    clean = clean.lstrip("/") if clean.startswith("/") and not Path(clean).exists() else clean
    if not clean:
        return None
    for base in (file_dir, root):
        if (base / clean).exists():
            return None
    first = clean.split("/")[0]
    has_ext = clean.lower().endswith(PATH_EXTENSIONS)
    first_exists = any((base / first).exists() for base in (file_dir, root))
    credible = first_exists or (has_ext and "/" in clean) or token.endswith("/")
    if not credible and has_ext and "/" not in clean:
        # bare filename: only flag if no file with that name exists anywhere
        for _, _, filenames in walk(root):
            if clean in filenames:
                return None
        return "missing"
    return "missing" if credible else None


def analyze_file(path: Path, root: Path) -> dict:
    text = read_text(path)
    lines = text.splitlines()
    file_dir = path.parent
    in_fence = False
    fence_lang = ""
    headings: list[tuple[int, str, int]] = []
    generic, overview, secrets, tree_lines = [], [], [], []
    commands, missing_paths, seen_paths = [], [], set()
    content_lines: dict[int, bool] = {}
    last_prose = ""

    for i, line in enumerate(lines, 1):
        for name, pat in SECRET_PATTERNS:
            if re.search(pat, line):
                secrets.append({"line": i, "type": name})
                break
        if FENCE_RE.match(line):
            if not in_fence:
                fence_lang = line.strip().strip("`~").strip().lower()
            in_fence = not in_fence
            content_lines[i] = True
            continue
        if TREE_RE.search(line):
            tree_lines.append(i)
        if in_fence:
            content_lines[i] = True
            stripped = re.sub(r"^\s*[$>]\s+", "", line).strip()
            if fence_lang in ("", "sh", "bash", "shell", "zsh", "console", "powershell", "cmd", "bat") \
                    and stripped and not stripped.startswith("#"):
                first = split_command(stripped)[1].split()[:1]
                if stripped.startswith("cd ") or (first and first[0] in COMMAND_TOOLS):
                    commands.append((i, stripped, prose_cwd(last_prose)))
            continue

        h = HEADING_RE.match(line)
        if h:
            headings.append((len(h.group(1)), h.group(2), i))
            continue
        if line.strip():
            content_lines[i] = True
            last_prose = line
        else:
            last_prose = ""
        for pat in GENERIC_PATTERNS:
            m = re.search(pat, line, flags=re.I if pat not in (r"\bSOLID\b", r"\bDRY\b", r"\bKISS\b") else 0)
            if m:
                generic.append({"line": i, "match": m.group(0), "text": line.strip()[:160]})
                break
        for pat in OVERVIEW_PATTERNS:
            if re.search(pat, line, flags=re.I):
                overview.append({"line": i, "text": line.strip()[:160]})
                break
        for m in INLINE_CODE_RE.finditer(line):
            token = m.group(1).strip()
            first = split_command(token)[1].split()[:1]
            if first and first[0] in COMMAND_TOOLS and " " in token:
                commands.append((i, token, prose_cwd(line[:m.start()])))
            elif looks_like_path(token) and token not in seen_paths:
                seen_paths.add(token)
                if check_path(token, file_dir, root) == "missing":
                    missing_paths.append({"line": i, "path": token})

    empty_headings = []
    for idx, (level, title, ln) in enumerate(headings):
        nxt = headings[idx + 1] if idx + 1 < len(headings) else None
        end = nxt[2] if nxt else len(lines) + 1
        has_content = any(content_lines.get(n) for n in range(ln + 1, end))
        if not has_content and (nxt is None or nxt[0] <= level):
            empty_headings.append({"line": ln, "heading": title})

    cmd_out, cmd_problems = [], []
    for ln, cmd, hint in commands:
        context = " ".join(lines[max(0, ln - 4):ln])
        entry = {"line": ln, "command": cmd, "has_cwd_hint": bool(CWD_HINT_RE.search(context))}
        if hint:
            entry["stated_cwd"] = hint
        problem = check_command(cmd, file_dir, root, hint)
        if problem:
            entry["unresolved"] = problem
            cmd_problems.append(entry)
        cmd_out.append(entry)

    return {
        "path": rel(root, path),
        "scope": rel(root, file_dir),
        "lines": len(lines),
        "non_blank_lines": sum(1 for l in lines if l.strip()),
        "words": len(text.split()),
        "approx_tokens": len(text) // 4,
        "headings": [{"level": l, "title": t, "line": n} for l, t, n in headings],
        "empty_headings": empty_headings,
        "generic_phrases": generic,
        "overview_prose": overview,
        "tree_listing_lines": tree_lines if len(tree_lines) >= 4 else [],
        "secrets": secrets,
        "commands": cmd_out,
        "unresolved_commands": cmd_problems,
        "missing_paths": missing_paths,
    }


def scan_repo(root: Path) -> dict:
    agents_files: list[Path] = []
    manifest_dirs: dict[str, set[str]] = {}
    workflows: list[str] = []
    for d, _, filenames in walk(root):
        for f in filenames:
            if f == "AGENTS.md":
                agents_files.append(d / f)
            eco = MANIFESTS.get(f) or MANIFEST_SUFFIXES.get(Path(f).suffix)
            if eco:
                manifest_dirs.setdefault(rel(root, d), set()).add(eco)
    wf = root / ".github" / "workflows"
    if wf.is_dir():
        workflows = sorted(rel(root, p) for p in wf.iterdir() if p.suffix in (".yml", ".yaml"))

    agents_scopes = {rel(root, p.parent) for p in agents_files}

    def covered_by(dir_rel: str) -> str | None:
        parts = [] if dir_rel == "." else dir_rel.split("/")
        while True:
            scope = "/".join(parts) or "."
            if scope in agents_scopes:
                return scope
            if not parts:
                return None
            parts.pop()

    root_ecos = manifest_dirs.get(".", set())
    boundaries = []
    for d in sorted(manifest_dirs):
        if d == ".":
            continue
        ecos = sorted(manifest_dirs[d])
        boundaries.append({
            "dir": d, "ecosystems": ecos, "nearest_agents_md": covered_by(d),
            "has_own_agents_md": d in agents_scopes,
            "differs_from_root": bool(root_ecos) and not set(ecos) <= root_ecos,
            "has_own_task_runner": any((root / d / n).is_file() for n in ("Makefile", "justfile", "Taskfile.yml")),
        })

    others = []
    root_agents = root / "AGENTS.md"
    root_agents_text = read_text(root_agents) if root_agents.is_file() else None
    for name in OTHER_INSTRUCTION_FILES:
        p = root / name
        if p.exists():
            text = read_text(p) if p.is_file() else ""
            others.append({
                "path": name, "lines": len(text.splitlines()), "is_symlink": p.is_symlink(),
                "identical_to_root_agents_md": root_agents_text is not None and text == root_agents_text,
                "mentions_agents_md": "AGENTS.md" in text,
            })
    for sub in (".cursor/rules", ".github/instructions"):
        p = root / sub
        if p.is_dir():
            others.append({"path": sub + "/", "files": sorted(x.name for x in p.iterdir())[:30]})

    tooling = {k: [n for n in names if (root / n).exists()] for k, names in TOOLING_FILES.items()}
    tooling["ci"] = tooling["ci"] + workflows
    generated = []
    ga = root / ".gitattributes"
    if ga.is_file():
        generated = [l.split()[0] for l in read_text(ga).splitlines() if "linguist-generated" in l and l.split()]

    files = [analyze_file(p, root) for p in sorted(agents_files)]
    return {
        "repo_root": str(root),
        "agents_md_count": len(files),
        "has_root_agents_md": "." in agents_scopes,
        "agents_md_files": files,
        "other_instruction_files": others,
        "manifest_dirs": {"root": sorted(root_ecos), "nested": boundaries},
        "nested_candidates": [b["dir"] for b in boundaries
                              if not b["has_own_agents_md"] and (b["differs_from_root"] or b["has_own_task_runner"])],
        "tooling": tooling,
        "gitattributes_generated": generated,
        "blocker_hints": {
            "B1_secret": sum(len(f["secrets"]) for f in files),
            "B2_stale_command": sum(len(f["unresolved_commands"]) for f in files),
            "B3_stale_path": sum(len(f["missing_paths"]) for f in files),
        },
    }


def to_markdown(r: dict) -> str:
    out = [f"# AGENTS.md scan: {r['repo_root']}", "",
           f"- AGENTS.md files: {r['agents_md_count']} (root: {'yes' if r['has_root_agents_md'] else 'no'})",
           f"- Blocker hints: {r['blocker_hints']}",
           f"- Nested candidates without their own file: {r['nested_candidates'] or 'none'}",
           f"- Other instruction files: {[o['path'] for o in r['other_instruction_files']] or 'none'}", ""]
    for f in r["agents_md_files"]:
        out += [f"## {f['path']}",
                f"{f['lines']} lines, {f['words']} words, ~{f['approx_tokens']} tokens, {len(f['commands'])} commands", ""]
        for key, label in (("secrets", "Possible secrets"), ("unresolved_commands", "Unresolved commands"),
                           ("missing_paths", "Missing paths"), ("generic_phrases", "Generic phrases"),
                           ("overview_prose", "Overview prose"), ("empty_headings", "Empty headings")):
            if f[key]:
                out.append(f"**{label}**")
                out += [f"- L{x['line']}: " + json.dumps({k: v for k, v in x.items() if k != 'line'}, ensure_ascii=False)
                        for x in f[key]]
                out.append("")
        if f["tree_listing_lines"]:
            out += [f"**Directory listing** at lines {f['tree_listing_lines'][0]} to {f['tree_listing_lines'][-1]}", ""]
        no_cwd = [c for c in f["commands"] if not c["has_cwd_hint"]]
        if no_cwd and r["manifest_dirs"]["nested"]:
            out.append("**Commands with no working-directory hint (multi-project repo)**")
            out += [f"- L{c['line']}: `{c['command']}`" for c in no_cwd]
            out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    result = scan_repo(root)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(to_markdown(result) if args.format == "md" else json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
