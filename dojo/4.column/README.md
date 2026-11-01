# 4. A type-erased column

`dojo/4.column/play_column.rin`

A column is one component's rows, kept as bytes. It doesn't know the type it
holds, only how many bytes make a row and how they must be aligned. That is
enough to grow, to zero a new row, and to move the last row into a hole,
which is everything a table does to its columns. The type comes back only at
the edge: a typed view turns the bytes into a `[]T`, for a `T` of the
column's size and alignment.

Two things make it work:

- **Aligned storage.** The bytes come from the region aligned to the column's
  alignment, so every row of the type lands where that type may live.
- **Growing by a factor.** A full column doubles, so the copies that growing
  costs add up to about one per push, however many rows there are.

**The invariant:** the column holds `count` rows of `size` bytes each, packed
from the start of a block aligned to `align`, with room for `capacity` rows. A
typed view is only handed out for a plain-data `T` of exactly `size` bytes,
aligned to exactly `align`, and only when the rows fit in the bytes. Plain
data means a struct of numbers with no pointers in it, since a column copies
rows as bytes.

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
to the new block. The old block stays in the region, unused, so a slice taken
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

You write `column`. Its bytes are a slice, `data: []u8 in level`, so even type
erasure is mostly checked code: `slice<u8>copy` and `slice<u8>zero` do the
work, and a row past the end stops the program like any index. Three things
need `unsafe { }`, a few lines each, and their signatures are the promise safe
code relies on:

- `column_make` keeps the region's arena, since a region can't be stored: a
  field `arena: ^memops_arena`, and `c*.arena = r`.
- `column_grow` takes a block from that arena, because `new_slice<u8>` can't
  ask for an alignment, and makes it a slice.
- `column_slice` tests the address and casts the bytes to `T`.

Keep each block that small: put your checks outside it, where the checker can
see them.

A full column's new bytes come from the arena, aligned to the column's
alignment:

```rin
        raw: ^u8 = cast(memops_arena_push_zero(c*.arena[0]&, c*.size * capacity, c*.align), ^u8);
        bytes: []u8 in level = cast(raw[0..c*.size * capacity], []u8 in level);
```

and the rows go across with `slice<u8>copy(bytes[0..kept], c*.data[0..kept])`.
Slicing checks both ends, so the copy can't run off either block. The typed
view is a generic proc that checks everything it relies on before it casts:

```rin
column_slice: proc<T>(c: *const column) -> []T in level = {
```

plus `column_make(r, size, align)`, `column_len`, `column_capacity`,
`column_push_zeroed` (a zeroed row at the end, and its row number),
`column_swap_remove(c, row)`, and `column_row(c, row)`, a row's bytes as a
`[]u8 in level`. The kata has no vec to lean on: it is the thing a vec would
be built from.

**What an `unsafe` block may believe.** rin has no private fields. Any checked
code holding a `*column` can write `c*.count = 1000`, so an `unsafe` block
must not trust a field or an argument unless the value carries its own bound,
as a slice does. That decides what `column_slice` tests:

- **The type's size and alignment**, against the column's. The column can't
  know the type, but it can refuse every type that can't be the one it was
  made for.
- **That the type is plain data**, `reflect_is_plain(T<>&)`. Any bytes are
  then a valid `T`, so a wrong type of the right shape gives wrong numbers,
  never a bad pointer: a `vec3` column read as a struct of three `u32`s gives
  1065353216, 1073741824 and 1077936128, the bits of 1.0, 2.0 and 3.0. A `T`
  with a pointer in it would turn bytes into an address, so it stops the
  program. `T<>` needs a struct or an enum, so a row is always one: the
  four-byte row here is `word: struct = { value: u32; }`, and
  `column_slice<u32>` doesn't compile.
- **That the rows fit**: `c*.count` against `c*.data.length / size`. `count`
  is a field, and can say anything; `length` belongs to the slice, and can't
  be wrong about it.
- **The address itself**: `cast(c*.data.data, usize) % align`, the bytes as
  they are, not what `c*.align` says about them.

