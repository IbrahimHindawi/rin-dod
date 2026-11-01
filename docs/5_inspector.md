# 5. The inspector

`src/5.inspector/inspector.rin`

**In the dojo:** [11. a reflection walk](../dojo/11.reflect/README.md), on its own, to watch and to practise.

A soldier and a crate, printed field by field by code that names no component
type, then edited by component and field name, then a table layout report.
Everything comes from the reflect records the world already holds for sizes.

## What a reflect record has

`T<>` is a `reflect` record: `name`, `size`, `align`, `kind`, `count`, and
for a struct, `count` fields. Each field has its `name`, `offset`, `size`,
`type` (`"f32"` for a builtin, `"array_16_c8"` for a `[16]c8`), `elem_type`
and `array_count` for arrays, and `info`, the record of the field's own type
when it has one. A nested struct or an enum field has `info`; a builtin like
`f32` does not.

The walk asks for these through procs that return `option<*const>`, because a
record can run out of fields and a builtin has no record of its own:

    f: option<*const reflect_field> = reflect_field_at(type, i);
    ...
    info: option<*const reflect> = reflect_field_info(f);

`print_fields` walks that. It takes the component's bytes as a `[]const u8`,
from `kayan_get_bytes`, and cuts each field's bytes out of it by offset and
size, so a record that disagreed with the data would stop the program in
any build. Struct fields recurse through `info`, enum fields print their member
name through `reflect_name_from_value_or`, a `[16]c8` prints as text, and
builtins print by type name. Because components are structs, even a single
float like `health.points` has a name to print.

## Bytes as a value

The walk is checked. The last step is not: a field's bytes may sit at any address,
so they cannot simply be cast to a `*f32`. They go through a local, which is
aligned, with `memcpy`, and `memcpy` is C's, so that is `unsafe`. These are the
lesson's small unsafe procs, one a type, each checking the length it is given:

    bytes_as_f32: proc(at: []const u8) -> f32 = {
        unsafe {
            if (at.length < sizeof(f32)) { printfmt("inspector: too few bytes for an f32\n"); exit(1); }
            value: f32 = 0.0;
            memcpy(value&, at.data, sizeof(f32));
            return value;
        }
    }

`bytes_as_u32`, `bytes_as_i32` and `bytes_set_f32` are the same, `print_text`
prints a `[N]c8`, and `cstr_into` copies a C string into one. The bytes come from
`kayan_get_bytes`, which is checked: a `[]u8` cut from the column.

## Tags

    health: struct = { points: f32; max: f32; regen_timer: f32 @ "hidden"; }

`@ "hidden"` is a string attached to the field, read with
`reflect_field_has_attr`. The inspector skips it. The component decides what
a tool shows, and the tool does not need to know the component.

## Names belong in tools

`set_f32_by_name(world, soldier, "health", "points", 55.0)` finds the component
by name, the field by name, checks the field is an `f32`, and writes it. It
refuses `weapon.ammo`, a `u32`, and the crate's `health`, which it does not
have. That is the flexibility an editor or a console needs. It is also the
string comparison kayan did in every query, once per archetype. Here it runs
once per edit, and systems keep using ids.

## Layout

`print_layout` lists each table's columns with size and alignment, and each
column's bytes in use out of the bytes allocated for the table's capacity. It
is the kind of report that shows when a component has grown padding, when a
table has far more room than rows, or when a table carries a column most of
its systems never read.

## Try

1. Add a `bool`-like `b32` field to `weapon` and teach `print_builtin` to print
   it as `yes` or `no`. It needs a reader beside `bytes_as_u32`, through a local
   in the same way.
2. Give `position`'s `heading` field a `@ "readonly"` tag, the way `health` tags
   `regen_timer`, and make `set_f32_by_name` refuse fields that carry it.
3. Write `set_by_name` for `u32` and `i32` as well, picking the write from
   `f*.type`. Each new write is another small unsafe proc, like `bytes_set_f32`.
4. Print a whole table as rows and columns: one line per entity, one column
   per field.
