# 6. kayan

`src/6.kayan/kayan.rin`

**In the dojo:** [5. a command buffer](../dojo/5.commands/README.md), [7. an arena](../dojo/7.arena/README.md), each on its own, to watch and to practise.

A turret at the centre, five wings of three drones, 140 frames. Seven systems
run each frame, and every structural change they want goes through a command
buffer applied at the end of the frame.

## The frame

    spawner    wings of drones enter                    records spawns
    turret     shoot at the nearest drone               records spawns
    movement   position += velocity * dt                writes
    lifetime   bullets expire                           records despawns
    collision  live bullets against drones              writes health, records despawn and add
    burning    burning drones lose health               writes
    outcome    destroy dead drones, catch leaks         records despawns
      blast    a destroyed drone hurts its neighbours   writes health, records adds
    apply      every recorded change, in order

Writes to components happen in place, during queries. Changes to which table
an entity is in are recorded, and applied once nothing is iterating.

Lifetime runs before collision, and collision skips bullets whose lifetime is
used up. Those bullets are only still in their table because nothing
structural happens until the end of the frame. Without the skip, a bullet that
hit on its last frame would be despawned twice and counted as both a hit and
a miss.

The frame is a region inside `level`, declared `frame: region in level;` and
opened once per frame, around the systems and the apply:

    frame: region = {
        c: *commands in frame = commands_make(frame);
        spawner_system(g, c);
        turret_system(g, c, dt);
        movement_system(g*.world, dt);
        lifetime_system(g, c, dt);
        collision_system(g, c);
        burning_system(g*.world, dt);
        outcome_system(g, c);
        result: apply_result = commands_apply(c, g*.world);
        skipped += result.skipped;
    }

The world outlives every frame, so it is in `level`. The buffer belongs to one
frame, so it is made inside the block and passed to the systems beside the game.

## Systems and kernels

`movement_system` and `burning_system` are each a query and a kernel:

    integrate: proc[unsafe](ps: noalias []position, vs: []const velocity, dt: f32) -> void
    burn: proc[unsafe](hs: noalias []health, bs: []const burning, dt: f32) -> void

The system walks the tables and calls the kernel once for each table that
matches:

    unsafe { integrate(kayan_column<position>(t), kayan_column<velocity>(t), dt); }

The kernel sees two columns, so the compiler sees a straight loop over two
arrays. `noalias` qualifies parameters, so the loop needs a proc of its own to
carry it, and since `noalias` is a promise the checker cannot keep, that proc is
`proc[unsafe]`. The split is what keeps the promise small: the query around it
stays checked. The output does not change.

With the bounds checks compiled out, gcc `-O3` vectorized both loops behind a
run-time check that the columns were apart before the split, and without the check
after it. With the checks in, it vectorizes neither here, as lesson 1 says of gcc.
clang on Linux had no check either way, for the reason lesson 3 gives: the columns
are different types. clang-cl, which does not use C's type rules, needs `noalias`
here too.

`burn` is the cleanest loop in the game. `health` and `burning` are each one
`f32`, so their columns are plain runs of floats, and the kernel is eight
floats per pass with nothing to rearrange: loads, `mulps`, `subps`, stores.
`integrate` works on `vec2`s, both coordinates get the same math, and it is just
as clean at four `vec2`s per pass; lesson 1 shows what a `vec3` does to that, and
what the fully split layout looks like.

`integrate` and `burn` are streams: every row of every matching table, in
order. `collision_system` and `blast_system` are closer to lookups: for each
bullet or each blast, they visit drones that could be anywhere. Lesson 7
measures what each layout costs for both kinds of loop, and why the
components here stay small structs.

`lifetime_system` stays one proc. Its loop records a despawn for each expired
bullet, and a loop that calls something per row is not vectorized whatever
its parameters say. The other systems branch, search or record in their loops
too.

## Why not change tables during a query

Each of these would be a real bug with the world from lesson 4:

- **Despawn.** The swap-remove moves the last row into the hole, behind the
  loop, so that entity is not processed this frame. Meanwhile the slice the
  system cut before the despawn still reaches the old last row, a stale copy,
  and anything written to it is lost.
- **Spawn.** A table that is full grows, and its columns move to new memory.
  A system holding a `[]position` from before the spawn keeps writing to the
  old copy. Nothing crashes; the writes are just lost.
