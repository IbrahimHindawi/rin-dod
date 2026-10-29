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
in the arena unused, which is a waste these lessons accept. The last part of
the program spawns 40 entities so the first table grows twice, despawns every
other one, and checks the result two ways.

## Checking the world

Reading back each survivor's position is a weak check. Swap-remove copies
rows, so a stale row often still holds the right numbers. `kayan_verify` checks
the invariant instead: every row of every table belongs to a live entity whose
slot points back at that table and row, and the rows add up to the live count.
It prints each problem it finds and returns how many there were. The lesson
prints `kayan_verify: 0 problems` and fails if that is not so.

`kayan_get` also checks the slot's row against the rows in use, so in Debug a
slot that points past the end of its table stops the program at the first
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

1. Despawn `b` and keep using its handle. Which calls notice, and which would
   not if `kayan_alive` did not check the generation?
2. Remove the line in `kayan_table_remove_row` that updates the moved entity's
   slot. In Debug the program stops at the first `kayan_get` through a stale
   row. Build it with `-DNDEBUG` and run it again: the position check still
   says all 20 are fine, and `kayan_verify` lists every broken slot.
3. At the end of the lesson, table 0 has 22 rows and room for 64. Hold a
   `[]position` from `kayan_column`, spawn at least 43 more so the table grows,
   then write through the old slice and read the position back through
   `kayan_get`. The write is lost, and nothing reports it. That stale slice is
   why lesson 6 defers spawns.
4. Add `kayan_has<T>(w, e) -> b32` without moving anything.
