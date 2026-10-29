# The dojo

An ECS is mostly a few small building blocks put together. None of them is
specific to an ECS: a renderer's texture handles are a slot map, a particle
system is swap-remove over packed arrays, undo and network replication are
command buffers. The course meets each block for the first time in the middle
of building something bigger, which is why its chapters can feel dense. The
dojo takes the blocks out and gives each one two halves:

- **a playground**, to understand it: a small program that runs the block
  step by step and draws its insides, with one switch at the top that breaks
  it the way it most often breaks. Step through it in a debugger, flip the
  switch, watch what goes wrong.
- **a kata**, to own it: you write the block yourself, and a harness checks
  it. Reading and stepping through code feels like learning, but writing it
  from a blank page, getting it wrong, and doing it again a few days later is
  what makes it yours.

| | block | what it is | in the course |
|---|---|---|---|
| 1 | [free list and generations](1.free_list/README.md) | handles that are safe to keep after what they name is gone | 1.2, 1.3 |
| 2 | [swap-remove and the back-reference](2.swap_remove/README.md) | values packed with no holes, found by id: a sparse set | 1.4, 2.3, 2.6 |
| 3 | [the slot map](3.slot_map/README.md) | 1 and 2 together: handles into packed values | 1.4, 2.4 |
| 4 | [a type-erased column](4.column/README.md) | an array of any type as bytes, viewed as a typed slice | 2.2, 2.3, 2.5 |
| 5 | [a command buffer](5.commands/README.md) | structural changes recorded now and applied later | 3.3, 3.4 |
| 6 | [bitsets](6.bitset/README.md) | a set of components in a u64: has, all of, none of | 2.1, 3.1 |
| 7 | [an arena](7.arena/README.md) | push, push, clear: memory for things that die together | every chapter |
| 8 | [index, not pointer](8.index/README.md) | links that stay right when their storage moves | 2.2, 2.4, 2.5 |
| 9 | [interning](9.interning/README.md) | find or make, by key: a hash table that hands out dense ids | 2.4 |
| 10 | [memoized edges](10.edges/README.md) | a slow lookup done once, then remembered on the edge | 2.6 |
| 11 | [a reflection walk](11.reflect/README.md) | reading, writing and comparing any value through its type's record | 2.7 |
| 12 | [a watermark](12.watermark/README.md) | looking only at what was added since last time | 3.1 |
| 13 | [a dispatch table](13.dispatch/README.md) | behaviour as data: the schedule as a list of functions | 3.2 |

Do 1 to 5 in order the first time: 3 is 1 and 2 put together, and 5 applies
its commands to something like 3. 6 to 13 come in the order the course meets
them and stand on their own, except that 9, 10 and 12 work on 6's
signatures. Any of them can come before the course, alongside it, or after
it.

## Each block

    dojo/3.slot_map/
      README.md              the block, its invariant, the levels, the variations
      play_slot_map.rin      the playground
      harness.rin            fixed: a scenario, then a fuzz run against a model
      level1.rin ... 3.rin   where a kata starts
      solution.rin           the reference; don't peek
      kata.rin               yours: made by `start`, ignored by git

The harness doesn't know how your kata works, only what it must do. First it
runs a short scenario, the playground's steps, and prints each as it passes.
Then it runs 20,000 random operations from a seed against a simple model of
the right answers, and checks after each one. A failure says which operation,
which seed, and how to stop just before it in a debugger.

**Levels**, so the reps get harder:

1. **One function** in an otherwise finished file: the one with the idea in
   it, usually the one people forget.
2. **Every function body**, with the fields and signatures given.
3. **A blank page**, with only a list of what the harness calls.
4. **Variations**: the same harness, different insides, listed in each
   block's README.

Each README gives a target time for levels 1 to 3.

## Watching a playground

    python tools/dojo.py play slot_map