- **Add or remove.** The entity moves to another table, which the same query
  may reach later. That entity is processed twice this frame.

The checker catches the stale slices, the first two. It reads the body of a
checked proc to see what the proc can move. `kayan_spawn` and `kayan_despawn` can
grow or shrink what the world holds, so a column held across one is an error at
compile time. Put a `kayan_spawn` or a `kayan_despawn` in `lifetime_system`'s loop
and rin says:

    'ls' may be stale: 'g.world.tables', which it was taken from, has been changed since; take it again

`blast_system` and `nearest_drone` take the game or the world, but nothing in them
can move a table, so a column stays good across them. `turret_system` and
`outcome_system` take their columns again at the top of every pass all the same,
which is more than the checker asks today.

It does not catch the rest. Take the columns again as it says, and the loop
compiles, and you are back to visiting an entity twice or not at all, or to a
bounds check stopping the program: a wrong answer or a stop, not a memory error.
The checker rules out the lost write. The design rule, that nothing changes
structure during a query, is still yours.

## The buffer

    command: struct = { kind; entity; pending; signature; id; payload; }

Spawned entities have no handle until the buffer runs, so `commands_spawn`
returns a `pending` number, and `commands_set_spawned<T>` writes a component
into "the entity that pending spawn will create". T has to be in the spawn's
signature, and applying the buffer stops the program with a message if it is
not. Payloads are copies of the component value, kept as `[]u8 in frame` next to
the commands, and the commands themselves are `*vec<command> in frame`.
`commands_apply` runs everything in order. Nothing clears anything: the frame
region ends at its closing brace in `main`, and every command and payload go
with it.

So a command cannot outlive its frame, by construction. Try to keep the buffer in
the game, in a field that says `level`, and rin refuses:

    this points into region 'frame', which may end before the memory in region 'level' that holds it

Copying a component into bytes is the one unsafe act here, in `commands_payload`.
`commands_make` keeps the region's arena, and `commands_spawned` takes a block from
it. Everything else is checked. `write_component` copies a payload out with
`slice<u8>copy`, so both ends are slices and the copy cannot run off either. The
systems are checked too, but for their kernels' `noalias`.

## Skipped commands

Frame 113 is the interesting one. A bullet destroys one drone, and its blast
takes two burning neighbours below zero in the same loop. Each of them is
destroyed in turn, and each blast reaches back to drones already recorded as
destroyed:

    bullet 8:9 hits drone 6:1, health -13.2
    drone 6:1 is destroyed
    drone 7:1 is caught in the blast, health -14.4
    drone 4:2 is caught in the blast, health -4.8
    drone 7:1 is destroyed
    drone 6:1 is caught in the blast, health -54.0
    ...

The blast cannot know `6:1` is doomed: its despawn is only recorded, and it is
still in its table. So it records an `add<burning>` against it. When the
buffer is applied the despawn comes first, and `kayan_move` reports
`kayan_status.dead` for the add, so the command is skipped. The summary
counts three.

## Try

1. Call `kayan_despawn` directly in `outcome_system` instead of recording it.
   It compiles, because that loop takes its columns again each pass. Then the
   program stops at frame 56 with `index 1 out of bounds (length 1)`. Explain why,
   from the swap-remove and `drones_here`, the count the loop took before it
   started.
2. Make `blast_system` skip neighbours whose health is already at or below
   zero. The skip count drops to zero. Is the buffer's check still needed?
3. Give the turret a `health` component and let leaking drones damage it.
   When it reaches zero, despawn it through the buffer and end the game.
4. Print the buffer before applying it, as a log of every structural change
   the frame made.
5. Inline `integrate` back into `movement_system`, build with gcc `-O3
   -fopt-info-vec`, and find the loop it now versions for aliasing. It needs no
   `unsafe` now: without `noalias`, the checker can vouch for all of it.
6. Hold a column across a `kayan_spawn` that grows its table, and read the
   message. Then translate it with `RIN_UNSAFE=1`, which turns the rules off, and
   build it with AddressSanitizer, in a VM, since it misuses memory. AddressSanitizer
   says nothing, because the old memory is still valid memory in the region: a write
   through the held column lands there, and the table never sees it. That is why this
   is a rule in the checker: no sanitizer would have found it.
