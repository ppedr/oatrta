#!/usr/bin/env python3
"""Copy shared/ sources into every skill so each skill folder stays self-contained.

    python scripts/sync_shared.py          # write copies
    python scripts/sync_shared.py --check  # exit 1 if any copy drifted (use in CI)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {
    "shared/guide.md": "references/guide.md",
    "shared/scan_agents_md.py": "scripts/scan_agents_md.py",
}


def main() -> int:
    check = "--check" in sys.argv[1:]
    drift = []
    for skill in sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file()):
        for src_rel, dst_rel in TARGETS.items():
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
