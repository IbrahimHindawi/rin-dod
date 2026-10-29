# 11. A reflection walk

`dojo/11.reflect/play_reflect.rin`

A **reflect record** lists a struct's fields: each one's name, where its
bytes start in the struct, how many there are, and its type, with the type's
own record when it's a struct too. rin's compiler writes one for every
struct: `lamp<>` is lamp's. With records, one piece of code can list, read,
write and compare the fields of any type it's handed, by name: an inspector,
an editor, a save file, a network diff. It never names the type. It walks the
bytes by the record:

    "at.y" in a lamp:  lamp's field at, offset 8  ->  vec2's field y, offset 4  ->  bytes 12..16

Each offset counts from the start of the field's own struct, so a path adds
them up as it goes down. And an offset is the record's to say, not something
to work out from the sizes before it: a `u8` followed by an `f32` leaves 3
bytes of padding, and the `f32` starts at 4.

**The invariant:** the walk reads and writes exactly the bytes the compiler
gave each field. Read by path, every field is what the struct holds.

In the course: [2.7](../../ecs/docs/2.7_inspecting.md) prints any entity
field by field from records. The Advanced [lesson 5](../../docs/5_inspector.md)
builds an inspector, and an editor's write by name.

## Watch it: the playground

    python tools/dojo.py play reflect

It prints a lamp's record, walks the lamp by it, changes fields by path, and
diffs the lamp with how it was:

```
a lamp's record: 20 bytes
    on: offset 0, size 1, u8
    power: offset 4, size 4, f32
    at: offset 8, size 8, a struct
    flicker: offset 16, size 4, f32, hidden
...
set at.x to 5.00: true
diff with the lamp before: power at.x
set flicker to 0.50: true
diff with the lamp before: power at.x
```

The walk reads the lamp through its bytes. Step through it: break on `find`
and watch `offset` add up. `verify` runs after every step and checks every
`f32` the walk reads against the field read directly, `l.power` and so on.
Then flip the switch at the top, `use_record_offsets`, to `0` and run it
again. The walk adds up the sizes before each field instead, as if nothing
had padding: `power` is read from offset 1, three padding bytes and one byte
of the real `power`, and writing `at.x` lands on `power`. The record printed
above it still says 4.

## Do reps: the kata

You write the walk, over the compiler's records, `reflect` and
`reflect_field` from `std/reflect.rin`. First, every field a tool shows, by
path, walking into the ones that are structs:

```rin
walk_leaves: proc(arena: *memops_arena, type: *const reflect, prefix: ^const char, base: u64,
                  out: *vec<walk_leaf>) -> void = {
    fields: ^const reflect_field = reflect_fields(type);
    for (i: u64 = 0; i < reflect_field_count(type); i += 1) {
        f: *const reflect_field = fields[i]&;
        if (reflect_field_has_attr(f, "hidden")) {
            continue;
        }
        leaf: walk_leaf = { .offset = base + f*.offset, .size = f*.size };
        path: fmt = fmt_to(leaf.path.text);
        fmt_cstr(path&, prefix);
        fmt_cstr(path&, f*.name);
        if (reflect_is_struct(f*.info)) {
            fmt_char(path&, '.');
            walk_leaves(arena, f*.info, path.data, leaf.offset, out);
        } else {
            _ = vec<walk_leaf>append(arena, out, leaf);
        }
    }
}
```

and on it and on a walk down one path, `walk_find`, the procs the harness
calls:

```rin
walk_paths: proc(arena: *memops_arena, type: *const reflect) -> vec<walk_path> = {
```

```rin
walk_diff: proc(arena: *memops_arena, type: *const reflect, a: []const u8, b: []const u8) -> vec<walk_path> = {
```

```rin
walk_get_f32: proc(type: *const reflect, bytes: []const u8, path: ^const char) -> option<f32> = {
```

```rin
walk_set_f32: proc(type: *const reflect, bytes: []u8, path: ^const char, value: f32) -> b32 = {
```

A path is a `walk_path`, 48 characters at most, ending in a zero. A hidden
field is left out of `walk_paths` and `walk_diff`, with everything inside
it, but a path still reaches it: hiding is for tools that list, not for code
that asks by name. `walk_get_f32` and `walk_set_f32` refuse a path that names
a struct, a `u8`, or nothing.

| level | you write | target |
|---|---|---|
| 1 | `walk_leaves`, the walk, in an otherwise finished file | 4:00 |
| 2 | every proc body; the types and signatures are given | 15:00 |
| 3 | the whole file, from a blank page | 18:00 |

    python tools/dojo.py start reflect 2
    python tools/dojo.py reflect

The harness's test types have the traps in them: `lamp` has padding after
`on: u8`, `room` has a `lamp` inside it (paths three deep, offsets added
twice), and a hidden `draft: vec2`. It runs the playground's steps as a
scenario, then 20,000 random reads, writes and diffs of a `room` by path,
each checked against the same fields reached directly, `r.light.at.x` and so
on. The paths include ones that name a struct, a `u8`, or nothing:
`light.atx.x`, `corner.x.y`, `light.`. The seeds give the same runs as
rust-dod's dojo.

**rin notes.** rin's compiler writes the records; Rust's kata gets them from
a macro in its harness, the way 2.7 makes them, and has `paths` return
`Vec<String>` where this one fills a `vec<walk_path>` from the arena it's
given. The harness gives each fuzz operation a temporary arena mark, so what
a walk allocates is gone after it. A field's bytes are cut out with a slice,
`bytes[at..at + 4]`, so a wrong offset past the end stops a Debug build
instead of reading past the value.

**Level 4, variations.** The same harness, different insides:

- **`walk_find` by recursion**: find the field the first name names, and
  recurse into its record with the rest of the path.
- **Paths without a vec of leaves**: walk with a callback, a `proc(path:
  ^const char, offset: u64, f: *const reflect_field) -> void`, and let
  `walk_paths` and `walk_diff` each pass their own.
- **A tiny text format**: write a value as `path = value` lines and read it
  back. That's a save file and a network message. (Not checked by the
  harness; write your own test.)

## When it fails

    FAIL at operation 4 (seed 1): set_f32("light.", -50.25) returns true, it should return false
        debug it: build/dojo/reflect/harness --seed 1 --stop 4
        with a breakpoint on dojo_stop_here, which runs just before that operation

The name after the dot is empty, and it matched a field anyway: a name
compare that stops at the end of the shorter of the two finds `range` for
nothing, and `at` for `atx`. Run the harness under your debugger with those
arguments and a breakpoint on `dojo_stop_here`, then step through
`walk_find`, watching each name and offset. If it crashes instead, the
runner runs it again with `--trace 1` and prints the operation that was
running.
