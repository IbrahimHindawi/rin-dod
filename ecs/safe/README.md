# The entity lessons, in rin's safe subset

The four programs here are `ecs/src/1.entities/*` checked by rin with its
safety rules on (the default on the `regions` branch of the compiler; the rest
of the course still needs `--unsafe`). They print the same `.expected` files as
the originals, so `tools/check.py` runs them beside the originals.

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
