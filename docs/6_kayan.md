# 6. kayan

`src/6.kayan/kayan.rin`

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

## The buffer

    command: struct = { kind; entity; pending; signature; id; payload; }

Spawned entities have no handle until the buffer runs, so `commands_spawn`
returns a `pending` number, and `commands_set_spawned<T>` writes a component
into "the entity that pending spawn will create". T has to be in the spawn's
signature, and applying the buffer stops the program with a message if it is
not. Payloads are copies of the component value, kept as a `[]u8` in the
buffer's frame arena next to the commands. `commands_apply` runs everything
in order, then clears the arena. One `memops_arena_clear` frees the whole
frame's commands.

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
   The first difference is at frame 56: the program reports drone 3:1
   destroyed, but the drone it removed was 1:1. Explain why, from the
   swap-remove and the slices the loop is holding.
2. Make `blast_system` skip neighbours whose health is already at or below
   zero. The skip count drops to zero. Is the buffer's check still needed?
3. Give the turret a `health` component and let leaking drones damage it.
   When it reaches zero, despawn it through the buffer and end the game.
4. Print the buffer before applying it, as a log of every structural change
   the frame made.
5. Run with `--sanitize` after each change. A stale slice into a grown table
   is exactly what AddressSanitizer does not catch, because the old memory
   is still valid arena memory. Think about what would.
