#!/usr/bin/env python3
"""Copy shared sources into the skills that need them, so each skill folder stays self-contained.

    python scripts/sync_shared.py          # write copies
    python scripts/sync_shared.py --check  # exit 1 if any copy drifted (use in CI)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# source (repo-relative) -> destination (skill-relative), for every skill
COMMON = {
    "shared/guide.md": "references/guide.md",
    "shared/scan_agents_md.py": "scripts/scan_agents_md.py",
}

# extra copies per skill
EXTRA = {
    "agents-md-audit": {
        "shared/audit-schema.json": "references/audit-schema.json",
        "shared/run_tools.py": "scripts/run_tools.py",
    },
    "agents-md-remediate": {
        "shared/audit-schema.json": "references/audit-schema.json",
        "shared/run_tools.py": "scripts/run_tools.py",
        "skills/agents-md-audit/SKILL.md": "references/audit-procedure.md",
        "skills/agents-md-audit/references/report-template.md": "references/report-template.md",
        "skills/agents-md-refactor/SKILL.md": "references/refactor-procedure.md",
    },
}


def version_mismatch() -> str | None:
    """The version lives only in plugin.json. A second copy in marketplace.json would drift."""
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    dup = [p.get("name") for p in market.get("plugins", []) if "version" in p]
    if dup or "version" in market or "version" in market.get("metadata", {}):
        return ("marketplace.json must not set version; bump it only in .claude-plugin/plugin.json"
                + (f" (entries: {dup})" if dup else ""))
    return None


def main() -> int:
    check = "--check" in sys.argv[1:]
    mismatch = version_mismatch()
    if mismatch:
        print(mismatch)
        return 1
    drift = []
    for skill in sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file()):
        for src_rel, dst_rel in {**COMMON, **EXTRA.get(skill.name, {})}.items():
            src, dst = ROOT / src_rel, skill / dst_rel
            data = src.read_bytes()
            if dst.is_file() and dst.read_bytes() == data:
                continue
            drift.append(dst.relative_to(ROOT).as_posix())
            if not check:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
    if check and drift:
        print("out of sync, run scripts/sync_shared.py:\n  " + "\n  ".join(drift))
        return 1
    print("in sync" if not drift else "updated:\n  " + "\n  ".join(drift))
    return 0


if __name__ == "__main__":
    sys.exit(main())
