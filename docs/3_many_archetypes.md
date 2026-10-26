# 3. Many archetypes

`src/3.many_archetypes/many_archetypes.rin`

Four archetypes (rock, ship, bullet, turret) and four components (position,
velocity, health, damage). One `table` type holds all four archetypes, and two
queries decide which tables each system visits.

## A table without a type

Lesson 2's table had one typed field per column. That cannot work for every
archetype at once, so the columns become bytes:

    table: struct = {
        signature: u64;
        count: u64;
        capacity: u64;
        columns: [component<>.count][*]u8;
    }

`columns[id]` is null when the table has no such component. Its element size
is `component_info[id][0].size`, where `component_info` holds each
component's reflect record, `position<>&` and so on. `table_add_row` and
lesson 4's moves work only from sizes, so they never need to know a
component's type.

Types come back at the edges. `column<T>(t)` asks `component_of<T>()` for T's
id, casts that column to `[*]T`, and returns it as a `[]T` of the rows in use.
`component_of` is one specialisation per component, one line each. Systems
take `[]position`, `[]velocity` and so on, exactly as in lesson 2.

## Sized by reflection

`component` has no `count` member at the end. `component<>.count` is the
number of members, from the enum's reflect record, and it sizes both
`columns` and `component_info`. With a hand-added `count` member the
reflected count is one more than the number of components. That is how the
bounds check found a bug while this lesson was being written.

`components_check` compares each enum member's name with the name in
`component_info`. Swap two entries in `component_info` and the program stops
before anything runs:

    component 2 is health in the enum but damage in component_info

## Queries

    moving: query = { .all = bit(component.position) | bit(component.velocity) };
    healing: query = { .all = bit(component.health), .none = bit(component.damage) };

A table matches when it has every bit in `all` and none in `none`. `moving`
visits ships and bullets. `healing` visits ships but not turrets, which have
health but also deal damage. The output prints each visit.

## The signature cannot lie

`table_create` builds the signature from the component list it allocates
columns for. kayan wrote them separately, and archetype D's signature left out
two of its columns (see [0_from_kayan.md](0_from_kayan.md)).

## Try

1. Add an `armor` component, give it to turrets, and make a query that
   visits only tables with both `health` and `armor`.
2. Ask a rock for `column<velocity>`. Read the message, then find where it
   comes from.
3. Change `columns` to `[4][*]u8`. Then add a fifth component and see what
   happens, and where.
4. Write `table_remove_row` with the swap-remove from lesson 2, working only
   from `component_info` sizes and `memcpy`.
