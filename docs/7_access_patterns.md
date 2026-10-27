# 7. Layout follows access

`src/7.access_patterns/access_patterns.rin`

Lesson 1 found the layout SIMD wants: one array per float. This lesson asks
what that layout costs everywhere else. 1,048,576 bodies are stored four ways,
and two kinds of loop run over each, and the program checks that all four end
with the same positions.

## Two kinds of loop

**Stream**: every body, in order, the same math. Integration is the example:

    for (i: u64 = 0; i < px.length; i += 1) {
        px[i] += vx[i] * dt;
        ...
    }

The next body is always right after the last one, so the hardware prefetcher
has it ready, and SIMD can take four or eight at once if they sit side by
side.

**Lookup**: bodies picked by index, two at a time, in no particular order.
Contacts are the example, the way collision and constraints reach bodies:

    a: u64 = cast(cs[c].a, u64);
    b: u64 = cast(cs[c].b, u64);
    dx: f32 = px[b] - px[a];
    ...

Each body is somewhere else in memory. What matters is how many cache lines
one body's data sits in, because each one is a separate trip to memory. SIMD
does not help: there are no four neighbours to load at once.

## Four layouts

    aos      [ x y z vx vy vz m r ][ x y z vx vy vz m r ] ...      32 bytes a body
    columns  positions  [ x y z ][ x y z ][ x y z ] ...
             velocities [ vx vy vz ][ vx vy vz ] ...                 24 bytes a body
    split    px [ x x x x ... ]   py [ y y y y ... ]   pz ...  vx ...  vy ...  vz ...
    blocks   [ x0..x7 | y0..y7 | z0..z7 | vx0..vx7 | vy0..vy7 | vz0..vz7 ][ x8..x15 ...

- **aos** keeps everything about a body together, two fields neither loop
  uses included.
- **columns** is one array per component, each component a small struct. This
  is what an ECS table stores, and what lessons 2 to 6 use.
- **split** is one array per float, lesson 1's `move_split`.
- **blocks** is eight bodies at a time, each coordinate a run of eight floats.
  It is split cut into pieces of eight, with the pieces of one body kept near
  each other. The usual name is AoSoA, an array of structs of arrays.

The program prints how many 64-byte cache lines one body's position sits in:

    cache lines one lookup touches: aos 1.000, columns 1.125, split 3.000, blocks 2.000

A 12-byte `vec3` crosses a line boundary 2 times in 16, hence 1.125. In
split, x, y and z are in three different arrays. In a block, x and y share a
line and z is in the next.

## Measured

Release, clang `-O2`, best of three runs, on the 2.8 GHz Xeon these lessons
were checked on: 4 MB of L2, 33 MB of L3. The body count was changed in the
generated C for the first and last columns. At 65,536 bodies each layout fits
in L2; at the lesson's 1,048,576 each is about the size of L3; at 8,388,608
each is 192 to 256 MB and comes from RAM.

**Stream, ns per body:**

| layout | 65,536 | 1,048,576 | 8,388,608 |
|---|---|---|---|
| aos | 1.67 | 4.20 | 4.09 |
| columns | 1.68 | 2.08 | 2.88 |
| split | 0.93 | **1.30** | **1.66** |
| blocks | **0.70** | 1.62 | 2.79 |

**Lookup, ns per contact:**

| layout | 65,536 | 1,048,576 | 8,388,608 |
|---|---|---|---|
| aos | 5.03 | 26.27 | 50.35 |
| columns | **3.42** | **11.94** | **40.35** |
| split | 6.54 | 28.22 | 95.01 |
| blocks | 5.98 | 25.70 | 61.20 |

clang with `-mavx2 -mfma` and gcc `-O3` agree on the main points: split
streams fastest from RAM, columns look up fastest at every size, and split
looks up slowest from RAM. Where two numbers are within about 20 percent, the
order changes from build to build; gcc `-O3`, for one, streamed columns
fastest at a million bodies. The machine is shared; expect about 20 percent
noise.

What it says:

- **Split wins the stream and loses the lookup.** From RAM it streams 1.7
  times faster than columns, and looks up 2.4 times slower: three lines a
  body instead of one.
- **Columns win the lookup everywhere** and come second or third in the
  stream. AoS also has one line a body, but its bodies are 32 bytes, so the
  same lookups spread over more memory. At a million bodies, columns'
  positions are 12 MB and sit comfortably in L3; AoS spreads them over
  32 MB, about all of it.
- **Blocks are the compromise.** In L2 they streamed fastest of all, and a
  little behind split at a million bodies. They look up better than split at
  every size. From RAM their stream fell back to about columns' speed on this
  machine, which I have not explained.
- **Out of cache, a lookup costs ten to fifty times a streamed body.** From
  RAM, 40 to 95 ns a contact against 2 to 4 ns a body. Turning lookups into something closer to
  a stream, by sorting contacts or walking space in order, usually saves
  more than any layout choice.

## What the compiler makes of it

clang-cl `/O2`, Windows x64, from the object file:

| loop | bodies a pass | instructions a pass | shuffles |
|---|---|---|---|
| `integrate_aos` | 1 | 16 | 1 |
| `integrate_columns` | 4 | 77 | 30 |
| `integrate_split` | 4 | 20 | 0 |
| `integrate_blocks` | 8 | 37 | 0 |
| `integrate_split`, `/arch:AVX2` | 8 | 14 | 0 |
| `integrate_blocks`, `/arch:AVX2` | 8 | 14 | 0 |
| `contacts_columns` | 1 contact | 25 | 0 |
| `contacts_split` | 1 contact | 32 | 0 |

Blocks vectorize as cleanly as split: the inner loop over eight lanes is a
fixed-size loop over consecutive floats, which compilers turn into whole
registers. The contact loops are one contact a pass in every layout.

## In between

Engines that have both kinds of loop do one of these:

- **Blocks**, as above. One layout, decent at both.
- **Gather, work, scatter.** Storage stays in columns or AoS, good for
  lookups. The hot loop copies a batch of bodies into a wide layout, x's in
  one register and y's in another, does its math, and copies them back. The
  copy pays off when the same batch is worked on many times, as a constraint
  solver does over several iterations. Box2D v3 solves contacts this way, four
  or eight at a time.
- **Two layouts for two jobs.** A particle system that only ever streams
  stores split. The bodies that collision looks up stay in columns.

## How an ECS decides

An ECS does not decide where each float goes. **The component is the unit it
stores together**, and the programmer decides what a component is.

- **Tables.** kayan, Unity's entities, Bevy and flecs keep one table per
  archetype, with one column per component. That is this lesson's columns
  layout: an array per component, and each component's fields side by side
  inside it. Unity cuts its tables into 16 KB chunks, each holding every
  component array for as many entities as fit, which is close to blocks at
  the level of components.
- **Sparse sets.** EnTT stores each component in its own dense array with a
  lookup table from entity to index, and can keep several components in the
  same order ("groups") so a system over them streams. Bevy lets each
  component choose: table storage, or a sparse set for components added and
  removed often.
- **Systems are streams.** A system is a query and a kernel, as in lesson 6:
  the ECS finds the tables that match, and hands the kernel each table's
  columns. That stream over columns is the fast path every ECS is built for.
  Systems that say which columns they read and which they write are what lets
  a scheduler run them in parallel.
- **Lookups go through the handle.** Reaching one entity is handle, slot,
  table and row, then the column: `kayan_get` in lesson 4. That is this
  lesson's lookup loop with an extra hop in front. ECS code keeps lookups for
  the places that need them, such as relationships between entities and
  collision, and finds the rest by query.

So the decisions that are yours:

1. **Keep components small**, to what one stream system reads. A component a
   system reads half of is AoS's wasted bytes again.
2. **Leave components as small structs**, `position { x, y, z }`, unless a
   profiler shows a stream over them is the bottleneck. They are the best
   layout for lookups and good enough for most streams.
3. **For a hot stream over huge counts,** particles above all, store split or
   blocks, or gather into them for the hot loop.
4. **Make lookups rarer and less random** before tuning their layout.

## Try

1. Sort `cs` by `a` before the timing loops and run `--time` again. Which
   lookup numbers change, and by how much?
2. Set `body_count` and `contact_count` to 8388608 and run `--time` in
   Release. Compare with the tables above.
3. Make the contacts push velocities too, `vx`, `vy` and `vz` of both
   bodies. How many lines does a lookup touch in each layout now?
4. Add `/arch:AVX2` to `build_c_flags` and compare the stream column.
5. Write `contacts_gather`: for every eight contacts, copy the sixteen bodies'
   positions into `[8]f32` arrays, do the arithmetic over the arrays, and copy
   back. Contacts that share a body in the same eight break it; find the case
   and decide what to do about it.
6. Make `body` 64 bytes with fields neither loop uses, and watch aos in both
   tables.
