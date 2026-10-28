"""Check that the code and output samples in the ECS course's guides match the
chapter files they come from.

    python tools/check_snippets.py

Each guide in ecs/docs names its chapter's source on a line of its own, in
backticks. Then:

  * every ```rin block must appear in that source exactly, as consecutive
    lines, indentation included;
  * every plain ``` block whose first line is a line of the chapter's .expected
    is an output sample: its lines, except "...", must appear in the .expected
    in the same order.

Each dojo block's README is checked the same way against every file of its
block: its playground, harness, solution and levels, and dojo/dojo.rin; and
its output samples against the playground's and the harness's expected
output.

Plain blocks that do not start with an output line, such as diagrams, are not
checked. A guide that passes can be copied from with confidence.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "ecs" / "docs"


def blocks(text: str) -> list[tuple[str, list[str], int]]:
    """(language, lines, line number) for every fenced block."""
    found = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^```(\w*)\s*$", lines[i])
        if m:
            lang, start, body = m.group(1), i + 1, []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                body.append(lines[i])
                i += 1
            found.append((lang, body, start))
        i += 1
    return found


def in_order(sample: list[str], expected: list[str]) -> bool:
    at = 0
    for line in sample:
        if line.strip() == "...":
            continue
        try:
            at = expected.index(line, at) + 1
        except ValueError:
            return False
    return True


def guides() -> list[tuple[Path, list[str], list[str], str, str]]:
    """(guide, source texts, expected lines, what the code is, what the output is)"""
    found = []
    for doc in sorted(DOCS.glob("*.md")):
        m = re.search(r"^`(ecs/src/[^`]+\.rin)`", doc.read_text(encoding="utf-8"), re.M)
        if not m:
            continue
        source_path = ROOT / m.group(1)
        expected_path = source_path.with_suffix(".expected")
        expected = expected_path.read_text(encoding="utf-8").split("\n") if expected_path.exists() else []
        found.append((doc, [source_path.read_text(encoding="utf-8")], expected, m.group(1),
                      expected_path.relative_to(ROOT).as_posix()))
    for block in sorted(p for p in (ROOT / "dojo").glob("*.*") if (p / "README.md").exists()):
        files = sorted(f for f in block.rglob("*.rin") if f.name != "kata.rin")
        texts = [f.read_text(encoding="utf-8") for f in files + [ROOT / "dojo" / "dojo.rin"]]
        outputs = sorted(block.glob("*.expected"))
        expected = [line for o in outputs for line in o.read_text(encoding="utf-8").split("\n")]
        name = block.relative_to(ROOT).as_posix()
        found.append((block / "README.md", texts, expected, name, name + "'s expected output"))
    return found


def main() -> int:
    failures = 0
    checked = 0
    for doc, sources, expected, code_name, output_name in guides():
        text = doc.read_text(encoding="utf-8")
        for lang, body, line in blocks(text):
            if lang == "rin":
                checked += 1
                if not any("\n".join(body) in source for source in sources):
                    failures += 1
                    print(f"{doc.relative_to(ROOT)}:{line}: rin sample not found in {code_name}")
                    for b in body[:3]:
                        print(f"      {b}")
            elif lang == "" and body and body[0] in expected:
                checked += 1
                if not in_order(body, expected):
                    failures += 1
                    print(f"{doc.relative_to(ROOT)}:{line}: output sample does not match {output_name}")
    print(f"{checked - failures} of {checked} samples match")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
