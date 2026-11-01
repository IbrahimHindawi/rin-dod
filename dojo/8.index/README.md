# 8. Index, not pointer

`dojo/8.index/play_index.rin`

A linked list whose nodes live side by side in one vec, and link to each other
by **index**: node 1's `next` is 0, a position in the vec, not an address.
When the vec is full and grows, it moves: the nodes are copied to a bigger
place, and the old one is let go. Every index is still right after the move,
because an index says where a node is *in the vec*, wherever the vec is. A
pointer says where the node is in memory, so it still points at the old
place, and nothing tells you.

That's the whole idea, and it's everywhere in data-oriented code: an ECS
keeps an entity's row by number because a growing column moves its rows, a mesh
keeps triangles as three vertex indices, a scene graph keeps a parent index.
A freed node goes on a free list and is used again before the vec grows, as
in dojo 1.

**The invariant:** walking `next` from the head visits every live node once
and ends at the tail; each node's `prev` is the node before it; and a node's
index names it from the moment it's made until it's removed, however many
times the vec moves in between.

In the course: [2.4](../../ecs/docs/2.4_archetypes.md) keeps an entity's table
and row as numbers in its slot. It's why a pointer into
[2.2](../../ecs/docs/2.2_columns.md)'s columns goes stale when a column grows,
and why [2.5](../../ecs/docs/2.5_typed_access.md) says to keep handles and
borrow pointers only to use them. The tables themselves are level pointers in
a vec, so the vec can grow without moving a table: the other way out, for a
thing that never has to move.

## Watch it: the playground

    python tools/dojo.py play index

Memory in the playground is an array of 16 cells, small enough to see whole
in a debugger, and the list takes 2 cells of it, then 4, then 8. It keeps node
`b` two ways: by its index, and by a `*node` to its cell. Then the list fills
up and moves, and the program writes to `b`:

```
push_back 30 as c: the list is full
    the list moves from cells 0..2 to cells 2..6
    c is node 2
...
write 21 into b through its index, 1: cell 3 now
    nodes    0: 10, prev -, next 1 | 1: 21, prev 0, next 2 | 2: 30, prev 1, next -
    list     10 21 30
    memory   0..2 old copy: 10 20 | 2..6 the list: 10 21 30 .
```

After every step `verify` walks the links and checks that every node holds
what the program last wrote to it. Put a breakpoint on `broken`, which it
calls when something is wrong.

Then break on the line that writes 21 into `b`, set `use_index` to `0` in the
watch window, and continue. The write goes through the kept pointer, into the
old copy, and the list never sees it:

    write 21 into b through what was kept, cell 1: where b was before the move
        ...
        memory   0..2 old copy: 10 21 | 2..6 the list: 10 20 30 .
        verify: node 1 holds 20, but the program last wrote 21 to it

Nothing crashes, and AddressSanitizer stays quiet too: the old copy is still
memory the program owns, as a region's old blocks are until the region ends. The
write is simply lost. The checker lets the playground keep that pointer because
its cells are a fixed array inside the list, so to it nothing has moved. In the
kata the nodes are in a vec, and it won't.

## Do reps: the kata

You write `list`, made in the region `level`, with `nodes` and `free` each a
`*vec<...> in level`. The idea is in `list_remove`: the two neighbours link to
each other, past the node, and the node's index goes on the free list. The
node's fields are read first, and it is marked free, before the calls that touch
other nodes, since each of those ends what `n` may be used for:

```rin
list_remove: proc(l: *list, node: u32) -> option<u64> = {
    n: option<*list_node> = list_live(l, node);
    if (!n) {
        return option<u64>none();
    }
    prev: u32 = n*.prev;
    next: u32 = n*.next;
    value: u64 = n*.value;
    n*.alive = 0;
    if (prev != list_none) {
        list_at(l, prev)*.next = next;
    } else {
        l*.head = next;
    }
    if (next != list_none) {
        list_at(l, next)*.prev = prev;
    } else {
        l*.tail = prev;
    }
```

