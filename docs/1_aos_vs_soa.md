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

With `--time` it also prints how long each took. Release builds, best of five
runs, on the 2.8 GHz Xeon these lessons were checked on:

| build | AoS ms | SoA ms | SoA faster by |
|---|---|---|---|
| gcc `-O2` | 54.6 | 21.3 | 2.6x |
| gcc `-O3` | 34.1 | 13.4 | 2.5x |
| clang `-O2` | 47.1 | 26.5 | 1.8x |
| clang `-O3` | 45.3 | 26.3 | 1.7x |

That machine has 33 MB of L3, so the 6 MB the SoA loop reads stays in cache
between steps. The machine is shared; expect about 20 percent noise between
runs. Debug numbers are not worth comparing: every `positions[i]` is bounds
checked there.

For a Release build, set `build_type` to `"Release"` in `build.rin` and run
`rin build` again. Release defines `NDEBUG`, which compiles the bounds checks
out. Or compile the C that `tools/check.py` leaves in `build/check/aos_vs_soa/`
with `-O2 -DNDEBUG`.

## The parameter list is the data

`move_aos(ps: []particle, ...)` says it needs particles. `move_soa(positions:
noalias []vec3, velocities: noalias []vec3, ...)` says exactly which data it
reads and writes. In lessons 2 and 3 every system is written the second way. In lesson
6 each system runs its own query, then works only on the columns it named.

Naming the columns is what lets a scheduler see that two systems touch
different data, and it is what makes a system easy to test: hand it two
small arrays.

## noalias

As far as the C compiler can tell, two `[]vec3` slices could overlap. So
before it works on several particles at once, it checks at run time that the
two are apart, and keeps a one-at-a-time copy of the loop for when they are
not. `noalias` on a parameter promises that, for the call, nothing else
reaches the memory behind it. The check and the second copy go away.

The SoA loop without and with it, Release, ms:

| build | without `noalias` | with `noalias` |
|---|---|---|
| gcc `-O3` | 31.7 | 13.4 |
| gcc `-O2` | 20.5 | 21.3 |
| clang `-O2` | 26.3 | 26.5 |

- **gcc `-O3`** is where it shows. Without the promise, its checked vector
  loop was slower than not vectorizing at all (21 ms with
  `-fno-tree-loop-vectorize`), and the SoA loop lost to the AoS one. With it,
  this is the fastest number in the lesson.
- **clang** vectorized the loop either way. Its check runs once per call, so
  removing it saves nothing that shows here.
- **gcc `-O2`** does not work on several particles at once either way.

The promise is checked in Debug. Pass `soa.positions` as both arguments and
the Debug build stops before the loop runs:

    aos_vs_soa.rin:116: noalias parameters 'positions' and 'velocities' overlap

A Release build does not check. It runs on, and the lesson prints
`same result: no`.

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
   parameter list should say so, `noalias` included.
5. Remove `noalias` from `move_soa` and build Release with gcc `-O3`. Compare
   `--time`, then compile with `-fopt-info-vec` and find "loop versioned for
   vectorization because of possible aliasing".
6. Pass `soa.positions` as both arguments to `move_soa`. Run it in Debug,
   then in Release.
