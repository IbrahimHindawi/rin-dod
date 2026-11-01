# 3. Many archetypes

`src/3.many_archetypes/many_archetypes.rin`

**In the dojo:** [4. a type-erased column](../dojo/4.column/README.md), [6. bitsets](../dojo/6.bitset/README.md), each on its own, to watch and to practise.

Four archetypes (rock, ship, bullet, turret) and four components (position,
velocity, health, damage). One `table` type holds all four archetypes, and two
queries decide which tables each system visits.

## A table without a type

Lesson 2's table had one typed field per column. That cannot work for every
archetype at once, so the columns become bytes:

    table: struct = {
        name: ^const c8;
        signature: u64;
        count: u64;
        capacity: u64;
        columns: [component<>.count][]u8 in level;
    }

`columns[id]` is empty when the table has no such component, and `table_has`
reads that from the signature. Its element size is `component_info[id]*.size`,
where `component_info` holds each component's reflect record, `position<>&` and
so on. `table_add_row` and lesson 4's moves work only from sizes, so they never
need to know a component's type. A column is a slice of bytes, so all of that is
checked: a row past the end stops the program like any index.

    slice<u8>zero(t*.columns[c][row * size..(row + 1) * size]);

Types come back at the edges. `column<T>(t)` asks `component_of<T>()` for T's
id, views that column's bytes as T, and returns a `[]T` of the rows in use.
`component_of` is one specialisation per component, one line each. Systems
take `[]position`, `[]velocity` and so on, exactly as in lesson 2.

## What the checker cannot see

Two things are `unsafe { }` here. `table_create` allocates columns with a
component's alignment, which only the arena can promise. `column<T>` turns bytes
into a type, which no checker can vouch for:

    column: proc<T>(t: *const table) -> []T in level = {
        c: component = component_of<T>();
        if (!table_has(t, c)) {
            printfmt("table {} has no {} column\n", t*.name, component_info[c]*.name);
            exit(1);
        }
        if (!reflect_is_plain(T<>&)) {
            printfmt("a column holds plain data, and {} is not\n", T<>.name);
            exit(1);
        }
        bytes: []u8 in level = t*.columns[c];
        if (t*.count > bytes.length / sizeof(T)) {
            printfmt("table {} has {} rows and room for {}\n", t*.name, t*.count, bytes.length / sizeof(T));
            exit(1);
        }
        unsafe {
            if (cast(bytes.data, usize) % alignof(T) != 0) {
                printfmt("table {}: a column that is not aligned for {}\n", t*.name, T<>.name);
                exit(1);
            }
            raw: ^T = cast(bytes.data, ^T);
            return cast(raw[0..t*.count], []T in level);
        }
    }

Most of that is checks, and each one is there for a reason.

**rin has no private fields.** Any checked proc can write `t*.count`, so an
`unsafe` block must not trust a field or an argument unless the value carries its
own bound, as a slice does. Here the bytes know their length, and `count` is
measured against them. Write `tables[1]*.count = 1000;` in `main` and the program
stops rather than hand out a slice past the column:

    table ship has 1000 rows and room for 16

Set a bit in a signature by hand and it stops the same way, since the column
behind that bit is empty.

**A plain-data T means any bytes are a valid T.** `reflect_is_plain` accepts
numbers, enums, and arrays and structs of them, and refuses a pointer. So reading
the wrong type gives wrong numbers, never a bad pointer. Make
`component_of<health>` return `component.position` and the program runs to the
end, with ships at `( 62.0, 100.0)`. That is a bug, and it is one the output shows.
It is not a memory error.

What comes back is `[]T in level`, and it is a borrow of the table, good until a
row is added or removed. Everything above those two procs is checked, and works in
slices and `*table`. A struct holding a raw pointer, here the table's name, is
only ever made by a proc that vouches for it, so `main` holds the tables by
pointer, in the region:

    tables: [4]*table in level = {
        table_create(level, "rock", rock_components, 16),
        table_create(level, "ship", ship_components, 16),
        table_create(level, "bullet", bullet_components, 16),
        table_create(level, "turret", turret_components, 16),
    };

## Sized by reflection

`component` has no `count` member at the end. `component<>.count` is the
number of members, from the enum's reflect record, and it sizes both
`columns` and `component_info`. With a hand-added `count` member the
reflected count is one more than the number of components. That is how the
bounds check found a bug while this lesson was being written.

`component_info` is a global, and globals live in `permanent`, the region of the
whole program, so its type says that of the records it holds:

    component_info: [component<>.count]*const reflect in permanent = {

`components_check` compares each enum member's name with the name in
`component_info`. Swap two entries in `component_info` and the program stops
before anything runs:

    component 2 is health in the enum but damage in component_info

## Different types, fewer checks

`move_system` takes `noalias []position`, as lesson 2's takes
`noalias []vec2`, and for the same reason, so it is `proc[unsafe]` too.
`regen_system` takes `noalias []health`, its only slice, for the reason lesson 2
gives for `age_system`.

One difference shows without `noalias`: clang on Linux vectorizes this
`move_system` without a run-time overlap check, and lesson 2's only with one.
Here the two columns are different struct types, `position` and `velocity`, and
clang reads C's type rules as saying they cannot share memory; built with
`-fno-strict-aliasing`, it checks here too. In lesson 2 both are `vec2`. gcc
checks in both, once it vectorizes at all (lesson 1). clang-cl, rin's default
compiler, does not use those rules, to match MSVC, so on Windows neither lesson
vectorizes without it. `noalias` makes the answer the same everywhere, whatever
the column types are.

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
3. Change `columns` to `[4][]u8 in level`. Then add a fifth component, give it to
   a table, and see what happens, and where.
4. Write `table_remove_row` with the swap-remove from lesson 2, working only
   from `component_info` sizes and `slice<u8>copy`. It needs no `unsafe`, since
   both ends of each copy are slices.
5. Give `damage` a field that holds a pointer, `owner: option<*position in level>`,
   and read what `column<damage>` says. Now see what `column<T>`'s checks are for.
   The rest of this exercise misuses memory on purpose, so run it in a VM, not on
   your machine.

   Take out the plain-data check. The program prints what it always did, because
   nothing reads `owner`. So read one: declare
   `lookalike: struct = { owner: option<*position in level>; }`, make its
   `component_of` return `component.position`, and read `owner` from the second
   ship's row. rin accepts it, and the ship's position, `(0.0, 10.0)`, faults as an
   address. That is the bad pointer plain data rules out.

   Put that check back and take out the check of `count` against the bytes. Set a
   ship table's `count` to 1000, call `table_set<position>` at row 16, and set
   `count` back to 2. Under AddressSanitizer it stops at that write. Without the
   sanitizers nothing reports it: row 16 is the first ship's velocity, and that ship
   ends frame 1 at `(0.5, 0.5)` instead of `(1.0, 0.0)`. Keep writing to row 199
   and you pass the health column and reach the bullet table's own fields at row 48,
   its name pointer among them, and the program dies with no message.
