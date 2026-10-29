# 13. A dispatch table

`dojo/13.dispatch/play_dispatch.rin`

A frame is a list of systems run in order, and the list is **data**: a name
and a pointer to a proc for each, in an array the program changes as it runs.
Adding, removing, reordering or switching off a system is an edit to the
array, not to the code that calls them:

    schedule  0 move   1 shoot   2 damage   3 die
    a frame   for each enabled system, in order: entry.run(world)

The order is a statement about data: a system that **reads** what another
**writes** runs after it. `damage` writes health and `die` reads it, so
`damage` goes before `die`, and a drone dies in the frame its health runs
out. The same table drives an interpreter's opcodes, a menu's actions, a
network protocol's message handlers: a number or a name picks a proc.

**The invariant:** a run calls every enabled system once, in the list's
order, and nothing else. Edits keep the order of everything they don't
touch.

In the course: [3.2](../../ecs/docs/3.2_systems.md) makes a system a name, a
query and a proc pointer, and runs a schedule of them each frame, and
[3.4](../../ecs/docs/3.4_game.md)'s game has nine, each placed after what it
reads.

## Watch it: the playground

    python tools/dojo.py play dispatch

A drone flies at a turret. Four systems, `move`, `shoot`, `damage` and
`die`, run frame by frame, and between frames the program edits the
schedule: `shoot` is switched off while the turret reloads, back on, and
removed at the end. After each step it prints the schedule or the world:

```
frame 2
    ran       move shoot damage die
    drone     4 from the turret, health 60, alive
switch shoot off: the turret is reloading
    schedule  move (shoot off) damage die
frame 3
    ran       move damage die
```

Then `verify` checks that the drone is dead exactly when its health has run
out; break inside its `if` to stop when it fires. Step through it: break on
`schedule_run` and step into each call, through the pointer, into the
system.

Then flip the switch at the top, `in_order`, to `0`, and run it again.
`damage` is added at the end of the schedule instead of before `die`, so
`die` reads the health from before this frame's damage:

    frame 5
        ran       move shoot die damage
        drone     0 from the turret, health -20, alive
        verify: the drone has health -20 and is still alive

and it dies in frame 6, a frame late. A frame late is a drone that fires once
more after it should be dead, or a death sound one frame after the
explosion. The switch is a global, read when `damage` is added, so a
debugger can flip it too: stop on the first line of `main`, set it to 0 in
the watch window, and continue.

## Do reps: the kata

You write `schedule`. A system is a plain pointer to a proc, which takes the
harness's `ctx`:

```rin
system_proc: alias = *proc(c: *ctx) -> void;

schedule_system: struct = {
    name: ^const char;
    run: system_proc;
    enabled: b32;
    // How many times schedule_run has called it.
    calls: u32;
}
```

and the schedule is a vec of them, in the order they run:

```rin
schedule_insert_before: proc(s: *schedule, before: ^const char, name: ^const char, run: system_proc) -> b32 = {
```

```rin
schedule_run: proc(s: *schedule, c: *ctx) -> void = {
```

plus `schedule_init`, `schedule_add(s, name, run)` (at the end),
`schedule_remove(s, name)`, `schedule_set_enabled(s, name, on)`,
`schedule_len` and `schedule_name(s, i)` (every name, enabled or not, in
order), and `schedule_calls(s, name)`. `schedule_insert_before`,
`schedule_remove` and `schedule_set_enabled` return 0, and change nothing,
when there's no system by that name. Names are C strings, compared with
`strcmp`.

| level | you write | target |
|---|---|---|
| 1 | `schedule_run`, in an otherwise finished file | 2:00 |
| 2 | every proc body; the fields and signatures are given | 10:00 |
| 3 | the whole file, from a blank page | 15:00 |

    python tools/dojo.py start dispatch 2
    python tools/dojo.py dispatch

The harness has twelve systems, `input` to `save`, and each one writes its
name in the `ctx`'s log when it's called, so after a run the log says what
ran, in what order, and through which proc. It runs a short scenario, then
20,000 random adds, inserts, removes, enables, disables and runs against a
model that keeps the schedule as a plain list. After every operation the
order and every count must match the model, and every run must log exactly
the enabled systems, in order. The seeds give the same runs as rust-dod's
dojo.

**rin notes.** Rust's kata has `order()`, which returns the names as a Vec;
here `schedule_len` and `schedule_name` give them one at a time, so nothing
is allocated to read them.

**Level 4, variations.** The same harness, different insides:

- **A fixed array**: `[16]schedule_system` and a count instead of a vec, as
  the playground has. What happens on the seventeenth add?
- **Struct of arrays**: the names, the procs, the flags and the counts in
  four vecs, one place per system. `schedule_insert_before` and
  `schedule_remove` must move all four the same way.
- **Reads and writes**: each system declares bitmasks of what it reads and
  writes, and `schedule_insert_before` refuses a place where a system would
  read something a later one writes. Then: which neighbours could run at the
  same time, on two threads? (Not checked by the harness; write your own
  test.)

A system with data of its own is one more pointer beside the proc pointer,
handed back on every call: [3.4](../../ecs/docs/3.4_game.md)'s
`kayan_system` has a `ctx: *void` for that, which is what a closure is,
written out.

## When it fails

The scenario catches the common mistakes first:

    FAIL in the scenario: run: what ran gave move, it should give move damage die

That run stopped at the first disabled system, `collide`: a `break` where a
skip was meant. A failure in the fuzz run says where:

    FAIL at operation 110 (seed 1): after schedule_remove(die), schedule_calls(damage) is 0; the model counts 2 since it was added
        debug it: build/dojo/dispatch/harness --seed 1 --stop 110
        with a breakpoint on dojo_stop_here, which runs just before that operation

That kata kept the counts in a vec of their own, the struct of arrays above,
and `schedule_remove` popped the last count rather than the removed system's,
so the counts after it shifted one place. Run the harness under your
debugger with those arguments and a breakpoint on `dojo_stop_here`, then step
into `schedule_remove` and watch both vecs.

If the harness crashes instead, on a proc pointer that was never set, say,
the runner runs it again with `--trace 1` and prints the operation that was
running, or says the crash came in the scenario, after the last step printed.
