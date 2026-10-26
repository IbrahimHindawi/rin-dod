# 0. From kayan

[kayan](https://github.com/IbrahimHindawi/kayan) is a sketch of an archetype
entity component system in C, about 200 lines in `src/kayan.h`, with haikal
generating its containers. These lessons start from its idea and rebuild the
rest. This page says what was kept, what was changed, and why, so the lessons
can be read as a review of it as much as a rewrite.

## What kayan does

Components are bits in an enum, `positions = 1 << 0`, `velocities = 1 << 1`
and so on. Each archetype is a C struct written by hand (`A`, `B`, `C`, `D`)
that starts with an `ArchetypeHeader` and then holds one haikal `Array_T` per
component. The header has a `u64` signature and a `Map_u64` from column name
to the column's byte offset in the struct.

A query walks an array of `void *` pointing at the archetypes, reads each
header, and tests `(signature & want) == want`. For a match it looks up
`"positions"` and `"velocities"` in the offset map, adds the offsets to the
struct's address, and runs the loop over the two columns.

## Kept

- **An archetype is a struct of arrays.** Each component is a contiguous column
  and every entity in the table has every column. That is the whole point,
  and kayan had it right from the start.
- **A signature is a u64 of component bits**, and a query is the test
  `(signature & all) == all`. Lesson 3 adds a `none` mask beside it.
- **Arenas** for all of it. Nothing in these lessons is freed one at a time.

## Changed

- **One table type for every archetype** (lesson 3). kayan needs a new C
  struct, a new signature line and new offset-map lines for every archetype.
  Here an archetype is data: a signature, and the world makes its table the
  first time something needs it (lesson 4).
- **Columns by component id, not by name** (lesson 3). kayan hashes the
  strings `"positions"` and `"velocities"` on every query. Here a table's
  columns are an array indexed by component id, so finding one is an index.
  Names are kept for tools, through reflection (lesson 5).
- **The signature comes from the columns** (lesson 3). In kayan they are
  written separately and can disagree. In `D` they do: it has `positions` and
  `velocities` columns, but its signature is `health | damage | alive`, so
  the movement query never visits it.
- **A row is added and removed in one place** (lesson 2). kayan appends to
  each column at the call site, and keeps `entity_count` apart from the
  columns. For `B` and `D` it increments `a`'s count instead of their own
  (`kayan.h` lines 142, 145, 168, 174), so `A` reports seven entities and the
  others report none. Nothing breaks only because the query loop happens to
  use the column's own length.
- **Entities have handles** (lesson 4). kayan's entity id is the value of an
  archetype's `entity_count` before it is bumped: meant per table, in
  practice `A`'s, as above. Nothing records where an entity lives, so there is
  no way to refer to one entity from elsewhere, to remove it, or to move it to
  another archetype. The lessons use an
  `{index, generation}` handle and a slot list that tracks each entity's
  table and row.
- **Entities move between archetypes** (lesson 4). Adding or removing a
  component moves the entity to the matching table, copying the components
  both tables share.
- **Structural changes wait for the end of the frame** (lesson 6), through a
  command buffer in a frame arena. kayan never changes structure while a
  query runs, but only because it never changes structure at all.
- **Reflection replaces hand-written tables** (lessons 3 to 5). A component's
  size and alignment come from `T<>`, and so do the names a tool prints. The
  offset map goes away entirely.

## Not carried over

- **`vec4s` for positions.** kayan pads 3D vectors to 16 bytes, which suits
  SIMD loads. The lessons use `vec2` and `vec3` and keep loops scalar. Lesson
  1's exercises come back to this.
- **cglm and the haikal containers.** rin's generics and std (`vec<T>`,
  `hashmap<K, V>`, slices) cover what they did.

## Small things in kayan.h

- The query's inner loop declares `i32 i`, shadowing the outer `i`
  (line 201).
- Each lookup on lines 199 and 200 hashes and compares a string, once per
  column per archetype per query. That is cheap next to a large loop, but it
  is work that an array index does for nothing.
