# 12. A watermark

`dojo/12.watermark/play_watermark.rin`

A query keeps the list of tables it matches, so a system doesn't search for
them every frame. Tables are only ever **added, at the end**, and never
removed. So the query remembers how many tables it has looked at, its
**watermark**, and an update looks only at the tables past it:

    tables   0 P   1 PV   2 PVH  |  3 PVHB   4 H
                                 ^ movers has checked 3: an update looks at 3 and 4

A frame with no new tables costs one comparison, and each query looks at each
table once, ever. It works for anything that only grows at the end: a log
read by several readers, a list of events, the lines of a file being
written.

**The invariant:** a query lists exactly the tables below its watermark that
match, each once, in order, and it has looked at each of them once.

In the course: [3.1](../../ecs/docs/3.1_queries.md) builds the query and its
`checked` count, and [3.2](../../ecs/docs/3.2_systems.md) updates every
system's query at the start of every frame, which is what makes the
watermark matter.

## Watch it: the playground

    python tools/dojo.py play watermark

It makes tables a few at a time, and updates two queries: `movers`, all
{Position Velocity}, and `healthy`, all {Health}, none {Burning}. After each
step it draws the tables, and under them what each query has looked at, with
a `|` at its watermark:

```
update movers: it looks at tables 3 and 4 only
    table     0    1    2    3    4
    has       P    PV   PVH  PVHB H
    movers    -    yes  yes  yes  -    |    checked 5, scanned 5, tables 1 2 3
    healthy   |                             checked 0, scanned 0, tables none
```

`scanned` counts every table an update has looked at. With the watermark it
always equals `checked`. Then `verify` checks both queries against the tables
and prints what's wrong; break inside its `if` to stop when it fires.

Step through it: break on `query_update` and watch `from`, `checked` and
`found`. Then flip the switch at the top, `use_watermark`, to `0`, and run it
again. Every update starts from table 0, and the second update of `movers`,
with nothing new, finds tables 1 and 2 again:

    movers    -    yes  yes  |    checked 3, scanned 6, tables 1 2 1 2
    verify: movers lists tables 1 2 1 2; it should list 1 2
    verify: movers has looked at 6 tables to check 3; each should be looked at once

A system walking that list would run twice over the same entities, and the
work grows with every frame. The switch is a global, read on every update,
so a debugger can flip it mid-run too: stop on `query_update`, set it to 0 in
the watch window, and continue.

## Do reps: the kata

You write `query`:

```rin
query: struct = {
    arena: *memops_arena;
    all: u64;
    none: u64;
    // The tables that match, by index, in the order they were found.
    tables: vec<u32>;
    // The watermark: tables 0 to checked - 1 have been looked at.
    checked: u64;
    // How many tables query_update has looked at, ever. With the watermark,
    // each table once.
    scanned: u64;
}
```

and its update, which is given the world's tables as their signatures:

```rin
query_update: proc(q: *query, signatures: []u64) -> void = {
```

plus `query_init(q, arena, all, none)`, `query_tables` (the matching tables,
in increasing order), `query_checked` and `query_scanned`. A table matches
when its signature has every bit of `all` and no bit of `none`.

| level | you write | target |
|---|---|---|
| 1 | `query_update`, in an otherwise finished file | 2:00 |
| 2 | every proc body; the fields and signatures are given | 5:00 |
| 3 | the whole file, from a blank page | 7:00 |

    python tools/dojo.py start watermark 2
    python tools/dojo.py watermark

The harness runs the playground's steps as a scenario, then 20,000 random
operations: tables made with random signatures, four queries with random
masks updated at random, and now and then one replaced by a new query, which
must start from nothing. A model keeps, for each query, the tables that match
among the ones it has been updated over. After every update the query must
have checked the whole list, list exactly the model's tables, and have
scanned each table once. Some `none` masks have two bits, so "none of these"
and "not all of these" give different answers. The seeds give the same runs
as rust-dod's dojo.

**Level 4, variations.** The same harness, different insides:

- **A while loop, and `scanned` added once**: `scanned` grows by the number
  of new tables, which is known before the loop starts.
- **Push, don't poll**: flecs does the reverse. When the world makes a table,
  it tells every query, and `query_update` has nothing left to do. What does
  the world have to keep, and what happens to a query made after the table?
  (Not checked by the harness; write your own test.)
- **A table that can go away**: the list keeps a tombstone where a removed
  table was, a signature no query matches. What must a query do with a table
  it already lists? (Not checked by the harness.)

## When it fails

The scenario catches the common mistakes first:

    FAIL in the scenario: make tables 3 and 4, update movers: tables gave 1 2 0, it should give 1 2 3

That's a count of the new tables pushed as if it were the table's index: a
loop that counts from 0 over the tables past the watermark has to add
`checked` back. A failure in the fuzz run says where:

    FAIL at operation 27 (seed 1): after query_update, query 1 (all {0 5}, none {0 6}): it lists 1, the model 0; the first difference is at position 0: table 1, where the model has nothing
        debug it: build/dojo/watermark/harness --seed 1 --stop 27
        with a breakpoint on dojo_stop_here, which runs just before that operation

That one tested `none` the way it tested `all`, `(signature & none) != none`,
which is "not every bit of `none`" rather than "no bit of it". It only
differs when `none` has more than one bit. Run the harness under your
debugger with those arguments and a breakpoint on `dojo_stop_here`, then step
into `query_update` and look at the table it lists.
