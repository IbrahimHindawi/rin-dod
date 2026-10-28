# 2. Swap-remove and the back-reference

`dojo/2.swap_remove/play_swap_remove.rin`

Systems loop over values, so values are kept **packed**: one after another,
no holes, nothing to skip. Removing one from the middle would leave a hole, so
the last value moves into it instead. That's **swap-remove**: one copy,
however many values there are, at the price of order.

Values move, so an id can't be the position of its value. Two arrays keep
track:

- **sparse, by id:** `rows[id]` says which row id's value is in now;
- **packed, by row:** `ids[row]` is the id that owns the row. This is the
  **back-reference**: when the last row moves into a hole, it says whose entry
  in `rows` to fix.

The whole structure is what [EnTT](https://github.com/skypjack/entt) calls a
sparse set.

**The invariant:** the rows are packed, and the two arrays point at each
other: for every row, `rows[ids[row]]` names that row, and an id with no value
has no row.

In the course: [1.4](../../ecs/docs/1.4_entity_index.md) packs entities into
rows this way, [2.3](../../ecs/docs/2.3_tables.md) does it for every column of
a table, and [2.6](../../ecs/docs/2.6_add_remove.md) does it when an entity
moves between tables.

## Watch it: the playground

    python tools/dojo.py play swap_remove

It inserts four values, removes one from the middle, and draws both sides
after each step:

```
remove 7, in row 1: the last row, 5's, moves into the hole
    row         0    1    2
    ids         3    5    1
    values     30   50   10
    rows    1->2  3->0  5->1  (id -> row)
```

Step through it: break on `sparse_set_remove`, and watch `ids` and `rows` as
the last row moves. Then flip the switch at the top, `fix_back_reference`, to
`0` and run it again. Id 5's row still says 3, past the end, so `get 5` finds
nothing. Then `insert 9` puts 9's value in row 3, and `get 5` returns 90,
another id's value, with nothing to say it's wrong. That's the bug every
packed array invites, and the reason the back-reference exists.

## Do reps: the kata

You write `sparse_set`. The heart of it is `sparse_set_remove`:

```rin
sparse_set_remove: proc(s: *sparse_set, id: u32) -> option<u64> = {
    if (sparse_set_get(s, id) == null) {
        return option<u64>none();
    }
    entry: *u32 = vec<u32>at(s*.rows&, cast(id, u64));
    row: u64 = cast(entry* - 1, u64);
    entry* = 0;
    value: u64 = vec<u64>at(s*.values&, row)*;
    last_value: u64 = vec<u64>pop(s*.values&);
    last_id: u32 = vec<u32>pop(s*.ids&);
    if (row < s*.values.length) {
        vec<u64>at(s*.values&, row)* = last_value;
        vec<u32>at(s*.ids&, row)* = last_id;
        vec<u32>at(s*.rows&, cast(last_id, u64))* = cast(row, u32) + 1;
    }
    return option<u64>some(value);
}
```

That's the reference, so don't read it before level 1 if you'd rather not
know. `vec` has no swap-remove of its own: the last element is popped, and
written over the hole unless the hole was the last row. The full API:

```rin
sparse_set_insert: proc(s: *sparse_set, id: u32, value: u64) -> option<u64> = {
```

```rin
sparse_set_get: proc(s: *sparse_set, id: u32) -> *u64 = {
```

plus `sparse_set_init`, `sparse_set_len`, `sparse_set_values` (the packed
values, in row order) and `sparse_set_ids` (`ids[row]` owns `values[row]`).

| level | you write | target |
|---|---|---|
| 1 | `sparse_set_remove`, in an otherwise finished file | 2:00 |
| 2 | every proc body; the fields and signatures are given | 8:00 |
| 3 | the whole file, from a blank page | 10:00 |

    python tools/dojo.py start swap_remove 2
    python tools/dojo.py swap_remove

The harness runs the playground's steps as a scenario, then 20,000 random
inserts and removes over a small range of ids, so the same ids come and go
many times, against a plain array from id to value. Every 64 operations it
checks the packed rows themselves: as many as the model has, and each row's
owner holding exactly that row's value. The seeds give the same runs as
rust-dod's dojo.

**rin notes.** Where Rust's kata returns `Option<T>` and has `get_mut`, this
one uses std's `option<u64>` for what `insert` and `remove` give back (the old
value, or none), and one `sparse_set_get` that returns a pointer to the value,
null for none, to read or to change, the way `kayan_get<T>` does in the
course. `rows[id]` holds the row plus one, so a new entry, 0, means "no row",
and growing `rows` is appending zeros.

**Level 4, variations.** The same harness, different insides:

- **Pages:** `rows` split into pages of 64 ids, each page made only when an
  id in it gets a value: a `vec<^u32>` of pages, null for a page not made yet.
  A big id no longer means a big `rows`. This is what EnTT does.
- **A sentinel:** `rows[id]` holds the row itself, with `0xFFFFFFFF` for "no
  row". What does growing `rows` cost now?
- **A flag:** a second `vec<b32>`, `has_row`, beside `rows`. Compare the
  memory with the plus-one encoding.

And one that **fails on purpose**: a remove that keeps order, shifting every
later row down and fixing each one's back-reference. The scenario stops it at
the first `ids` line. Why does the harness insist on swap-remove's order, and
what does keeping order cost?

## When it fails

A forgotten back-reference often shows up as a crash in a `sparse_set_get`
that is right, not in the `sparse_set_remove` that is wrong: `get` follows the
stale row past the end, and `vec<u64>at` stops the program.

    rin runtime: vec index out of bounds
    the harness crashed in the scenario, after the last step printed above

The last step printed is the last that passed, so the bug is in what ran
after it. In the fuzz run, the runner runs the harness again with `--trace 1`
and prints the operation that was running when it crashed. A failed check
gives the operation and the seed:

    FAIL at operation 64 (seed 1): row 4 holds 43's value 37043, but get(43) gives 43020
        debug it: build/dojo/swap_remove/harness --seed 1 --stop 64
        with a breakpoint on dojo_stop_here, which runs just before that operation

Run the harness under your debugger with those arguments and a breakpoint on
`dojo_stop_here` (`gdb --args build/dojo/swap_remove/harness --seed 1 --stop 64`,
then `break dojo_stop_here`, `run`). It stops just before the operation that
fails; step out and into your code.
