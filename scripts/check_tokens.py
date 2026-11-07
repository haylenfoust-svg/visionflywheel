#!/usr/bin/env python3
"""
Token discipline lint — the "Friday test" from the UI/UX Pro Max guidance.

Fails the build if raw hex / rgb / arbitrary-value bracket syntax appears
in component files (outside of `design-system.scss` and `tokens.ts`).

Usage:
    python scripts/check_tokens.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent / "frontend" / "src"
# Files allowed to contain raw values (token definitions)
ALLOWED_FILES = {"design-system.scss", "tokens.ts"}

# Patterns that signal raw-value leakage
PATTERNS = [
    (re.compile(r"#[0-9a-fA-F]{3,8}\b"), "raw hex color"),
    (re.compile(r"rgba?\([^)]+\)"), "raw rgb/rgba"),
    (re.compile(r"\[[0-9-]+px\]"), "arbitrary px value"),
    (re.compile(r"\[#[0-9a-fA-F]{3,8}\]"), "arbitrary hex value"),
]


def check_file(path: Path) -> list[tuple[int, str, str]]:
    if path.name in ALLOWED_FILES:
        return []
    if path.suffix not in {".vue", ".ts", ".scss"}:
        return []

    text = path.read_text(encoding="utf-8", errors="ignore")
    # Skip comments and CSS var declarations
    lines = text.splitlines()
    findings: list[tuple[int, str, str]] = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        if "var(--" in line:
            continue
        # Skip the tokens.ts import line (it's the token source)
        if "from '@/styles/tokens'" in line:
            continue
        # Skip default prop values that call token() — they contain no hex
        if "token(" in line and "chart" in line:
            continue

        for pattern, label in PATTERNS:
            for match in pattern.finditer(line):
                findings.append((i, label, match.group()))

    return findings


def main() -> int:
    total = 0
    for path in sorted(ROOT.rglob("*")):
        findings = check_file(path)
        if findings:
            print(f"\n{path.relative_to(ROOT.parent)}")
            for lineno, label, value in findings:
                print(f"  L{lineno}: {label}: {value}")
                total += 1

    if total:
        print(f"\n✗ {total} raw values found. Use tokens from '@/styles/tokens' instead.")
        print("  Rule: tokens first, fence forever — never hardcode hex/rgb/px in components.")
        return 1

    print("✓ Token discipline clean — no raw hex/rgb/arbitrary values in components.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