and the playground's lesson is one the checker holds you to, in
`list_insert_after`:

```rin
// A new node between `node` and the one after it; list_none if `node` isn't
// in the list. Every pointer into the nodes is taken after list_take, which
// can move them.
list_insert_after: proc(l: *list, node: u32, value: u64) -> u32 = {
```

plus `list_make(r)`, which sets `head` and `tail` to `list_none`,
`list_push_back`, `list_push_front`, `list_get`, `list_len`, and the links to
walk the list by: `list_head`, `list_tail`, `list_next` and `list_prev`. A
link past either end is `list_none`, the largest u32, which no node ever gets.

| level | you write | target |
|---|---|---|
| 1 | `list_remove`, in an otherwise finished file | 3:00 |
| 2 | every proc body; the fields and signatures are given | 12:00 |
| 3 | the whole file, from a blank page | 15:00 |

    python tools/dojo.py start index 2
    python tools/dojo.py index

The harness runs the playground's steps as a scenario, then 20,000 random
pushes, inserts, removes, reads and writes against a model that keeps the
live nodes in list order. After every operation it walks your list both ways,
`list_head` to the end by `list_next`, and `list_tail` back by `list_prev`, so
a link left wrong is caught by the operation that left it. The list grows to
about a thousand nodes, moving many times, and every node is checked by the
index it was given. A freed index must be handed out again before a new one
is made. The seeds give the same runs as rust-dod's dojo.

**rin notes.** Rust's kata has `Option<u32>` links; here a link is a `u32`,
and `list_none` stands for none, as `UINT32_MAX` would in C. `list_get`
returns an `option<*u64 in level>`, a pointer that is null for a node not in
the list and tested before use, to read or to change the value; Rust's kata
has `get` and `get_mut`. Helpers that hand out a node say the same, `list_at`
a `*list_node in level` and `list_live` an `option<*list_node in level>`. The
checker refuses a result that comes out of a vec in `level` and doesn't say
so.

**Level 4, variations.** The same harness, different insides:

- **The free list through the nodes**: a freed node's `next` is the next
  free node, and the list keeps `first_free: u32`. No `free` vec.
- **A pointer kept across `list_take`**, which fails on purpose, twice: in
  `list_insert_after`, take `list_live(l, node)` once, before `list_take`,
  and write through it after. The checker stops it first: `'n' may be stale:
  'l', which it was taken from, has been changed since; take it again`. Now
  declare it `n: option<*list_node in level>`, a pointer good for as long as the
  region, which is true: the old block is still there. It builds. Which
  operation does the harness stop at, and where did the write go? Then put it
  back.
- **A list walker**: `list_each(l, visit)`, with `visit` a `*proc(node: u32,
  value: u64) -> void`, called head to tail. Read the next link before you
  call it: the checker counts a call through a proc pointer as one that may
  change the list. (Not checked by the harness; write your own test.)

## When it fails

    FAIL at operation 17 (seed 1): walking head to tail, list_next(3) gives 2, but 3 is the last of 3 nodes
        debug it: build/dojo/index/harness --seed 1 --stop 17
        with a breakpoint on dojo_stop_here, which runs just before that operation

A link pointing somewhere it shouldn't is usually a node from the free list
that kept its old links, or a neighbour that wasn't told about a change: an
insert at the tail that didn't move the tail, a remove that fixed `next` but
not `prev`, or a write through a pointer kept `in level` past a move. Run the
harness under your debugger with those arguments and a breakpoint on
`dojo_stop_here`, which runs just before that operation, and look at the nodes
the message names.

If the harness crashes instead, on a node past the end of the vec say, the
runner runs it again with `--trace 1` and prints the operation that was
running, or says the crash came in the scenario, after the last step printed.

An index alone can't tell a removed node from the new node that took its
place: `a` is node 0, and so is `e` after it. That's dojo 1's problem, and its
answer, a generation beside the index, works here unchanged.
