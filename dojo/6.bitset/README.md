# 6. Bitsets

`dojo/6.bitset/play_bitset.rin`

A set of small numbers, 0 to 63, fits in one `u64`: bit `id` is set when `id`
is in the set. An ECS keeps what each kind of entity is made of this way, a
**signature** with a bit per component, and a **query** as two sets: the ids
a table must have, and the ids it must not. The questions an ECS asks all day
are then one or two instructions each, however many components there are:

    with(set, id)            set | (1 shl id)
    without(set, id)         set & ~(1 shl id)
    has(set, id)             (set & (1 shl id)) != 0
    contains_all(set, all)   (set & all) == all
    intersects(set, none)    (set & none) != 0

The same trick is a file's permissions, which of 64 workers are idle, and
which chunks of a map are loaded.

**The invariant:** bit `id` is set exactly when `id` is in the set.
Everything else follows from it: one set contains all of another when masking
it with the other leaves the other whole, and two sets share an id when their
AND isn't zero.

In the course: [2.1](../../ecs/docs/2.1_components.md) gives each component a
bit and each kind of entity a signature, [2.4](../../ecs/docs/2.4_archetypes.md)
finds a table by its signature, [2.6](../../ecs/docs/2.6_add_remove.md) moves
an entity by setting or clearing one bit, and
[3.1](../../ecs/docs/3.1_queries.md) matches queries against tables with
`contains_all` and `intersects`.

## Watch it: the playground

    python tools/dojo.py play bitset

It gives five kinds of thing a signature each, draws them as rows of bits,
highest id first, and runs queries over them:

```
query move: all {position velocity}, none {frozen}
    all     00000011
    none    01000000
    player  00011111  matches
    drone   00001111  matches
    turret  00101101  no
    rock    00001001  no
    ghost   01001011  no
```

Read it by columns: a kind matches when it has a 1 under every 1 of `all`,
and a 0 under every 1 of `none`. Then the drone is frozen and the ghost
thaws, one bit each, and the same query gives a different answer. Each kind
keeps its ids twice, as a signature and as a `b32` per id, and `verify`
checks the fast answer against the slow one after every step.

Step through it: break on `matches`, and watch `set & wanted` in the watch
window, in binary. Then flip the switch at the top, `all_not_any`, to `0` and
run it again. `contains_all` now asks whether the signature has **any** of
the ids. The turret and the rock have a position, so both match the movement
query, and the turret and the ghost each have half of what the think query
wants:

```
    verify: turret matches, but it has no velocity
```

It's the most common bitset bug, and it compiles: the compiler has no idea
which question you meant.

## Do reps: the kata

You write procs over a `u64`. The one with the idea in it:

```rin
bitset_contains_all: proc(set: u64, wanted: u64) -> b32 = {
    return (set & wanted) == wanted;
}
```

and a query, built from it:

```rin
bitset_matches: proc(set: u64, all: u64, none: u64) -> b32 = {
    return bitset_contains_all(set, all) && !bitset_intersects(set, none);
}
```

plus `bitset_bit` (the set of `id` alone), `bitset_with`, `bitset_without`,
`bitset_has`, `bitset_intersects`, `bitset_count` and `bitset_ids`, which
writes the ids, smallest first, into a slice with room for 64 and returns how
many. Ids are `u32`s, 0 to 63.

| level | you write | target |
|---|---|---|
| 1 | `bitset_contains_all`, in an otherwise finished file | 1:00 |
| 2 | every proc body; the signatures are given | 5:00 |
| 3 | the whole file, from a blank page | 6:00 |

    python tools/dojo.py start bitset 2
    python tools/dojo.py bitset

The harness runs the playground's kinds and queries as a scenario, then
20,000 random operations on a set: adding and taking away ids, and asking
`has`, `contains_all`, `intersects`, `matches`, `count` and `ids`, against a
model that keeps a `b32` per id and answers one id at a time. The sets it
asks about are mostly made from the set itself: part of it, part of it plus
one more id, or ids it doesn't have, so the answers aren't nearly always
false. Ids go up to 63, so a shift done in 32 bits shows. The seeds give the
same runs as rust-dod's dojo.

**rin notes.** rin binds `&` tighter than `==`, as Rust does, so
`set & wanted == wanted` means what it says; in C it would be
`set & (wanted == wanted)`. The reference keeps the parentheses anyway, for
anyone reading it with C eyes. And rin gives a bare `1` the type its result
is going to, so in a proc that returns a `u64`, `1 shl id` is already a 64-bit
shift. The 32-bit bug needs a `u32` on the left, `one: u32 = 1; one shl id`,
and `--sanitize` names it: UBSan reports a shift exponent too large for a
32-bit type.

**Level 4, variations.** The same harness, different insides:

- **Count without a loop over 64**: `set & (set - 1)` clears the lowest set
  bit. Loop until the set is empty, one step per id rather than per bit.
- **`bitset_ids` the same way**: `low = set & (0 - set)` is the lowest set
  bit alone, its id is the number of bits below it, `bitset_count(low - 1)`,
  and clearing it moves on.
- **More than 64 components**: a struct of two `u64`s, with id `i` at bit
  `i % 64` of word `i / 64`, and the same procs. What does `contains_all`
  become? (Not checked by the harness; write your own test.)

## When it fails

    FAIL at operation 2 (seed 1): without({}, 57) gave {57}, it should give {}
        debug it: build/dojo/bitset/harness --seed 1 --stop 2
        with a breakpoint on dojo_stop_here, which runs just before that operation

That one is `set ^ bitset_bit(id)`: an XOR flips the bit, so taking away an
id the set doesn't have puts it in. Sets print as their ids, smallest first.
Run the harness under your debugger with those arguments and a breakpoint on
`dojo_stop_here`, which runs just before that operation.