A playground runs one scenario, one operation per line of `main`, and prints
what changed after each, so it works without a debugger. In one, put a
breakpoint on a line of `main` and step over the operations. Where the block
has slots there are only a few of them, in fixed arrays, so the watch window
shows the whole state. From block 6 on, a `verify` proc runs after every
operation, checks the block's invariant, and says what broke; a breakpoint
inside its failure branch stops at the first operation that breaks it.

The switch is a global `b32`, read each time it's used, so besides editing it
and running again, you can flip it mid-run: stop where the playground's
header says, set it to 0 in the watch window, and continue. rin writes C, and
the global keeps its name, so in gdb:

    (gdb) break handles_free
    (gdb) run
    (gdb) set var bump_on_free = 0
    (gdb) continue

## Doing reps

    python tools/dojo.py                      the blocks, your reps, and what is due
    python tools/dojo.py play slot_map        the playground
    python tools/dojo.py start slot_map 2     a fresh kata.rin from level 2; the clock starts
    python tools/dojo.py slot_map             build the harness with your kata.rin and run it

A block can be named by its number, its name or the start of its name: `3`,
`slot_map` and `slot` are the same. While the kata fails, fix it and run it
again. When it passes, the time since `start` goes into `dojo/log.md`, and the
block is due again 1, 3, 7, 14 and then 30 days after each pass.
`python tools/dojo.py` with no arguments says what is due. Spacing reps out is
what makes them stick, much more than doing many in one day.

`start` won't overwrite a kata.rin you've changed unless you add `--force`.
Your log is a plain markdown table; commit it or don't.

**When a kata fails**, the harness says where:

    FAIL at operation 64 (seed 1): row 4 holds 43's value 37043, but get(43) gives 43020
        debug it: build/dojo/swap_remove/harness --seed 1 --stop 64
        with a breakpoint on dojo_stop_here, which runs just before that operation

Run that binary under a debugger with a breakpoint on `dojo_stop_here`. It
stops just before the failing operation, with your structure in the state
that leads to the failure. If the harness crashes instead, on a `vec` index
past the end say, the runner runs it again with `--trace 1` and prints the
operation that was running. `--seed N` reruns a different fuzz run, and
`--sanitize` builds with AddressSanitizer and UBSan, which block 4's column
of raw bytes is exactly what they're for.

## How it's built

Every kata file is a whole program. Yours, the solution and each level import
what they use, then the harness, which has `main`:

    import "std/memops.rin"
    import "std/vec.rin"
    import "std/option.rin"
    import "../dojo.rin"
    import "harness.rin"

So any of them builds on its own, `rin compile dojo/3.slot_map/solution.rin`
for instance, and `rin check` or your editor finds every name it uses. Only
the harness doesn't build alone: it calls the procs the kata defines. A file
imported twice is read once, so the kata and the harness both importing
`dojo.rin` is fine. `dojo/dojo.rin` holds what every harness shares:
`dojo_handle` and `dojo_status`, the run's settings, the random number
generator, and the reporting. The runner builds `kata.rin` the way
`tools/check.py` does, `rin compile` and then the C compiler, with the
warnings for unused parameters and locals off, since a kata in progress is
full of them.

`python tools/check.py dojo` keeps the dojo honest: every solution must build
on its own, pass its harness and print its `harness.expected`, level 1 must fail
(its gap must be a gap), level 2 must compile, and the playgrounds must print
their `.expected`. The harnesses were also checked against broken solutions,
the mistakes each block is about, and catch each one.

The same dojo exists in Rust, in [rust-dod](https://github.com/IbrahimHindawi/rust-dod).
The random number generator is the same, so a seed is the same run in both,
and the playgrounds print the same thing, except where block 4's column gets
its memory: an arena in rin, a Vec in Rust. The katas differ where the
languages do: block 7's arena hands out offsets in Rust and addresses in rin,
and in block 8 only rin can keep a pointer across a move, so only rin's switch
does; each README says how.
