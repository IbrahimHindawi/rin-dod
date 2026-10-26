# 1. AoS vs SoA

`src/1.aos_vs_soa/aos_vs_soa.rin`

The same 262,144 particles, stored twice: once as an array of 68-byte
`particle` structs, once as seven arrays, one per field. Sixty steps of
movement run over each, and the program checks that both end with the same
positions.

## What the loop fetches

Memory reaches the CPU in 64-byte cache lines. A loop that reads 24 bytes of
each 68-byte particle still pulls every byte of every line those particles
sit in, so about two thirds of what movement fetches in the AoS loop is tint,
age, lifetime, size and name. In the SoA loop the two arrays it reads are the
only thing it fetches, and the hardware prefetcher sees two simple streams.

The program prints that arithmetic:

    bytes fetched per step: 17825792     (AoS: 68 bytes x 262144)
    bytes fetched per step: 6291456      (SoA: 24 bytes x 262144)

With `--time` it also prints how long each took. In a Release build of this
lesson the SoA loop ran two to five times faster than the AoS one, on the
machine these lessons were checked on. Debug numbers are not worth comparing:
every `positions[i]` is bounds checked there.

For a Release build, set `build_type` to `"Release"` in `build.rin` and run
`rin build` again. Release defines `NDEBUG`, which compiles the bounds checks
out. Or compile the C that `tools/check.py` leaves in `build/check/aos_vs_soa/`
with `-O2 -DNDEBUG`.

## The parameter list is the data

`move_aos(ps: []particle, ...)` says it needs particles. `move_soa(positions:
[]vec3, velocities: []vec3, ...)` says exactly which data it reads and
writes. In lessons 2 and 3 every system is written the second way. In lesson
6 each system runs its own query, then works only on the columns it named.

Naming the columns is what lets a scheduler see that two systems touch
different data, and it is what makes a system easy to test: hand it two
small arrays.

## When AoS is right

When the code that touches a record touches most of its fields, AoS fetches
nothing wasted, and keeping a record together is simpler. Data-oriented
design does not mean SoA everywhere. It means choosing the layout from the
loops that run over it. An entity component system is the case where many
small loops each touch a few fields.

## Try

1. Run with `--time` in Release. Then remove `tint`, `age`, `lifetime` and
   `name` from `particle` and run again. The AoS loop should close most of
   the gap, because the struct shrinks toward what the loop reads.
2. Go one step further than SoA: split `positions` into `xs`, `ys` and `zs`,
   arrays of `f32`, and the same for velocities. Write `move_split` and
   compare. Each loop is now a straight line over floats, which is the shape
   a compiler can vectorise.
3. kayan stored positions as 16-byte `vec4s`. Change `vec3` to four floats
   and see what it does to the bytes-per-step line and to the timing.
4. Add a `fade_soa` system that only reads `ages` and writes `tints`. Its
   parameter list should say so.
