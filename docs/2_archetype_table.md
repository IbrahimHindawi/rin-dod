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

## The table lives in a region

The table and its columns come from the region `level`, and their types say so:

    spark_table_create: proc(r: region level, capacity: u64) -> *spark_table in level = {
        return new<spark_table>(r, {
            .capacity = capacity,
            .numbers = new_slice<u32>(r, capacity),
            .positions = new_slice<vec2>(r, capacity),
            .velocities = new_slice<vec2>(r, capacity),
            .lives = new_slice<f32>(r, capacity),
        });
    }

`main` opens `level` and holds the result as `*spark_table in level`, so the
checker will not let it be kept past the region's end. Every column here is typed,
so no byte is ever reinterpreted, and the only `unsafe` in the file is for
`noalias`, below.

## Removing while iterating

`expire_system` walks the rows backwards. When it removes row `i`, the row
that moves in comes from the end, and the end has already been tested. A
forward loop would have to stay on `i` after a removal, and it is easy to get
wrong. Lesson 6 removes the question entirely by not removing anything during
a loop.

## Systems take slices

`move_system(positions: noalias []vec2, velocities: []const vec2, dt)` gets
the rows in use, `sparks*.positions[0..sparks*.count]`, and knows nothing about
tables. `[]const` says it only reads velocities. Each `positions[i]` is bounds
checked, in every build, against the count rather than the capacity, so a system
that runs past the live rows stops with a message instead of reading stale data.

`noalias` says that for the call, nothing else reaches the memory `positions`
covers. Only the column the system writes needs it: a promise on the written
column already rules out a write landing in the column being read. Without
it, clang `-O2` on Linux vectorized this loop behind a run-time check that the
two columns are apart, and so did gcc `-O3` with the bounds checks compiled out.
With it, neither checks. A build with the bounds checks in checks the promise
instead, once per call.

The promise is one the checker cannot keep, so the two kernels are
`proc[unsafe]`, and `main` calls each from inside `unsafe { }`:

    unsafe { move_system(sparks*.positions[0..sparks*.count], sparks*.velocities[0..sparks*.count], dt); }

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

The bounds check does not cost this loop anything: `lives.length` is already the
loop's bound, so the compiler drops it. `move_system`, with two lengths to check,
keeps its vector loop on clang too, as lesson 1 explains; clang-cl does not
vectorize it at all without `noalias`, and gcc `-O3` does not with the checks in.

The rule that holds on every compiler: `noalias` on every slice a loop writes,
even when it is the only one.

`lives` is a plain run of floats. `positions` and `velocities` are `vec2`, x and
y side by side, but both get the same math, so the compiler keeps the pairs
together and `move_system`'s vector loop needs no shuffles at all: four `vec2`s a
pass in two registers. A `vec3`, which does not divide into a register, is
another matter. Lesson 1 measures what that costs.

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
4. Make the table grow instead of reporting `full`: `spark_spawn` now needs the
   region, `r: region level`, to `new_slice` double the capacity, and a plain loop
   copies every column across. It is all checked, since the columns are typed.
   Lesson 4's `kayan_table_grow` is the same idea over columns of bytes.
