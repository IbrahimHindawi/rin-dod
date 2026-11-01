# 4. Entity handles

`src/4.entity_handles/entity_handles.rin`, `includes/kayan.rin`

**In the dojo:** [1. free list and generations](../dojo/1.free_list/README.md), [3. the slot map](../dojo/3.slot_map/README.md), [9. interning](../dojo/9.interning/README.md), each on its own, to watch and to practise.

The world: tables made on demand, entity handles that survive row moves,
despawning with index reuse, and moving an entity between archetypes when a
component is added or removed. The code is `includes/kayan.rin`. The lesson
program calls each part and prints what happened.

## Handles, slots, rows

    kayan_entity: struct = { index: u32; generation: u32; }
    kayan_slot:   struct = { generation: u32; table: u32; row: u32; }

A handle is what the rest of a program keeps. Its `index` picks a slot, and
the slot says where the entity lives now. Rows move all the time: every
despawn and every archetype change swap-removes. When one does, the table's
`entities` column says which entity owned the moved row, and that entity's
slot gets the new row number. Handles never change.

`generation` is what makes a handle safe to keep after its entity dies.
Despawning bumps the slot's generation and frees the index, and the next spawn
reuses the index with the new generation:

    spawn d: it reuses a's index with the next generation
        d = 0:2 in table 0 row 2 {position velocity} at (4.0, 0.0)
        a = 0:1 is dead

`kayan_alive` is one comparison: the handle's generation against the slot's.
A free slot already holds its next generation, which no handle carries yet,
so no separate "alive" flag is needed. `a` cannot reach `d`'s data,
`kayan_get` returns null for it, and despawning it again returns
`kayan_status.dead` and changes nothing.

Generations start at 1. A zeroed handle, `{}`, is `0:0`, which never matches
a slot, so it can stand for "no entity" without a separate flag.

## A handle to keep, a pointer to borrow

`kayan_get` can miss, and its type says so. It returns `option<*T>`, which the
checker will not let you read until you have tested it:

    p: option<*position> = kayan_get<position>(w, e);
    if (p) {
        printfmt(" at ({:.1}, {:.1})", cast(p*.at.x, f64), cast(p*.at.y, f64));
    }

The pointer is a borrow of the world, good until the next spawn, despawn, add or
remove, which can move what it points at. The checker holds you to that: use one
after a call that can change the world and rin says

    'kept' may be stale: 'world', which it was taken from, has been changed since; take it again

So a pointer is for now, and the handle is for later. That was already this
lesson's advice; now it is checked.

## The world in a region

    world: *kayan_world in level = kayan_world_make(level);

`kayan_world_make` makes the world whole, inside the region, and every list it
holds says where it lives:

    tables: *vec<kayan_table> in level;
    by_signature: *hashmap<u64, u32> in level;
    slots: *vec<kayan_slot> in level;
    free: *vec<u32> in level;

A table holds lesson 3's columns of bytes, and its entities, as slices:

    kayan_table: struct = {
        signature: u64;
        count: u64;
        capacity: u64;
        entities: []kayan_entity in level;
        columns: [64][]u8 in level;
    }

Each slice knows its own length, so nothing here depends on a count being right.
Almost all of `includes/kayan.rin` is checked because of that: spawning,
despawning, moving, growing a table, adding and removing a row are plain indexing
and `slice<u8>copy`, and a row past the end stops the program. Only three procs
need `unsafe { }`. `kayan_world_make` keeps the region's arena, a raw pointer, so
columns can grow without being handed the region on each call. `kayan_bytes` takes
a block from that arena with a component's alignment. `kayan_view<T>` is the one
place bytes become a type:

    kayan_view: proc<T>(bytes: []u8 in level, count: u64) -> []T in level = {
        if (!reflect_is_plain(T<>&)) {
            printfmt("kayan: a column holds plain data, and {} is not\n", T<>.name);
            exit(1);
        }
        if (count > bytes.length / sizeof(T)) {
            printfmt("kayan: a view of {} {} on {} bytes\n", count, T<>.name, bytes.length);
            exit(1);
        }
        unsafe {
            if (cast(bytes.data, usize) % alignof(T) != 0) {
                printfmt("kayan: bytes that are not aligned for {}\n", T<>.name);
                exit(1);
            }
            raw: ^T = cast(bytes.data, ^T);
            return cast(raw[0..count], []T in level);
        }
    }

It takes nothing on trust, for the reasons lesson 3 gives. rin has no private
fields: a program can write `kayan_table_at(world, 0)*.count = 1000;`, and an
`unsafe` block must not trust a field or an argument unless the value carries its
own bound, as a slice does. That write stops at the next view:

    kayan: a view of 1000 position on 128 bytes

