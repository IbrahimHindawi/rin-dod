# 3. The slot map

`dojo/3.slot_map/play_slot_map.rin`

Dojos 1 and 2, put together. Values live **packed** in rows, so a loop over
them has no holes (dojo 2). The rest of the program keeps **handles**, which
survive rows moving and say when their value is gone (dojo 1). In between is
a **slot** per index:

    handle 1:2  ->  slots[1] { generation 2, row 0 }  ->  values[0]

A lookup is two steps: the handle's generation must be the slot's, and the
slot says the row. A remove is both dojos' work: bump the generation and free
the index, then swap-remove the row and fix the slot of whoever moved. Game
engines keep textures, meshes and sounds this way, and it is the ECS's entity
index.

**The invariant:** dojo 1's and dojo 2's together. A handle is alive exactly
when its generation is its slot's; the rows are packed; and for every row,
the slot of the row's handle points back at that row.

In the course: [1.4](../../ecs/docs/1.4_entity_index.md) is a slot map with
an entity's components as its value, and every chapter after keeps it, with a
table number added to the slot in [2.4](../../ecs/docs/2.4_archetypes.md).

## Watch it: the playground

    python tools/dojo.py play slot_map

It keeps three textures, removes one, reuses its index, and draws the slots
and the rows after each step:

```
remove stone: free index 1 in its next life, and water moves into row 1
    slots    0: generation 1, row 0 | 1: generation 2, free | 2: generation 1, row 1
    rows     0:1 grass | 2:1 water
```

Step through it: break on `slot_map_remove`, and watch the slot, the free list
and the rows change in that order. Then flip the switch at the top,
`check_generation`, to `0` and run it again. The removed `stone` still finds
slot 1, and reads whatever is in slot 1's row now: `water`, then `lava`. In a
game, that's a sound that plays the wrong sample, or a mesh drawn with another
mesh's texture.

## Do reps: the kata

You write `slot_map`. Its two-step lookup:

```rin
slot_map_get: proc(m: *slot_map, h: dojo_handle) -> *u64 = {
    if (!slot_map_contains(m, h)) {
        return null;
    }
    row: u32 = vec<slot_map_slot>at(m*.slots&, cast(h.index, u64))*.row;
    return vec<u64>at(m*.values&, cast(row, u64));
}
```

and the API around it:

```rin
slot_map_insert: proc(m: *slot_map, value: u64) -> dojo_handle = {
```

```rin
slot_map_remove: proc(m: *slot_map, h: dojo_handle) -> option<u64> = {
```

plus `slot_map_init`, `slot_map_contains`, `slot_map_len`, `slot_map_values`
(the packed values, in row order) and `slot_map_handles` (`handles[row]` owns
`values[row]`). `dojo_handle` comes from `dojo/dojo.rin`, as in dojo 1.

| level | you write | target |
|---|---|---|
| 1 | `slot_map_remove`, in an otherwise finished file | 3:00 |
| 2 | every proc body; the fields and signatures are given | 12:00 |
| 3 | the whole file, from a blank page | 15:00 |

    python tools/dojo.py start slot_map 2
    python tools/dojo.py slot_map

Level 3 is the one to come back to. Once you can write a slot map from a blank
page in fifteen minutes, dojos 1 and 2 are in your hands too.

The harness runs the playground's steps as a scenario, then 20,000 random
inserts, removes, reads and writes against a model that keeps, per index, the
last generation handed out, whether the index is free, and its value. It
checks dojo 1's rules for the handles (a generation never handed out twice
for an index, a freed index reused before a new one is made, a removed handle
never alive again) and dojo 2's for the rows (packed, each row's handle
holding that row's value). The seeds give the same runs as rust-dod's dojo.

**rin notes.** As in dojo 2, `slot_map_remove` gives back std's `option<u64>`
and `slot_map_get` returns a pointer, null for a dead handle, to read or to
change the value; Rust's kata has `get` and `get_mut`. A zeroed handle, `{}`,
is never alive, since generations start at 1, and the scenario checks that
too.

**Level 4, variations.** The same harness, different insides:

- **Free list inside the slots**: a `next_free: u32` in each slot, only
  meaningful while the slot is free, and a `first_free` in `slot_map`. No
  `free` vec. What marks the end of the list?
- **One look at the slot**: `slot_map_remove` without `slot_map_contains`:
  fetch the slot once, check its generation, and use it. How many times does
  the reference look the slot up?
- **`slot_map_retain(m, keep)`**, with `keep` a `proc(h: dojo_handle, value:
  u64) -> b32`: remove every value it rejects, in one pass, keeping the rows
  packed. Which way should the loop walk? (Not checked by the harness; write
  your own test.)

## When it fails

    FAIL at operation 233 (seed 1): remove(33:1) returned 214, the model says 210
        debug it: build/dojo/slot_map/harness --seed 1 --stop 233
        with a breakpoint on dojo_stop_here, which runs just before that operation

The wrong value usually means a slot pointing at the wrong row: an earlier
remove moved a row and didn't fix its slot. Run the harness under your
debugger with those arguments and a breakpoint on `dojo_stop_here`, which runs
just before that operation, then look at the slot of the handle being
removed.

If the harness crashes instead, on a row past the end of `values` say, the
runner runs it again with `--trace 1` and prints the operation that was
running, or says the crash came in the scenario, after the last step printed.
