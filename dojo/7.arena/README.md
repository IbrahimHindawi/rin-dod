# 7. An arena

`dojo/safe/7.arena/play_arena.rin`

**This is the safe-subset port, and it is the one block where the kata itself
changed.** The original `bump` was an arena over bytes it was handed, and
`bump_push` returned their address, a `^u8`, which safe code cannot hand out:
the checker has no region for it. Here the region *is* the arena. `bump_make`
takes `r: region level` and gets its bytes from it, `new_slice<u8>(r,
capacity)`, and `bump_push` returns an `option<u64>`: the **offset** of the
bytes, or none when they would end past the last byte. The caller writes and
reads through `bump_bytes(b)[offset]`, a slice the checker bounds-checks, so a
push that lands past the end is caught as it happens. That is exactly what
rust-dod's kata does, and the rin notes below about addresses are what the
original did; the rest of this page, the invariant, the levels and the
failures, is unchanged. The playground keeps its 64 bytes inside the struct
and hands out offsets the same way.

Most of what a frame allocates dies with the frame: commands, scratch lists,
text for the screen. An **arena** hands all of it out of one buffer and keeps
one number, how much of the buffer is used. A push rounds that number up to
the alignment asked for, hands out the address there, and moves the number
past the new bytes. Nothing is freed on its own. A **mark** remembers the
number, a **rewind** puts it back, and a **clear** sets it to 0: everything
pushed since goes at once, in one store, with no list of what to free.

    push(4, 4) with 1 used:   round 1 up to 4, hand out base + 4, used is now 8

For an `align` that is a power of two, rounding up is
`(used + align - 1) & ~(align - 1)`: adding `align - 1` reaches the next
multiple unless `used` is one already, and the mask drops what's past it.

**The invariant:** every push not yet let go of starts at a multiple of its
alignment, ends at or before `used`, and stops before the next push starts;
`used` never passes the end of the buffer.

In the course: everywhere. Every lesson allocates from a `memops_arena`, from
[2.2](../../ecs/docs/2.2_columns.md)'s columns on, and never frees anything
on its own. [3.3](../../ecs/docs/3.3_commands.md) adds a second arena for one
frame's commands, cleared after they're applied, and kayan does the same in
[6](../../docs/6_kayan.md). This block is that arena, small enough to write in
a few minutes.

## Watch it: the playground

    python tools/dojo.py play arena

It pushes things of different sizes and alignments into a 64-byte buffer,
rewinds, fills it to the last byte, and clears it. After each step it draws
the buffer, 16 bytes to a group: a letter for each byte of a push, `-` for
padding, `.` for free.

```
push b: a u32 count, 4 bytes, align 4
    offset 4, used 8 of 64: 3 bytes of padding first
    a---bbbb........|................|................|................
...
rewind to the mark: e and f are gone at once
    a---bbbbcccccccc|dddddddddddddddd|................|................
```

Each push is filled with its letter, and `verify` checks after every step
that each push is aligned, inside `used`, clear of the next, and still holds
its letter. Step through it: break on `bump_push` and watch `used`. The
buffer is a `struct[align(16)]`, so an offset that is a multiple of 16 is an
address that is one too.

Then flip the switch at the top, `align_offsets`, to `0` and run it again.
Pushes are handed out at `used` as it is, packed with no padding, and the
`u32`, the `u64` and the 16-byte vector land at offsets 1, 5 and 13:

```
    verify: b is at offset 1, not a multiple of 4: its address isn't aligned
```

The playground only ever writes bytes, with `memset`, so nothing breaks yet.
Read a `u32` through a `*u32` from there, though, and it's undefined
behaviour in C, so in rin: on x86 it usually works, slower when it straddles
two cache lines; an aligned SIMD load faults; and the optimiser is allowed to
assume it never happens. `--sanitize` reports it, as UBSan's "misaligned
address".

## Do reps: the kata

You write `bump`, an arena over bytes it's given. It isn't called `arena`,
since the one every lesson uses already has that name: `memops_arena`.

```rin
bump: struct = {
    base: ^u8;
    capacity: u64;
    // Bytes before `used` are handed out; bytes after it are free.
    used: u64;
}
```

Its one proc with an idea in it:

```rin
bump_push: proc(b: *bump, size: u64, align: u64) -> ^u8 = {
```

the address of `size` bytes at an offset from `base` that is a multiple of
`align`, or null, changing nothing, when they would end past the last byte.
Plus `bump_init(b, base, capacity)`, `bump_used`, `bump_capacity`,
`bump_mark`, `bump_rewind(b, mark)` and `bump_clear`.

| level | you write | target |
|---|---|---|
| 1 | `bump_push`, in an otherwise finished file | 2:00 |
| 2 | every proc body; the fields and signatures are given | 6:00 |
| 3 | the whole file, from a blank page | 8:00 |

    python tools/dojo.py start arena 2
    python tools/dojo.py arena
    python tools/dojo.py arena --sanitize     the same with AddressSanitizer and UBSan

The harness runs the playground's steps as a scenario, then 20,000 random
pushes, marks, rewinds and clears on a 256-byte buffer, against a model that
keeps the used count and every push not yet let go of. Pushes are 1 to 24
bytes at alignments 1 to 16, with some sized to end exactly at the last byte
and some one byte past it. Each push is filled with a pattern through the
address it gave, and read back later, so a push that lands on another shows.
The seeds give the same runs as rust-dod's dojo.

**rin notes.** `bump_push` hands out an address, as `memops_arena_push` does.
rust-dod's kata hands out an offset instead, and `bytes_mut(offset, len)` to
write through: a slice from `push` would borrow the whole arena for as long as
it was kept, and the arena couldn't push again until it was gone. rin lets you
keep the address, and keep it past a rewind too, which is the arena's one way
to go wrong: an address from before a rewind or a clear points at bytes the
next push will hand out again.

**Level 4, variations.** The same harness, different insides:

- **Align the address, not the offset**: round `cast(base, usize) + used` up,
  and subtract `base` again. `memops_arena` does it this way. The answers are
  the same for the harness's buffers, which start 16-aligned; what changes for
  a buffer that doesn't?
- **`bump_push_zero`**: the same, with the bytes zeroed. Rewind, push again,
  and read the bytes before zeroing: what's there? (Not checked by the
  harness; write your own test.)
- **Temporary scopes**: `bump_temp_begin(b)` returns a record of the mark and
  `bump_temp_end(t)` rewinds to it, like `memops_arena_temp_begin` and
  `_end`. What goes wrong if two scopes end out of order? (Not checked by the
  harness; write your own test.)

## When it fails

    FAIL in the scenario: push 4 bytes, align 4: 3 bytes of padding first gave 1, it should give 4

No rounding up at all: the offset is `used` as it is. The fuzz run is what
finds the rest:

    FAIL at operation 29 (seed 1): push(12, 2) gave offset 59, which isn't a multiple of 2
        debug it: build/dojo/arena/harness --seed 1 --stop 29
        with a breakpoint on dojo_stop_here, which runs just before that operation

That one rounds every alignment but 2, which the scenario never asks for. Run
the harness under your debugger with those arguments and a breakpoint on
`dojo_stop_here`, which runs just before that operation, and step into
`bump_push`.

If the harness crashes instead, on a write through an address outside the
buffer say, the runner runs it again with `--trace 1` and prints the
operation that was running. `--sanitize` stops on the bad write itself.