And a component must be plain data, so any bytes are a valid T: reading the wrong
type gives wrong numbers, never a bad pointer. Everything else, `kayan_column` and
`kayan_get` included, is written in terms of this. The lesson program itself has
no `unsafe` at all.

## Statuses

`kayan_despawn`, `kayan_add`, `kayan_remove` and `kayan_move` return
`kayan_status`, an `enum[must_use]`: `ok`, or `dead` when the handle no longer
names a live entity. Ignoring one is a compile error. The lesson discards
them on purpose with `_ = kayan_add<health>(...)` where the handle is known to
be alive.

## Tables on demand

`kayan_table_for(w, signature)` looks the signature up in a
`hashmap<u64, u32>` and makes the table if it is new. Nobody declares
archetypes; they appear when an entity first needs that combination. Tables
live in a `vec<kayan_table>` and are referred to by index, because adding one
can move the whole list.

Tables start with room for 16 rows and double when full. The old columns stay
in the region unused, which is a waste these lessons accept. The last part of
the program spawns 40 entities so the first table grows twice, despawns every
other one, and checks the result two ways.

## Checking the world

Reading back each survivor's position is a weak check. Swap-remove copies
rows, so a stale row often still holds the right numbers. `kayan_verify` checks
the invariant instead: every row of every table belongs to a live entity whose
slot points back at that table and row, and the rows add up to the live count.
It prints each problem it finds and returns how many there were. The lesson
prints `kayan_verify: 0 problems` and fails if that is not so.

`kayan_get` also checks the slot's row against the rows in use, in every build,
so a slot that points past the end of its table stops the program at the first
lookup.

## Moving between archetypes

    give b health: b moves to a new table and keeps its position

`kayan_add<health>` computes `signature | bit(health)`, finds or makes that
table, appends a row, copies every component the two tables share, then
swap-removes the old row. `kayan_remove` is the same move with the bit
cleared. A move costs two row copies, one into the new table and one to fill
the hole in the old, so components that come and go every frame are better as
a field than as a component. A burning flag in `health`, say, instead of a
`burning` component.

## Try

1. Right after the first three spawns, despawn `b`, spawn an `x`, which reuses
   `b`'s index, and keep using `b`'s handle. Every call notices: `kayan_alive` says
   no, `kayan_get` returns null, `kayan_set` refuses, `kayan_signature` is 0,
   `kayan_get_bytes` is empty, and `kayan_add`, `kayan_remove` and `kayan_despawn`
   return `dead`. `x` is untouched. Now make `kayan_alive` stop checking the
   generation. None of them notices, and they all land on `x`: `kayan_set`
   overwrites it, `kayan_add` and `kayan_remove` move it, and `kayan_despawn` kills
   it. `kayan_verify` still says 0 problems, because the world is consistent. It is
   only the wrong entity, a wrong answer and not a memory error. Further on, the
   lesson's own print of dead `a` stops on a bounds check, since its row is gone.
2. Remove the line in `kayan_table_remove_row` that updates the moved entity's
   slot. The program stops at the first `kayan_get` through a stale row, with
   `index 2 out of bounds (length 2)`, in Debug and in Release. Print
   `kayan_verify(world)` right after the first despawn, and it names the slot:
   `2:1 is in table 0 row 0, its slot says table 0 row 2`. Now build it with
   `-DRIN_NO_BOUNDS_CHECKS`, without that print. `c` reads back `(3.0, 0.0)` from a
   row nobody owns, the right numbers from the wrong place, and the program runs on
   until `kayan_table_remove_row`'s own check stops it: `kayan: row 30 is past the
   28 rows in use`.
3. At the end of the lesson, table 0 has 22 rows and room for 64. Hold a
   `[]position` from `kayan_column`, spawn at least 43 more so the table grows,
   then write through the old slice. rin refuses, with the same message. Compile
   it with `rin compile --unsafe`, which turns the rules off, and read the position
   back through `kayan_get`. The write is lost, and nothing reports it. That stale
   slice is why lesson 6 defers spawns. Now do what the message says, and take the
   slice again after the spawns.
4. Add `kayan_has<T>(w, e) -> b32` without moving anything.
5. Make `component_of<velocity>` return `component.position`. Both are 8 bytes, so
   nothing stops it: position and velocity now share a column, every position reads
   `(0.0, 1.0)`, and the lesson's own position check fails, with no crash anywhere.
   Then make `component_of<health>` return `component.velocity`, which is a different
   size, and read what `kayan_view` says.
