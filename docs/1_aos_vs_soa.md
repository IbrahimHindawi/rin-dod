# 1. AoS vs SoA

`src/1.aos_vs_soa/aos_vs_soa.rin`

The same 262,144 particles, stored three times: as an array of 68-byte
`particle` structs (AoS), as seven arrays, one per field (SoA), and with
position and velocity split one step further into six arrays of `f32`, one per
coordinate (split). Sixty steps of movement run over each, and the program
checks that all three end with the same positions.

## Where the particles live

All three layouts are in one region. A region is an arena the compiler can see:

    level: region;

Each array is a slice, and a slice kept in memory says which region holds its
elements:

    particles: struct = {
        positions: []vec3 in level;
        velocities: []vec3 in level;
        ...
    }

`main` opens the region, and `new_slice` is an arena push that keeps the length:

    level: region = {
    aos: []particle in level = new_slice<particle>(level, particle_count);
    soa: *particles in level = new<particles>(level, {
        .positions = new_slice<vec3>(level, particle_count),
        ...
    });

Everything lives exactly as long as that block. Nothing is freed one at a time,
and the checker will not let a pointer into `level` outlive the closing brace.
The movement procs take plain slices and know nothing about any of this.

## What the loop fetches

Memory reaches the CPU in 64-byte cache lines. A loop that reads 24 bytes of
each 68-byte particle still pulls every byte of every line those particles
sit in, so about two thirds of what movement fetches in the AoS loop is tint,
age, lifetime, size and name. In the SoA loop the two arrays it reads are the
only thing it fetches, and the hardware prefetcher sees two simple streams.
The split loop fetches the same 24 bytes per particle as SoA, as six streams.

The program prints that arithmetic:

    bytes fetched per step: 17825792     (AoS: 68 bytes x 262144)
    bytes fetched per step: 6291456      (SoA: 24 bytes x 262144)
    bytes fetched per step: 6291456      (split: 6 x 4 bytes x 262144)

## What the CPU does with each layout

SSE registers hold four floats, AVX registers eight. One instruction adds four
(or eight) pairs of floats at once, but only if they arrive side by side. Here
is what clang-cl `/O2` makes of each loop for Windows x64, read from the object
file:

| loop | particles per pass | instructions per pass | per particle | shuffles |
|---|---|---|---|---|
| `move_aos` | 1 | 16 | 16 | 1 |
| `move_soa` | 4 | 77 | about 19 | 30 |
| `move_split` | 4 | 20 | 5 | 0 |
| `move_split`, `/arch:AVX2` | 8 | 14 | under 2 | 0 |

- **AoS** goes one particle at a time: each particle's fields are 68 bytes
  from the next particle's, so there is nothing to load four of.
- **SoA** is vectorized, four particles per pass, but each `vec3` keeps x, y
  and z side by side. To get four x's into one register the compiler loads
  them one float at a time and stitches them together, then takes them apart
  again to store. About a tenth of the loop is arithmetic, and per particle it
  costs about what AoS does.
- **Split** is what SIMD wants. Each line of `move_split` becomes one load of
  four consecutive floats, one multiply, one add, one store:

      movups (%r10,%rsi,4), %xmm4     four vx
      movups (%r8,%rsi,4), %xmm5      four px
      mulps  %xmm1, %xmm4             vx * dt
      addps  %xmm5, %xmm4             px + vx * dt
      movups %xmm4, (%r8,%rsi,4)      four px back

A layout is right for SIMD when its vector loop is mostly full-width loads,
math and stores. When it is mostly `movss`, `unpcklps` and `shufps`, the data
is fighting the registers.

Split is right for this loop, which runs over every particle in order. It is
wrong for a loop that reaches particles by index, where x, y and z in three
arrays are three trips to memory instead of one. Lesson 7 measures both kinds
of loop over four layouts.

## The bounds checks

Every `positions[i]` is bounds checked, in every build, Release included. The
safety rules rest on it, so it does not hang on `NDEBUG`. A check is a compare
and a branch to a call that never returns, in the middle of a loop that wants
to do four particles at once, so you would expect it to cost the vector loop.

On clang it does not. The table above is with the checks on, and the passes
are the same with them off. The compiler sees that the loop runs `i` up to
`px.length`, works out before the loop how many full passes fit inside every
column's length, runs the vector loop for those with no checks in it, and
leaves the rest to a one-at-a-time loop that does check. A column shorter than
`px` stops the program there, with a message. What the checks add to
`move_split` is around the loop: 257 instructions in the whole proc instead of
79, and 27 in the one-at-a-time loop instead of 17.

gcc does not do this for `move_soa` or `move_split`. With the checks on,
`-fopt-info-vec` reports no vector loop over either, and split, the layout
that needs one most, is its slowest. `-DRIN_NO_BOUNDS_CHECKS` removes the checks
and brings the vector loop back, as the timings below show. A program built that
way has given up rin's guarantee. Try 8 is the other way, which keeps it.

## Timings

`--time` prints how long each layout took. Release builds on one core, best of
five runs, on a Ryzen 9 9950X3D: 1 MB of L2 a core and 96 MB of L3. clang-cl 22 on
Windows, gcc 16 under WSL on the same machine. Each run did ten times the work
and is divided by ten, because `clock()` on Windows ticks in milliseconds. ms for
sixty steps:

| build | AoS | SoA | split |
|---|---|---|---|
| clang-cl `/O2` | 12.2 | 10.8 | 6.7 |
| clang-cl `/O2 /arch:AVX2` | 9.8 | 7.2 | 5.5 |
| gcc `-O3` | 31.4 | 11.6 | 26.5 |
| gcc `-O2` | 12.5 | 11.2 | 27.5 |
| gcc `-O3 -DRIN_NO_BOUNDS_CHECKS` | 55.4 | 9.0 | 4.8 |
| gcc `-O2 -DRIN_NO_BOUNDS_CHECKS` | 9.9 | 8.5 | 4.4 |

The clang-cl rows do not change with `-DRIN_NO_BOUNDS_CHECKS`, beyond the noise,
and clang `-O3` is the same as `-O2`.

The same loops with 8,192 particles, so everything stays in L2, and 1,920
steps so the work is the same:

| build | AoS | SoA | split |
|---|---|---|---|
| clang-cl `/O2` | 11.8 | 9.9 | 4.5 |
| clang-cl `/O2 /arch:AVX2` | 9.2 | 5.7 | 3.9 |
| gcc `-O3` | 30.7 | 11.6 | 10.6 |
| gcc `-O3 -DRIN_NO_BOUNDS_CHECKS` | 53.4 | 8.9 | 2.7 |

And with 2,097,152 particles and 7.5 steps' worth, so the work is the same again.
AoS, at 143 MB, no longer fits in L3:

| build | AoS | SoA | split |
|---|---|---|---|
| clang-cl `/O2` | 27.9 | 10.8 | 7.9 |
| clang-cl `/O2 /arch:AVX2` | 28.0 | 8.2 | 6.0 |

- **In cache, split is the only layout SSE helps much.** SoA and AoS come out
  about even in L2 on clang-cl, as the instruction counts say they should.
  AVX2's eight-float registers help SoA too.
- **Out of cache, the bytes show.** At 262,144 particles all three sit in this
  machine's 96 MB of L3, and AoS fetching three times the bytes costs little. At
  2,097,152, AoS has left L3 and takes more than twice as long, while SoA and
  split, at 50 MB, are where they were. How much the layout matters here depends
  on the size of the cache you run on.
- **gcc's AoS at `-O3` is the odd one.** Two and a half to five times its `-O2`,
  and it is the loop vectorizer: `-fno-tree-loop-vectorize` brings it back to about
  12 ms. It vectorizes the loop with 8-byte vectors, and I have not explained why
  that is so slow on this machine.

The machine was busy; expect about 20 percent noise between runs, more for AoS,
which came out up to twice as slow in unlucky runs. Debug numbers are not worth
comparing: nothing is optimized there, and every check is a function call.

For a Release build, set `build_type` to `"Release"` in `build.rin` and run
`rin build` again. Release optimizes and defines `NDEBUG`, and the checks stay.
To take them out, add `"RIN_NO_BOUNDS_CHECKS"` to `build_defines`, or compile the
C that `tools/check.py` leaves in `build/check/aos_vs_soa/` with
`-O2 -DRIN_NO_BOUNDS_CHECKS`.

## The parameter list is the data

`move_aos(ps: noalias []particle, ...)` says it needs particles.
`move_soa(positions: noalias []vec3, velocities: noalias []vec3, ...)` and
`move_split(px, py, pz, vx, vy, vz, ...)` say exactly which data they read and
write. In lessons 2 and 3 every system is written that way. In lesson 6 each
system runs its own query, then works only on the columns it named.

Naming the columns is what lets a scheduler see that two systems touch
different data, and it is what makes a system easy to test: hand it two
small arrays.

## noalias

As far as the C compiler can tell, two `[]vec3` slices could overlap. So
before it works on several particles at once, it checks at run time that the
two are apart, and keeps a one-at-a-time copy of the loop for when they are
not, or it does not vectorize at all. `noalias` on a parameter promises that,
for the call, nothing else reaches the memory behind it. The check and the
second copy go away.

**It is a promise the checker cannot keep**, so it lives in code marked for it.
A proc with a `noalias` parameter is `proc[unsafe]`:

    move_soa: proc[unsafe](positions: noalias []vec3, velocities: noalias []vec3, dt: f32) -> void = {

and a call to it sits in `unsafe { }`:

    unsafe { move_soa(soa*.positions, soa*.velocities, dt); }

Take the `[unsafe]` off and rin stops:

    noalias is a promise to the C optimiser that the checker cannot keep: it belongs on a 'proc[unsafe]'

So the three movement kernels are outside what the checker vouches for. That is
the trade, and it is yours to make per kernel: take off both `noalias` and
`[unsafe]`, and the same loop is checked like everything else, at the cost below.

The SoA loop without and with it, Release, ms:

| build | without `noalias` | with `noalias` |
|---|---|---|
| clang-cl `/O2` | 23.2 | 10.8 |
| clang-cl `/O2 -DRIN_NO_BOUNDS_CHECKS` | 10.8 | 10.8 |
| clang `-O2`, Linux | 9.9 | 11.0 |
| gcc `-O3` | 11.8 | 11.6 |
| gcc `-O3 -DRIN_NO_BOUNDS_CHECKS` | 9.1 | 9.0 |

- **clang-cl** is where it shows. Without the promise it does not vectorize
  `move_soa` at all, and with the checks on it reads both slices from memory
  on every pass: one particle, 47 instructions. Without the checks it is 26
  instructions and costs what the vector loop does, since four `vec3`s gain
  little from SSE anyway.
- **clang on Linux** vectorized the loop either way. Without the promise it
  checks once per call, so removing the check saves nothing that shows here.
- **gcc** puts the loop behind a run-time check only when the bounds checks are
  gone and it vectorizes at all: "loop versioned for vectorization because of
  possible aliasing". The promise removes the check, and it does not show here
  either.

**On Windows, one slice needs it too.** `move_aos` has a single slice, which
cannot overlap another, and it still takes `noalias`. Windows passes a slice
to a proc by reference, as a pointer to a copy, and clang-cl does not use C's
type rules to decide what can overlap (it matches MSVC). So, without the
promise, a float written through `ps` might be the slice's own pointer or
length, and the loop reads both again after every particle:

    movq   (%rcx), %r8                         ps.data, every particle
    ...
    cmpq   0x8(%rcx), %rdx                     ps.length, every particle

With `noalias` the compiler gets the pointer and the length once, in
registers, and the loop is 16 instructions instead of 18.

**And `gravity` is a `const`.** rin computes a constant and hands C the number,
so the loops say `-(9.8f)` and there is no variable for a write to change:

    gravity: static const f32 = -9.8;

A plain global is different. `gravity: f32 = -9.8;` is something other files
could reach, and to gcc that is something a write through a slice might change,
even through a `noalias` one, so gcc `-O3` without the bounds checks puts a
run-time check in front of `move_split`'s vector loop. `static f32` keeps it to
this file, nothing takes its address, and the check goes away. Passing it as a
parameter would do the same, which is what `dt` does.

The promise is checked at run time, in every build. Pass `soa*.positions` as both
arguments to `move_soa` and the program stops before the loop runs:

    aos_vs_soa.rin:153: noalias parameters 'positions' and 'velocities' overlap

That is one check per call, not per particle. Only `-DRIN_NO_BOUNDS_CHECKS` turns
it off. That build runs on, and the lesson prints `same result: no`.

## Fused multiply-add

With `-mfma`, `-march=native` or clang-cl's `/arch:AVX2`, clang fuses
`p + v * dt` into one instruction that rounds once instead of twice. All
three layouts are fused the same way and still agree, but the checksum's last
digits move, from `38572460.505` to `38572460.519`, and the byte-for-byte
check against `aos_vs_soa.expected` fails. `tools/check.py` builds without
those flags.

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
2. Add `/arch:AVX2` to `build_c_flags` and compare `--time`. Then read
   `move_split` in the disassembly: eight floats per register, and `vfmadd`.
3. kayan stored positions as 16-byte `vec4s`. Change `vec3` to four floats
   and see what it does to the bytes-per-step line, to `move_soa`'s
   disassembly and to the timing.
4. Store the split columns in blocks of eight, `{ x: [8]f32; y: [8]f32; ... }`,
   and write the loop over blocks. Each block is a whole AVX register per
   coordinate, and a particle's coordinates stay near each other.
5. Remove `noalias` from `move_soa` and build Release with gcc
   `-O3 -DRIN_NO_BOUNDS_CHECKS`. Compare `--time`, then compile with
   `-fopt-info-vec` and find "loop versioned for vectorization because of
   possible aliasing". Then take off `[unsafe]` and the `unsafe { }` around its
   call, and read what clang-cl makes of a kernel the checker can vouch for.
6. Change `gravity` to a plain `gravity: f32 = -9.8;`, build with gcc
   `-O3 -DRIN_NO_BOUNDS_CHECKS -fopt-info-vec`, and find the same message for
   `move_split`. Then make it `static f32`.
7. Pass `soa*.positions` as both arguments to `move_soa`. Run it in Debug, in
   Release, then with `-DRIN_NO_BOUNDS_CHECKS`.
8. Get gcc's vector loop back with the checks on. At the top of `move_split`,
   cut every column to one length, `ys: []f32 = py[0..px.length];` and so on,
   and loop over those. gcc can now see that one bound covers them all, and it
   vectorizes, behind an overlap check, since the cuts carry no `noalias`. Split
   goes from 26.5 ms to about 8 on gcc `-O3`, a column that is too short stops
   the program at the cut, before the first particle, and nothing has been given
   up.
