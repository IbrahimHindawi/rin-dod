"""Build every lesson, run it, and compare what it prints with its .expected file.

    python tools/check.py               every lesson
    python tools/check.py archetype     only lessons whose path contains "archetype"
    python tools/check.py --bless       rewrite the .expected files from this run
    python tools/check.py --sanitize    also build with AddressSanitizer and UBSan

A lesson passes only if all four steps are clean:

  1. `rin compile` prints nothing but its "generated" line,
  2. the C compiler reports no warnings (-Wall -Wextra -Werror),
  3. the program exits with 0,
  4. its output matches the .expected file beside it, byte for byte.

The lessons are the list in build.rin, so there is one list to keep. The
dojo's playgrounds are in it too. Each dojo block is also checked on its own
(`python tools/check.py dojo` for only them): its solution.rin, a whole program
that imports the harness, must build and print its harness.expected;
level1.rin must build and fail, since it has a gap; level2.rin must build.

rin is found through RIN, then RIN_HOME, then PATH; its std is the folder beside
it, as `rin build` assumes. The C compiler is CC, or clang.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "check"


def find_rin() -> Path:
    names = ["rin.exe", "rin"] if os.name == "nt" else ["rin", "rin.exe"]
    if os.environ.get("RIN"):
        return Path(os.environ["RIN"])
    if os.environ.get("RIN_HOME"):
        for name in names:
            candidate = Path(os.environ["RIN_HOME"]) / name
            if candidate.exists():
                return candidate
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    sys.exit("check: rin not found; set RIN or RIN_HOME, or put rin on PATH")


def list_from_build_rin(name: str) -> list[str] | None:
    text = (ROOT / "build.rin").read_text(encoding="utf-8")
    block = re.search(rf"^{name}:[^{{]*\{{(.*?)\}}", text, re.S | re.M)
    if not block:
        return None
    return re.findall(r'"([^"]+)"', block.group(1))


def lessons_from_build_rin() -> list[Path]:
    entries = list_from_build_rin("build_entries")
    if entries is None:
        sys.exit("check: no build_entries in build.rin")
    return [ROOT / entry for entry in entries]


def run(cmd: list[str], cwd: Path = ROOT,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=300)


# On Windows a sanitized program loads clang_rt.asan_dynamic-x86_64.dll when it
# starts, and exits with 0xC0000135 before main if the DLL is not on PATH. It
# lives in the C compiler's own resource directory, so ask the compiler.
def sanitizer_env(cc: str) -> dict[str, str] | None:
    if os.name != "nt":
        return None
    resource = run([cc, "-print-resource-dir"]).stdout.strip()
    runtime = Path(resource) / "lib" / "windows"
    if not runtime.is_dir():
        return None
    env = dict(os.environ)
    env["PATH"] = str(runtime) + os.pathsep + env.get("PATH", "")
    return env


def check(rin: Path, cc: str, lesson: Path, bless: bool, sanitize: bool,
          env: dict[str, str] | None) -> tuple[bool, str]:
    stem = lesson.stem
    work = OUT / stem
    work.mkdir(parents=True, exist_ok=True)
    c_path = work / f"{stem}.c"
    exe = work / (f"{stem}.exe" if os.name == "nt" else stem)

    translate = run([str(rin), "compile", str(lesson), "-o", str(c_path),
                     "--header", str(work / f"{stem}.h")])
    noise = [line for line in translate.stdout.splitlines()
             if line.strip() and not line.startswith("rin: generated")]
    if translate.returncode != 0 or noise:
        return False, "rin compile:\n" + translate.stdout

    flags = ["-std=c11", "-g", "-Wall", "-Wextra", "-Werror"]
    flags += [f"-D{define}" for define in list_from_build_rin("build_defines") or []]
    if sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
    includes = ["-I", str(rin.parent), "-I", str(rin.parent / "std")]
    libs = [] if os.name == "nt" else ["-lm"]
    build = run([cc, *flags, *includes, str(c_path), "-o", str(exe), *libs])
    if build.returncode != 0 or build.stdout.strip():
        return False, f"{cc}:\n" + build.stdout

    ran = run([str(exe)], env=env)
    if ran.returncode != 0:
        return False, f"exit {ran.returncode}:\n{ran.stdout}"

    actual = ran.stdout.replace("\r\n", "\n")
    expected_path = lesson.with_suffix(".expected")
    if bless:
        expected_path.write_text(actual, encoding="utf-8", newline="\n")
        return True, "blessed"
    if not expected_path.exists():
        return False, f"no {expected_path.name}; run with --bless after reading the output:\n{actual}"
    expected = expected_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if actual != expected:
        got, want = actual.splitlines(), expected.splitlines()
        for i in range(max(len(got), len(want))):
            g = got[i] if i < len(got) else "<missing>"
            w = want[i] if i < len(want) else "<missing>"
            if g != w:
                return False, f"line {i + 1}\n  got:  {g}\n  want: {w}"
    return True, ""


# ---------------------------------------------------------------- the dojo

DOJO = ROOT / "dojo"
# A kata in progress is full of unused parameters and locals.
KATA_QUIET = ["-Wno-unused-parameter", "-Wno-unused-variable", "-Wno-unused-but-set-variable",
              "-Wno-unused-function"]


def dojo_blocks() -> list[Path]:
    # The blocks, then the same blocks in the safe subset under dojo/safe.
    roots = [DOJO] + ([DOJO / "safe"] if (DOJO / "safe").is_dir() else [])
    blocks: list[Path] = []
    for root in roots:
        blocks += sorted((p for p in root.iterdir() if p.is_dir() and re.match(r"\d+\.", p.name)),
                         key=lambda p: int(p.name.split(".")[0]))
    return blocks


# A kata file is a whole program: it imports what it uses and the harness,
# which has main, so each of the solution and the levels builds where it is.
def dojo_build(rin: Path, cc: str, block: Path, kata: Path, where: str, sanitize: bool,
               quiet: bool) -> tuple[Path | None, str]:
    folder = OUT / "dojo" / block.name
    folder.mkdir(parents=True, exist_ok=True)
    c_path = folder / f"{where}.c"
    exe = folder / (f"{where}.exe" if os.name == "nt" else where)
    translate = run([str(rin), "compile", str(kata), "-o", str(c_path),
                     "--header", str(folder / f"{where}.h")])
    noise = [line for line in translate.stdout.splitlines()
             if line.strip() and not line.startswith("rin: generated")]
    if translate.returncode != 0 or noise:
        return None, "rin compile:\n" + translate.stdout
    flags = ["-std=c11", "-g", "-Wall", "-Wextra", "-Werror", *(KATA_QUIET if quiet else [])]
    flags += [f"-D{define}" for define in list_from_build_rin("build_defines") or []]
    if sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
    includes = ["-I", str(rin.parent), "-I", str(rin.parent / "std")]
    libs = [] if os.name == "nt" else ["-lm"]
    build = run([cc, *flags, *includes, str(c_path), "-o", str(exe), *libs])
    if build.returncode != 0 or build.stdout.strip():
        return None, f"{cc}:\n" + build.stdout
    return exe, ""


def check_dojo(rin: Path, cc: str, block: Path, bless: bool, sanitize: bool,
               env: dict[str, str] | None) -> tuple[bool, str]:
    exe, err = dojo_build(rin, cc, block, block / "solution.rin", "solution", sanitize, False)
    if not exe:
        return False, "solution.rin, " + err
    ran = run([str(exe)], env=env)
    if ran.returncode != 0:
        return False, f"the solution fails its harness, exit {ran.returncode}:\n{ran.stdout}"
    actual = ran.stdout.replace("\r\n", "\n")
    expected_path = block / "harness.expected"
    detail = ""
    if bless:
        expected_path.write_text(actual, encoding="utf-8", newline="\n")
        detail = "blessed"
    elif not expected_path.exists():
        return False, f"no harness.expected; run with --bless after reading the output:\n{actual}"
    elif actual != expected_path.read_text(encoding="utf-8").replace("\r\n", "\n"):
        return False, "the harness's output with the solution is not harness.expected"
    for level in (1, 2):
        exe, err = dojo_build(rin, cc, block, block / f"level{level}.rin", f"level{level}", sanitize, True)
        if not exe:
            return False, f"level{level}.rin, " + err
        if level == 1 and run([str(exe)], env=env).returncode == 0:
            return False, "level 1 passes the harness as given; its gap is not a gap"
    return True, detail


def main() -> int:
    args = sys.argv[1:]
    bless = "--bless" in args
    sanitize = "--sanitize" in args
    filters = [a for a in args if not a.startswith("--")]

    rin = find_rin()
    cc = os.environ.get("CC", "clang")
    lessons = [l for l in lessons_from_build_rin()
               if not filters or any(f in str(l) for f in filters)]

    env = sanitizer_env(cc) if sanitize else None

    failed = 0
    for lesson in lessons:
        ok, detail = check(rin, cc, lesson, bless, sanitize, env)
        name = lesson.relative_to(ROOT).as_posix()
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if ok and detail else ""))
        if not ok:
            failed += 1
            print("     " + detail.replace("\n", "\n     "))
    print(f"{len(lessons) - failed} of {len(lessons)} passed")

    blocks = [b for b in dojo_blocks()
              if not filters or any(f in b.relative_to(ROOT).as_posix() for f in filters)]
    dojo_failed = 0
    for block in blocks:
        ok, detail = check_dojo(rin, cc, block, bless, sanitize, env)
        print(f"{'ok  ' if ok else 'FAIL'} {block.relative_to(ROOT).as_posix()}, the solution and the levels"
              + (f"  ({detail})" if ok and detail else ""))
        if not ok:
            dojo_failed += 1
            print("     " + detail.replace("\n", "\n     "))
    if blocks:
        print(f"{len(blocks) - dojo_failed} of {len(blocks)} dojo blocks passed")
    return 1 if failed or dojo_failed else 0


if __name__ == "__main__":
    sys.exit(main())
