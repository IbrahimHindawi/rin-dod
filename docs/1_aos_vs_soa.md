# 1. AoS vs SoA

`src/1.aos_vs_soa/aos_vs_soa.rin`

The same 262,144 particles, stored three times: as an array of 68-byte
`particle` structs (AoS), as seven arrays, one per field (SoA), and with
position and velocity split one step further into six arrays of `f32`, one per
coordinate (split). Sixty steps of movement run over each, and the program
checks that all three end with the same positions.

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

      movups (%r11,%rdi,4), %xmm4     four vx
      movups (%rcx,%rdi,4), %xmm5     four px
      mulps  %xmm1, %xmm4             vx * dt
      addps  %xmm5, %xmm4             px + vx * dt
      movups %xmm4, (%rcx,%rdi,4)     four px back

A layout is right for SIMD when its vector loop is mostly full-width loads,
math and stores. When it is mostly `movss`, `unpcklps` and `shufps`, the data
is fighting the registers.

Split is right for this loop, which runs over every particle in order. It is
wrong for a loop that reaches particles by index, where x, y and z in three
arrays are three trips to memory instead of one. Lesson 7 measures both kinds
of loop over four layouts.

## Timings

`--time` prints how long each layout took. Release builds, best of five runs,
on the 2.8 GHz Xeon these lessons were checked on, ms:

| build | AoS | SoA | split |
|---|---|---|---|
| clang `-O2` | 49.6 | 26.9 | 16.5 |
| clang `-O3` | 47.5 | 26.7 | 15.9 |
| clang `-O2 -mavx2 -mfma` | 47.9 | 18.6 | 13.0 |
| gcc `-O3` | 34.2 | 13.7 | 14.2 |
| gcc `-O2` | 46.1 | 21.3 | 44.3 |

The same loops with 8,192 particles, so everything stays in L2, and 1,920
steps so the work is the same:

| build | AoS | SoA | split |
|---|---|---|---|
| clang `-O2` | 24.1 | 25.6 | 11.9 |
| clang `-O2 -mavx2 -mfma` | 28.6 | 17.8 | 6.5 |
| gcc `-O3` | 12.7 | 12.0 | 8.9 |

- **In cache, split is the only layout SIMD helps much.** SoA and AoS come out
  about even in L2 on clang, as the instruction counts say they should.
- **From the 6 MB case, SoA's smaller footprint shows.** That machine has 33 MB
  of L3, so the data stays in cache between steps, but SoA and split still
  move a third of the bytes AoS does.
- **gcc `-O2` does not vectorize across particles at all,** so split, with six
  streams and nothing gained for them, is its slowest layout. gcc users want
  `-O3`. clang-cl, rin's default, is the clang rows.

The machine is shared; expect about 20 percent noise between runs. Debug
numbers are not worth comparing: every `positions[i]` is bounds checked
there.

For a Release build, set `build_type` to `"Release"` in `build.rin` and run
`rin build` again. Release defines `NDEBUG`, which compiles the bounds checks
out. Or compile the C that `tools/check.py` leaves in `build/check/aos_vs_soa/`
with `-O2 -DNDEBUG`.

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
  `-fno-tree-loop-vectorize`), and the SoA loop lost to the AoS one.
- **clang** vectorized the loop either way. Its check runs once per call, so
  removing it saves nothing that shows here.

**On Windows, one slice needs it too.** `move_aos` has a single slice, which
cannot overlap another, and it still takes `noalias`. Windows passes a slice
to a proc by reference, as a pointer to a copy, and clang-cl does not use C's
type rules to decide what can overlap (it matches MSVC). So, without the
promise, a float written through `ps` might be the slice's own pointer or
length, and the loop reads both again after every particle:

    mov   r8,qword ptr [rcx]                   ps.data, every particle
    movss xmm2,dword ptr [gravity]             gravity, every particle
    ...
    cmp   rdx,qword ptr [rcx+8]                ps.length, every particle

With `noalias` the compiler gets the pointer and the length once, in
registers, and the loop is 16 instructions instead of 19.

**And `gravity` is `static`.** A global that other files could reach is, to
gcc, something a write through a slice might change, even through a
`noalias` one, so gcc `-O3` put a run-time check in front of `move_split`'s
vector loop. `gravity: static f32` keeps it to this file, nothing takes its
address, and the check goes away. Passing it as a parameter would do the same.

The promise is checked in Debug. Pass `soa.positions` as both arguments to
`move_soa` and the Debug build stops before the loop runs:

    aos_vs_soa.rin:138: noalias parameters 'positions' and 'velocities' overlap

A Release build does not check. It runs on, and the lesson prints
`same result: no`.

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
5. Remove `noalias` from `move_soa` and build Release with gcc `-O3`. Compare
   `--time`, then compile with `-fopt-info-vec` and find "loop versioned for
   vectorization because of possible aliasing".
6. Remove `static` from `gravity`, build with gcc `-O3 -fopt-info-vec`, and
   find the same message for `move_split`.
7. Pass `soa.positions` as both arguments to `move_soa`. Run it in Debug,
   then in Release.
