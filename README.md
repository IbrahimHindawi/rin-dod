# rin-dod

Data-oriented programming in [rin](https://github.com/IbrahimHindawi/rin), in
six lessons: from one array of structs to a small archetype entity component
system and a game that runs on it. The ECS is a rework of
[kayan](https://github.com/IbrahimHindawi/kayan): its core idea is kept and
its rough edges are not. [docs/0_from_kayan.md](docs/0_from_kayan.md) says
which is which.

Every lesson is a standalone program in its own folder, laid out like
[rin-dx11](https://github.com/IbrahimHindawi/rin-dx11): one source file that
opens with what it teaches, and the output it must print beside it.

## Layout

    src/
      1.aos_vs_soa/
        aos_vs_soa.rin          the program
        aos_vs_soa.expected     what it prints
      ...
    includes/
      kayan.rin                 lesson 4's world, used by lessons 5 and 6
    docs/                       background and exercises, one guide a lesson
    website/
      index.html                every lesson as one page: guide, code, output
      template.html             its layout and styles
    tools/
      check.py                  build, run and compare every lesson
      site.py                   rebuild website/index.html from the repo
    build.rin                   the lesson list, for `rin build`

Lessons 1 to 3 are self-contained. Lesson 4 builds the world in
`includes/kayan.rin`, and lessons 5 and 6 import it unchanged.

## Build and run

Needs the rin compiler with `noalias` (rin `e67175d` or later; `rin.exe` from
`rin-windows-x64`, through `RIN_HOME` or `PATH`), CMake, Ninja, clang-cl and
the Windows SDK.

    rin build
    build\cmake\aos_vs_soa.exe

`python tools/check.py` builds every lesson with clang and warnings as
errors, runs it, and compares what it prints with its `.expected` file.
`--sanitize` adds AddressSanitizer and UBSan, `--bless` rewrites the expected
files after a deliberate change, and a word filters the lessons:

    python tools/check.py
    python tools/check.py kayan --sanitize

The checker also works on Linux. There it relaxes `-Wformat` only: rin's
`printfmt` and std `print` write `%llu` for `u64`, which is `unsigned long`
on 64-bit Linux.

## Reading it in a browser

Open `website/index.html`. It has every lesson's guide, its source with line
numbers, and the output it must print, with an index on the left. It is
generated from the files in this repository, so after changing a lesson or a
guide run `python tools/site.py` to bring it up to date.

## How to read it

Read each lesson's `.rin` file from the top. It opens with the problem it
solves, and the code follows in the order it runs. Then run it and read the
output against the code: every lesson prints what it does, step by step. The
guides in `docs/` give background that does not fit in a file header, and end
with exercises.

## The lessons

| | lesson | about |
|---|---|---|
| 0 | [from kayan](docs/0_from_kayan.md) | what was kept, what changed, and why |
| 1 | [aos vs soa](docs/1_aos_vs_soa.md) | the same particles in three layouts, what a loop fetches, and what SIMD needs |
| 2 | [archetype table](docs/2_archetype_table.md) | one table: columns, rows, spawn, swap-remove, systems over slices |
| 3 | [many archetypes](docs/3_many_archetypes.md) | one table type for every archetype: ids, signatures, queries |
| 4 | [entity handles](docs/4_entity_handles.md) | generational handles, slots, moving between archetypes |
| 5 | [inspector](docs/5_inspector.md) | printing and editing any entity from reflection records |
| 6 | [kayan](docs/6_kayan.md) | a small game, and deferring structural changes to a command buffer |

## License

MIT. See [LICENSE](LICENSE).
