"""The dojo's runner: start a kata, run it against its harness, keep your times.

    python tools/dojo.py                         the blocks, your reps, and what is due
    python tools/dojo.py start slot_map 2        a fresh kata.rin from level 2; the clock starts
    python tools/dojo.py slot_map                build the harness with your kata.rin and run it
    python tools/dojo.py slot_map --seed 42 --stop 1337
                                                 the same fuzz run, stopping before operation 1337
    python tools/dojo.py slot_map --sanitize     with AddressSanitizer and UBSan
    python tools/dojo.py play slot_map           the block's playground

A block can be named by its number, its name, or the start of its name:
`3`, `slot_map` and `slot` are the same block.

When a started kata passes, the time since `start` is added to dojo/log.md,
and the block is due again after 1, 3, 7, 14, then 30 days, counting its
passes. Spaced reps are what make a block stick, more than many in one day.

If the harness crashes rather than failing a check (an out-of-bounds index,
say), the runner runs it again with --trace to show the operation that was
running.

Your kata.rin files are yours: git ignores them, and `start` will not
overwrite one you have changed unless you add --force. A kata is a whole
program: it imports what it uses and the harness, which has main, so the
runner builds kata.rin, and the harness comes with it. rin and the C compiler
are found as tools/check.py finds them.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import find_rin, list_from_build_rin  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOJO = ROOT / "dojo"
OUT = ROOT / "build" / "dojo"
LOG = DOJO / "log.md"
STARTED = DOJO / ".started.json"
INTERVALS = [1, 3, 7, 14, 30]


def blocks() -> list[Path]:
    return sorted((p for p in DOJO.iterdir() if p.is_dir() and re.match(r"\d+\.", p.name)),
                  key=lambda p: int(p.name.split(".")[0]))


def name_of(block: Path) -> str:
    return block.name.split(".", 1)[1]


def find(word: str) -> Path:
    found = [b for b in blocks() if word in (b.name, name_of(b), b.name.split(".")[0])]
    found = found or [b for b in blocks() if name_of(b).startswith(word)]
    if len(found) != 1:
        sys.exit(f"dojo: no single block called {word!r}; the blocks are "
                 + ", ".join(name_of(b) for b in blocks()))
    return found[0]


# The target times, from the level table in each block's README:
# | 2 | every proc | 8:00 |
def targets(block: Path) -> dict[int, str]:
    readme = block / "README.md"
    text = readme.read_text(encoding="utf-8") if readme.exists() else ""
    return {int(m.group(1)): m.group(2) for m in re.finditer(r"^\| (\d) \|.*\| (\d+:\d\d) \|$", text, re.M)}


# rin writes C, and the C compiler does the rest, as tools/check.py does. A
# kata in progress is full of unused parameters and locals, so the warnings for
# those are off and warnings are not errors; tools/check.py builds the
# solutions with -Werror and every warning on.
def build(source: Path, exe: Path, sanitize: bool) -> None:
    exe.parent.mkdir(parents=True, exist_ok=True)
    rin = find_rin()
    c_path = exe.with_suffix(".c")
    translate = subprocess.run([str(rin), "compile", str(source), "-o", str(c_path),
                                "--header", str(exe.with_suffix(".h"))], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    noise = [l for l in translate.stdout.splitlines() if l.strip() and not l.startswith("rin: generated")]
    if translate.returncode != 0 or noise:
        print(translate.stdout, end="")
        sys.exit(1)
    cc = os.environ.get("CC", "clang")
    flags = ["-std=c11", "-g", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-unused-variable",
             "-Wno-unused-but-set-variable", "-Wno-unused-function"]
    flags += [f"-D{define}" for define in list_from_build_rin("build_defines") or []]
    if sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
    includes = ["-I", str(rin.parent), "-I", str(rin.parent / "std")]
    libs = [] if os.name == "nt" else ["-lm"]
    if subprocess.run([cc, *flags, *includes, str(c_path), "-o", str(exe), *libs]).returncode != 0:
        sys.exit(1)


def load_started() -> dict:
    try:
        return json.loads(STARTED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_started(started: dict) -> None:
    STARTED.write_text(json.dumps(started, indent=2) + "\n", encoding="utf-8")


def log_rows() -> list[list[str]]:
    if not LOG.exists():
        return []
    rows = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.match(r"\d{4}-\d\d-\d\d", cells[0]):
            rows.append(cells)
    return rows


def minutes(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def seconds(text: str) -> int:
    m, s = text.split(":")
    return int(m) * 60 + int(s)


def due(passes: list[dt.date]) -> dt.date | None:
    if not passes:
        return None
    return max(passes) + dt.timedelta(days=INTERVALS[min(len(passes), len(INTERVALS)) - 1])


def status() -> int:
    rows = log_rows()
    today = dt.date.today()
    started = load_started()
    print(f"{'block':<16}{'reps':>5}  {'best time, level':<18}{'last':<12}next")
    for b in blocks():
        mine = [r for r in rows if r[1] == name_of(b)]
        passes = [dt.date.fromisoformat(r[0]) for r in mine]
        best = min(mine, key=lambda r: (-int(r[2]), seconds(r[3])), default=None)
        best_text = f"{best[3]}, level {best[2]}" if best else "-"
        next_day = due(passes)
        next_text = "now" if next_day is None or next_day <= today else next_day.isoformat()
        if name_of(b) in started:
            next_text = f"started, level {started[name_of(b)]['level']}"
        last = max(passes).isoformat() if passes else "-"
        print(f"{b.name:<16}{len(mine):>5}  {best_text:<18}{last:<12}{next_text}")
    print()
    print("start one with: python tools/dojo.py start <block> <level 1 to 3>")
    return 0


def start(word: str, level: str, force: bool) -> int:
    b = find(word)
    source = b / f"level{level}.rin"
    if not source.exists():
        sys.exit(f"dojo: {name_of(b)} has no level {level}; the levels are "
                 + ", ".join(p.stem[len("level"):] for p in sorted(b.glob("level*.rin"))))
    kata = b / "kata.rin"
    untouched = [p.read_text(encoding="utf-8") for p in b.glob("level*.rin")]
    if kata.exists() and kata.read_text(encoding="utf-8") not in untouched and not force:
        sys.exit(f"dojo: {kata.relative_to(ROOT)} has your work in it; add --force to replace it")
    shutil.copyfile(source, kata)
    started = load_started()
    started[name_of(b)] = {"level": int(level), "at": dt.datetime.now().isoformat(timespec="seconds")}
    save_started(started)
    target = targets(b).get(int(level))
    print(f"{kata.relative_to(ROOT)} is level {level}" + (f"; the target is {target}" if target else ""))
    print(f"the clock is running. Test it with: python tools/dojo.py {name_of(b)}")
    return 0


# Run a program, printing what it prints as it prints it, and keep the text to
# look for PASS in.
def stream(cmd: list[str]) -> tuple[int, str]:
    lines = []
    with subprocess.Popen(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as p:
        for line in p.stdout:
            print(line, end="", flush=True)
            lines.append(line)
    return p.returncode, "".join(lines)


def check(word: str, args: list[str]) -> int:
    b = find(word)
    if not (b / "kata.rin").exists():
        sys.exit(f"dojo: no kata.rin in {b.relative_to(ROOT)} yet; start one with: "
                 f"python tools/dojo.py start {name_of(b)} 1")
    passthrough = [a for a in args if a != "--sanitize"]
    exe = OUT / name_of(b) / ("harness.exe" if os.name == "nt" else "harness")
    build(b / "kata.rin", exe, "--sanitize" in args)
    code, out = stream([str(exe), *passthrough])
    if code != 0 and not any(line.startswith("FAIL") for line in out.splitlines()):
        traced = subprocess.run([str(exe), *passthrough, "--trace", "1"], cwd=ROOT, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        ops = [l for l in traced.stdout.splitlines() if l.startswith("operation ")]
        print("the harness crashed" + (f"; the last operation it started was\n    {ops[-1]}" if ops
                                       else " in the scenario, after the last step printed above"))
    if code != 0 or "PASS" not in out.splitlines():
        return 1
    started = load_started()
    entry = started.pop(name_of(b), None)
    if entry and not passthrough:
        took = (dt.datetime.now() - dt.datetime.fromisoformat(entry["at"])).total_seconds()
        if not LOG.exists():
            LOG.write_text("# Dojo log\n\n| date | block | level | time |\n|---|---|---|---|\n", encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"| {dt.date.today().isoformat()} | {name_of(b)} | {entry['level']} | {minutes(took)} |\n")
        save_started(started)
        target = targets(b).get(entry["level"])
        print(f"\nlevel {entry['level']} in {minutes(took)}" + (f", target {target}" if target else ""))
        passes = [dt.date.fromisoformat(r[0]) for r in log_rows() if r[1] == name_of(b)]
        print(f"logged in {LOG.relative_to(ROOT)}; {name_of(b)} is due again on {due(passes).isoformat()}")
    return 0


def play(word: str) -> int:
    b = find(word)
    exe = OUT / name_of(b) / ("playground.exe" if os.name == "nt" else "playground")
    build(b / f"play_{name_of(b)}.rin", exe, False)
    return subprocess.run([str(exe)], cwd=ROOT).returncode


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return status()
    if args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if args[0] == "start":
        rest = [a for a in args[1:] if a != "--force"]
        if len(rest) != 2:
            sys.exit("dojo: start <block> <level>")
        return start(rest[0], rest[1], "--force" in args)
    if args[0] == "play":
        if len(args) != 2:
            sys.exit("dojo: play <block>")
        return play(args[1])
    return check(args[0], args[1:])


if __name__ == "__main__":
    sys.exit(main())
