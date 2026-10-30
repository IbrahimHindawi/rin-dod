# 4. A type-erased column

`dojo/safe/4.column/play_column.rin`

**This is the safe-subset port.** A type-erased column is type erasure
itself: it hands out rows as bytes and reads them back as `T`, which is what
the checker exists to refuse. So the column's core is marked `[trusted]` in
the kata, `column_make`, `column_push_zeroed`, `column_swap_remove`,
`column_row` and `column_slice`, with `column_len` and `column_capacity`
checked, and `column_make` takes the region `level` and keeps it as the
arena its bytes grow in. The harness has two trusted helpers of its own,
`bytes_of` and `slice_address`, to look at a value's bytes and a slice's
address. The rows, the alignment and the swap-remove are unchanged.

A column is one component's rows, kept as bytes. It doesn't know the type it
holds, only how many bytes make a row and how they must be aligned. That is
enough to grow, to zero a new row, and to move the last row into a hole,
which is everything a table does to its columns. The type comes back only at
the edge: a typed view turns the bytes into a `[]T`, for a `T` of the
column's size and alignment.

Two things make it work:

- **Aligned storage.** The bytes come from the arena aligned to the column's
  alignment, so every row of the type lands where that type may live.
- **Growing by a factor.** A full column doubles, so the copies that growing
  costs add up to about one per push, however many rows there are.

**The invariant:** the column holds `count` rows of `size` bytes each, packed
from the start of a block aligned to `align`, with room for `capacity` rows.
A typed view is only handed out for a `T` of exactly `size` bytes, aligned to
exactly `align`. The type must also be plain data, a struct of numbers with
no pointers in it, since a column copies rows as bytes; that part is on you.

In the course: [2.2](../../ecs/docs/2.2_columns.md) builds the column,
[2.3](../../ecs/docs/2.3_tables.md) puts columns in a table, and
[2.5](../../ecs/docs/2.5_typed_access.md) is about what happens to a pointer
into a column that grows.

## Watch it: the playground

    python tools/dojo.py play column

It fills a column of `vec2`s and draws each row's bytes next to the value
they are:

```
push 3 zeroed rows, and write each through the typed view
    capacity 4, 3 rows in use, 32 bytes of storage
    row 0  00 00 80 3f 00 00 00 40   as a vec2 (1, 2)
    row 1  00 00 40 40 00 00 80 40   as a vec2 (3, 4)
```

Then it grows the column, swap-removes from it, and asks for the rows as two
wrong types. Step through it: break on `column_grow` and watch the rows move
to the new block. The old block stays in the arena, unused, so a slice taken
before the grow still points somewhere valid, and anything written through it
is lost without a word.

The switch at the top, `grow_by_doubling`, picks how a full column grows. Set
it to `0`, so the column grows by one row, and run it again. The last line is
the point: the same 1000 pushes copy 1,020 rows when the column doubles, and
499,494 when it grows by one.

```
1000 pushes into a u32 column, growing by doubling
    9 grows, 1020 rows copied to make room
```

## Do reps: the kata

You write `column`. Its bytes come from the arena, aligned to the column's
alignment:

```rin
        data: ^u8 = cast(memops_arena_push_zero(c*.arena, c*.size * capacity, c*.align), ^u8);
```

and the typed view is a generic proc that checks the type before it casts:

```rin
column_slice: proc<T>(c: *column) -> []T = {
```

plus `column_init(c, arena, size, align)`, `column_len`, `column_capacity`,
`column_push_zeroed` (a zeroed row at the end, and its row number),
`column_swap_remove(c, row)`, and `column_row(c, row)`, a row's bytes as a
`[]u8`.

| level | you write | target |
|---|---|---|
| 1 | `column_slice`, the typed view, in an otherwise finished file | 3:00 |
| 2 | every proc body; the fields and signatures are given | 15:00 |
| 3 | the whole file, from a blank page | 20:00 |

    python tools/dojo.py start column 2         kata.rin from level 2, and the clock starts
    python tools/dojo.py column                 your kata.rin against the harness
    python tools/dojo.py column --sanitize      the same with AddressSanitizer and UBSan

The harness first runs a short scenario: three `vec3`s written through
`column_slice` and read back as bytes, a swap-remove, a column aligned to 16,
and a column of tags, zero-byte rows. Then it runs 20,000 random pushes,
writes and swap-removes, shared between four row types: 3 bytes aligned to 1,
a `u32`, a 12-byte `vec3`, and a 16-byte `vec4` aligned to 16. Each is
checked against a `vec` of that type, through `column_slice` and through
`column_row`, along with the alignment of every view, and that a full column
grows by at least half. The seeds give the same runs as rust-dod's dojo.

`--sanitize` is worth the wait here. A row copied one byte too far, or a
`memcpy` from a block that was never allocated, often works on your machine.
AddressSanitizer and UBSan don't let it happen by luck. (They need the C
compiler's sanitizer runtime; with clang that may be missing, so try
`CC=gcc`.)

What the harness can't check is a refusal: a column read as the wrong type
should stop the program with a message, and so should a row past the rows in
use, and a harness that stops can't go on to the next step. Try them by hand
in a scratch program: read a `vec3` column as a `u32`, then as a struct of
twelve `u8`s (the right size, aligned to 1), then ask for `column_row(c&, 2)`
of a two-row column. Each should stop with a message that says what was
wrong. rust-dod's harness checks these, because Rust can catch a panic.

**Level 4, variations.** The same harness, different insides:

- Grow by **1.5** instead of 2. Count the grows and the rows copied for 1000
  pushes. Why do some allocators prefer it?
- Allocate with **`memops_arena_realloc_`** instead of a new block and a
  `memcpy`. When does it move the rows, and when can it extend the block in
  place?
- **Shrink**: when a swap-remove leaves the column less than a quarter full,
  move the rows to a block of half the capacity. Why a quarter and not a half?
  (Push and remove one row, over and over, at the boundary.) In an arena,
  what does shrinking actually give back?

## When it fails

    FAIL at operation 11 (seed 1): the column was full at 4 rows and grew to 5; it should grow by at least half
        debug it: build/dojo/column/harness --seed 1 --stop 11
        with a breakpoint on dojo_stop_here, which runs just before that operation

`python tools/dojo.py column` built that harness with your kata. Run it under
your debugger with those arguments and a breakpoint on `dojo_stop_here`
(`gdb --args build/dojo/column/harness --seed 1 --stop 11`, then
`break dojo_stop_here`, `run`). It stops just before the operation that
fails; step out and into your code.

If the harness crashes instead, on a slice index past the end say, the runner
runs it again with `--trace 1` and prints the operation that was running.
