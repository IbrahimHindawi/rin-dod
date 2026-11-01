# 7. An arena

`dojo/7.arena/play_arena.rin`

Most of what a frame allocates dies with the frame: commands, scratch lists,
text for the screen. An **arena** hands all of it out of one buffer and keeps
one number, how much of the buffer is used. A push rounds that number up to
the alignment asked for, hands out the offset there, and moves the number
past the new bytes. Nothing is freed on its own. A **mark** remembers the
number, a **rewind** puts it back, and a **clear** sets it to 0: everything
pushed since goes at once, in one store, with no list of what to free.

    push(4, 4) with 1 used:   round 1 up to 4, hand out offset 4, used is now 8

For an `align` that is a power of two, rounding up is
`(used + align - 1) & ~(align - 1)`: adding `align - 1` reaches the next
multiple unless `used` is one already, and the mask drops what's past it.

**The invariant:** every push not yet let go of starts at a multiple of its
alignment, ends at or before `used`, and stops before the next push starts;
`used` never passes the end of the buffer.

In the course: everywhere. A region is a `memops_arena` the checker can see.
Every lesson from [2.2](../../ecs/docs/2.2_columns.md)'s columns on allocates
from the region `level`, and never frees anything on its own.
[3.3](../../ecs/docs/3.3_commands.md) adds a second, `frame: region in
level;`, for one frame's commands, let go when it ends, and kayan does the
same in [6](../../docs/6_kayan.md). This block is the arena inside a region,
small enough to write in a few minutes.

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

Each push is filled with its letter, written through `b*.bytes[offset]`, and
`verify` checks after every step that each push is aligned, inside `used`, clear
of the next, and still holds its letter. Step through it: break on `bump_push`
and watch `used`. The playground keeps its 64 bytes inside the struct.

Then flip the switch at the top, `align_offsets`, to `0` and run it again.
Pushes are handed out at `used` as it is, packed with no padding, and the
`u32`, the `u64` and the 16-byte vector land at offsets 1, 5 and 13:

```
    verify: b is at offset 1, not a multiple of 4: a 4-byte thing can't be read from there
```

The playground only ever writes bytes, so nothing breaks yet, and safe code
can't do anything else: reading a `u32` out of bytes is a cast to a pointer,
which takes `unsafe { }`. (Block 11 copies the bytes into a local with
`memcpy` instead, which has no alignment to get wrong.) Do the cast from
there, though, and it's undefined behaviour in C, so in rin: on x86 it usually
works, slower when it straddles two cache lines; an aligned SIMD load faults;
and the optimiser is allowed to assume it never happens. `--sanitize` reports
it, as UBSan's "misaligned address".

## Do reps: the kata

You write `bump`, an arena over bytes it gets from the region `level`. It isn't
called `arena`, since the one every lesson uses already has that name:
`memops_arena`.

```rin
bump: struct = {
    bytes: []u8 in level;
    // Bytes before `used` are handed out; bytes after it are free.
    used: u64;
}
```

Its one proc with an idea in it:

```rin
bump_push: proc(b: *bump, size: u64, align: u64) -> option<u64> = {
```

the **offset** of `size` bytes, a multiple of `align`, or none, changing
nothing, when they would end past the last byte. It can't be an address: a
`^u8` has no region, so safe code can't hand one out. The caller writes and
reads through `bump_bytes(b)[offset]`, a slice the checker bounds-checks. Plus
`bump_make(r, capacity)`, which gets its bytes with `new_slice<u8>(r,
capacity)`, `bump_bytes`, which returns a `[]u8 in level`, `bump_used`,
`bump_capacity`, `bump_mark`, `bump_rewind(b, mark)` and `bump_clear`.

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
and some one byte past it. Each push is filled with a pattern at the offset it
gave, and read back later, so a push that lands on another shows.
The seeds give the same runs as rust-dod's dojo.

**rin notes.** `memops_arena_push` hands out an address, and safe code never
calls it: it is what a region is built on, behind `new<T>` and `new_slice<T>`.
rust-dod's kata hands out an offset too, for its own reason: a slice from `push`
would borrow the whole arena for as long as it was kept, and the arena couldn't
push again until it was gone. An offset can still be kept past a rewind, which
is the arena's one way to go wrong: an offset from before a rewind or a clear
names bytes the next push will hand out again. In safe code that gets you the
wrong bytes, and never memory outside the slice.

**Level 4, variations.** The same harness, different insides:

- **Align the address, not the offset**, which fails on purpose: round the
  address of byte `used` up, and subtract the address of byte 0 again. That
  takes a small `unsafe { }`, `cast(b*.bytes[0]&, usize)`, since safe code
  can't turn a pointer into a number. `memops_arena` does it this way.
  `new_slice<u8>` aligns its bytes only as a `u8` needs, so unless they happen
  to start on a multiple of 16, the harness soon finds an offset that isn't a
  multiple of its alignment. Which one is right, and what would `bump_make`
  have to do for both to agree?
- **`bump_push_zero`**: the same, with the bytes zeroed. Rewind, push again,
  and read the bytes before zeroing: what's there? (Not checked by the
  harness; write your own test.)
- **Temporary scopes**: `bump_temp_begin(b)` returns a record of the mark and
  `bump_temp_end(t)` rewinds to it, like `memops_arena_temp_begin` and `_end`.
  The record keeps `b`, so `bump_temp_begin` takes a `*bump in level`, and the
  field is one too. What goes wrong if two scopes end out of order? (Not
  checked by the harness; write your own test.)

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

If the harness crashes instead, on an index past the end of the bytes say,
`index 257 out of bounds (length 256)`, the runner runs it again with
`--trace 1` and prints the operation that was running.
