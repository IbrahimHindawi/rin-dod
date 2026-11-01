# How the course stays memory safe

The fifteen programs here are checked by rin with its safety rules on, which is
the default on the `regions` branch of the compiler. `tools/check.py` runs each
one against the `.expected` beside it, and they also run clean under
AddressSanitizer and UndefinedBehaviorSanitizer
(`python tools/check.py ecs --sanitize`). The guides teach each piece as it comes
up; this page is the whole picture in one place. `main` has the earlier unsafe
version of the course, if you want to compare.

**Part 1, entities.** No regions at all: the world stays a value on `main`'s
stack and procs take `*kayan_world`. The details are below.

**Part 2, components.** The world moves into a region, `level: region;`, and
is made whole by `kayan_world_make(r: region level)`: its vecs are
`*vec<T> in level`, its tables are level pointers in a vec so a table pointer
never moves, and every allocating proc takes the region. The type-erased
column, bytes addressed by a size and an alignment, is the one thing that is
unsafe by nature; it is two `unsafe { }` blocks, the aligned grow and the typed
`[]T` view over the bytes, and 2.7 adds a third that prints a builtin by its
type name. Everything above them is checked: `kayan_get<T>` returns
`option<*T in level>`, row copies are bounds-checked byte loops, the registry is
`[64]option<*const reflect in permanent>`.

Those blocks follow one rule, and 2.2 teaches it. rin has no private fields, so
an `unsafe` block must not believe a field or an argument unless the value carries
its own bound, as a slice does. So the view checks a column's room against its
slice, tests the alignment, and takes only plain-data types, for which any bytes
are a valid value. Reading the wrong type gives wrong numbers, never a bad pointer.

**Part 3, systems.** The storage gets ready to be called from inside a frame: the
world remembers its region, so `kayan_spawn` no longer takes one, and a system
writes its column slices as region-free borrows that the checker can end. 3.1 has
six `unsafe { }` blocks, and its guide lists them. The frame's memory is
`frame: region in level;`, opened once per frame by `run_frame`; the command
buffer is made inside it, so no command can outlive its frame by construction,
and nothing has to clear it. A system is split into its immutable half, a name and
a proc pointer made by a trusted proc, and its scheduled half with the query and
counters. The context a system gets is a typed `option<*game in level>`, not a
`*void`. By 3.4 kayan has eight `unsafe { }` blocks, and the game has three
`noalias` kernels, each a `proc[unsafe]` called from a one-line `unsafe { }` in its
system. The rest of the game is checked.

The header comment of each file says what its `unsafe` blocks are for.

## What the rules cost

For a reader who wants to see the annotation cost without reading fifteen programs,
Part 1 is the clearest place to look, since it's so small:

  * Output goes through `printfmt("{:5.2}", x)`. `printf` is C's and takes a
    pointer, so safe code can't call it; `printfmt` takes a width and precision,
    so nothing is lost.
  * `get_position` in 1.3 and 1.4 returns `option<*vec2>`, because it returns
    null for a dead handle. Its callers test the result: `aim` in 1.3 has a
    three-line `if (!p) { ...; return; }` for the case where the fallback target
    is dead too, and 1.4's `main` prints the position inside `if (at) { }`.

Nothing else. The world stays a value on `main`'s stack, procs take it as
`*kayan_world`, and `get_position` hands back a pointer into it with no region
written anywhere: a pointer returned without a region points into what the
caller passed, so the caller treats it as a borrow of the world. No `region`
block, no `in R`, no `unsafe { }`, no `[unsafe]`.

So the entity index as this course builds it, with handles, generations and a
slot map over packed rows, is memory safe at compile time at the cost of one
`option` on one return type and a format string syntax.
