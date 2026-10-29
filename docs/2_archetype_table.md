# 2. One archetype table

`src/2.archetype_table/archetype_table.rin`

**In the dojo:** [2. swap-remove and the back-reference](../dojo/2.swap_remove/README.md), [4. a type-erased column](../dojo/4.column/README.md), each on its own, to watch and to practise.

Eight sparks in one table with three component columns, `positions`,
`velocities` and `lives`, plus a `numbers` column that exists only so the
output can say which spark is which. Each frame they move, they age, and the
ones that ran out are removed.

## Two rules

**Columns never disagree.** `spark_spawn` and `spark_despawn` are the only
places rows come and go, and each touches every column. A new component
means a new column, one line in each of those two procs, and one more
argument to `spark_spawn`. A call site cannot add a row to some columns and
forget the others.

**Rows are packed.** Systems loop over `0..count` and never test whether a row
is alive. Removing a row moves the last row into the hole:

    spark 0 in row 0 expired; spark 7 moved from row 7 into it

That one copy per column is the whole cost of a despawn, whatever the table's
size. The price is that a row number is not a name for a spark. After that
line, "row 0" means spark 7. Lesson 4 adds names that do not move.

## Removing while iterating

`expire_system` walks the rows backwards. When it removes row `i`, the row
that moves in comes from the end, and the end has already been tested. A
forward loop would have to stay on `i` after a removal, and it is easy to get
wrong. Lesson 6 removes the question entirely by not removing anything during
a loop.

## Systems take slices

`move_system(positions: noalias []vec2, velocities: []const vec2, dt)` gets
the rows in use, `sparks.positions[0..sparks.count]`, and knows nothing about
tables. `[]const` says it only reads velocities. Each `positions[i]` is bounds
checked in Debug, against the count rather than the capacity, so a system that
runs past the live rows stops with a message instead of reading stale data.

`noalias` says that for the call, nothing else reaches the memory `positions`
covers. Only the column the system writes needs it: a promise on the written
column already rules out a write landing in the column being read. Without
it, clang `-O2` and gcc `-O3` both vectorized this loop behind a run-time
check that the two columns are apart. With it, neither checks. A Debug build
checks the promise instead, once per call.

`age_system(lives: noalias []f32, dt)` has one slice, and still takes it.
Windows passes a slice by reference, as a pointer to a copy, and clang-cl does
not use C's type rules to decide what can overlap. So without the promise,
a float written through `lives` might be the slice's own pointer or length.
clang-cl then reads both again after every element and does one float at a
time. With it, the loop is eight floats per pass:

    movups (%rcx,%r8,4), %xmm2         four lives
    movups 0x10(%rcx,%r8,4), %xmm3     four more
    subps  %xmm0, %xmm2                minus dt
    subps  %xmm0, %xmm3
    movups %xmm2, (%rcx,%r8,4)
    movups %xmm3, 0x10(%rcx,%r8,4)

The rule that holds on every compiler: `noalias` on every slice a loop writes,
even when it is the only one.

`lives` is the one column here that is a plain run of floats. `positions` and
`velocities` are `vec2`, x and y side by side, so `move_system`'s vector loop
spends some of its instructions pulling the x's and the y's apart. Lesson 1
measures what that costs.

## Status codes

`spark_spawn` returns `spawn_status`, an `enum[must_use]`: calling it and
ignoring the result is a compile error. That is rin's convention for a
proc that can fail: a status, with the result through an out-parameter. The
ninth spark shows the `full` case.

## Try

1. Rewrite `expire_system` to walk forwards with a plain `for`. The output
   does not change, because no frame here expires a spark together with the
   one in the last row. Change two lives so that one does, and find the spark
   that outlives its life by a frame. Then fix the loop.
2. Delete the line in `spark_despawn` that copies `lives`. What does the
   output show, and how long did it take to notice?
3. Call `spark_spawn` without using its result and read the compiler's error.
   Then discard it on purpose with `_ = spark_spawn(...)`.
4. Make the table grow instead of reporting `full`: allocate double the
   capacity from the arena and copy every column across. Lesson 4's
   `kayan_table_grow` is one answer.
