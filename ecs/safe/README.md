# The ECS course, in rin's safe subset

The fifteen programs here are `ecs/src/*` checked by rin with its safety
rules on, the default on the `regions` branch of the compiler. They print the
same `.expected` files as the originals, so `tools/check.py` runs them beside
the originals, and they run clean under AddressSanitizer and
UndefinedBehaviorSanitizer.

**Part 1, entities.** No regions at all: the world stays a value on `main`'s
stack and procs take `*kayan_world`. What changed is below.

**Part 2, components.** The world moves into a region, `level: region;`, and
is made whole by `kayan_world_make(r: region level)`: its vecs are
`*vec<T> in level`, its tables are level pointers in a vec so a table pointer
never moves, and every allocating proc takes the region. The type-erased
column, bytes addressed by a size and an alignment, is the one thing that is
unsafe by nature; it is two `[trusted]` procs, the aligned grow and the typed
`[]T` view over the bytes, and 2.7 adds a third that prints a builtin by its
type name. Everything above them is checked: `kayan_get<T>` returns `?*T`,
row copies are bounds-checked byte loops, the registry is
`[64]?*const reflect in permanent`.

**Part 3, systems.** The frame arena becomes `frame: region in level;`, opened
once per frame by `run_frame`; the command buffer is made inside it, so no
command can outlive its frame by construction and the old
`memops_arena_clear` is gone. A system is split into its immutable half, a
name and a proc pointer, and its scheduled half with the query and counters;
the `*void` context became a typed `?*game in level`. Ten or eleven trusted
procs per lesson, all in the byte core; the whole game in 3.4 is checked.

The header comment of each file lists its trusted procs and says what each
does.

## Part 1, in detail

What changed, which is the whole annotation cost of this part of the course:

  * `printf("%5.2f", x)` became `printfmt("{:5.2}", x)`. `printf` is C's and
    takes a pointer, so safe code cannot call it; `printfmt` now takes a width
    and precision, so nothing was lost. Every other line of output was already
    `printfmt`.
  * `get_position` in 1.3 and 1.4 returns `?*vec2` instead of `*vec2`, because
    it returns null for a dead handle. Its callers test the result: `aim` in
    1.3 gained a three-line `if (!p) { ...; return; }` for the case where the
    fallback target is dead too, which the original assumed away, and 1.4's
    `main` prints the position inside `if (at) { }`.

Nothing else. The world stays a value on `main`'s stack, procs take it as
`*kayan_world`, and `get_position` hands back a pointer into it with no region
written anywhere: a pointer returned without a region points into what the
caller passed, so the caller treats it as a borrow of the world and may not
keep it past a change to the world. No `region` block, no `in R`, no
`[trusted]`, no `[unsafe]`.

So the entity index as this course builds it, with handles, generations and a
slot map over packed rows, is memory safe at compile time at the cost of two
`?` characters and a format string syntax.