The checked procs get this for nothing: a `column_row` with a lying `count` or
`size` stops at the slice, `range 6000..6012 out of bounds (length 48)`. The one
field still believed is `arena`: a raw pointer carries no bound. rin seals a
struct holding one to the file that declares it, so the harness and anything else
importing this file cannot write its fields. Inside the file that is on you:
only `column_make` writes `arena`, and every `unsafe` author owes that much.

| level | you write | target |
|---|---|---|
| 1 | `column_slice`, the typed view, in an otherwise finished file | 3:00 |
| 2 | every proc body, and a `column_grow` of your own; the fields and the other signatures are given | 15:00 |
| 3 | the whole file, from a blank page | 20:00 |

    python tools/dojo.py start column 2         kata.rin from level 2, and the clock starts
    python tools/dojo.py column                 your kata.rin against the harness
    python tools/dojo.py column --sanitize      the same with AddressSanitizer and UBSan

The harness first runs a short scenario: three `vec3`s written through
`column_slice` and read back as bytes, a swap-remove, a column aligned to 16,
and a column of tags, zero-byte rows. Then it runs 20,000 random pushes,
writes and swap-removes, shared between four row types: 3 bytes aligned to 1,
a `word` holding a `u32`, a 12-byte `vec3`, and a 16-byte `vec4` aligned to
16. Each is checked against a `vec` of that type, through `column_slice` and
through `column_row`, along with the alignment of every view, and that a full
column grows by at least half. The harness has two trusted helpers of its own,
`bytes_of` and `slice_address`, to look at a value's bytes and a slice's
address. The seeds give the same runs as rust-dod's dojo.

`--sanitize` is worth the wait here. A slice made from a raw pointer,
`raw[0..n]`, has whatever length you say, so a block asked for too small often
works on your machine. AddressSanitizer and UBSan don't let it happen by luck.
(They need the C compiler's sanitizer runtime; with clang that may be missing,
so try `CC=gcc`.)

What the harness can't check is a refusal: a column read as the wrong type
should stop the program with a message, and so should a row past the rows in
use, and a harness that stops can't go on to the next step. It never lies to
your column either, so a `column_slice` that tests only the type passes it.
Try them by hand in a scratch program: a copy of your kata with `level:
region;` where its `import "harness.rin"` was, and a `main` that opens the
region, `level: region = { ... }`, makes `c: *column in level =
column_make(level, sizeof(vec3), alignof(vec3));` in it, and pushes two rows.
Then, one at a time:

- read it as a `word` (the wrong size), then as a struct of twelve `u8`s (the
  right size, aligned to 1);
- ask for `column_row(c, 2)`;
- write `c*.count = 1000;`, then read it as a `vec3`;
- write `c*.data = c*.data[1..25];`, then read it as a `vec3`;
- make a column of a struct with an `option<*u32 in level>` in it, by its own
  `sizeof` and `alignof`, and read it as that struct.

Each should stop with a message that says what was wrong. Then read the
`vec3`s you wrote as a struct of three `u32`s, which should not stop, and
print what comes back. rust-dod's harness checks the first refusals, because
Rust can catch a panic.

**Level 4, variations.** The same harness, different insides:

- Grow by **1.5** instead of 2. Count the grows and the rows copied for 1000
  pushes. Why do some allocators prefer it?
- Allocate with **`memops_arena_realloc_`**, on `c*.arena[0]&` and inside
  `column_grow`'s `unsafe { }`, instead of a new block and a `slice<u8>copy`.
  Hand it the old block by `c*.data.data` and `c*.data.length`, the slice's
  own bound, not by `c*.capacity`. When does it move the rows, and when can it
  extend the block in place?
- **Shrink**: when a swap-remove leaves the column less than a quarter full,
  move the rows to a block of half the capacity. Why a quarter and not a half?
  (Push and remove one row, over and over, at the boundary.) In a region,
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

If the harness crashes instead, on a slice range past the end say, the runner
runs it again with `--trace 1` and prints the operation that was running.
