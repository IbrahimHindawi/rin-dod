# 5. The inspector

`src/5.inspector/inspector.rin`

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

`print_fields` walks that. It takes the component's bytes as a `[]const u8`,
from `kayan_get_bytes`, and cuts each field's bytes out of it by offset and
size, so a record that disagreed with the data would stop the program in
Debug. Struct fields recurse through `info`, enum fields print their member
name through `reflect_name_from_value_or`, a `[16]c8` prints as text, and
builtins print by type name. Because components are structs, even a single
float like `health.points` has a name to print.

## Tags

    health: struct = { points: f32; max: f32; regen_timer: f32 @ "hidden"; }

`@ "hidden"` is a string attached to the field, read with
`reflect_field_has_attr`. The inspector skips it. The component decides what
a tool shows, and the tool does not need to know the component.

## Names belong in tools

`set_f32_by_name(w, e, "health", "points", 55.0)` finds the component by
name, the field by name, checks the field is an `f32`, and writes it. It
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
   it as `yes` or `no`.
2. Give `position` a `@ "readonly"` tag and make `set_f32_by_name` refuse
   fields that carry it.
3. Write `set_by_name` for `u32` and `i32` as well, picking the write from
   `field.type`.
4. Print a whole table as rows and columns: one line per entity, one column
   per field.
