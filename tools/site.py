"""Build website/index.html: every lesson's guide, source and expected output
as one page, from the files in this repository.

    python tools/site.py

Run it again after changing a lesson, a guide or website/template.html. The
page is self-contained apart from its web fonts, which fall back to system
faces offline.
"""

import html, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "website" / "index.html"

def esc(s): return html.escape(s, quote=False)

# ---------------------------------------------------------------- highlight
RIN_KW = set("proc struct enum union alias import cinclude return if else for while do switch case default break continue cast sizeof alignof null const static volatile noalias label goto shl shr".split())
RIN_TY = set("i8 i16 i32 i64 u8 u16 u32 u64 f32 f64 usize b8 b16 b32 b64 c8 char void long intptr uintptr ptrdiff".split())
RIN_TOK = re.compile(r"""
 (?P<com>//[^\n]*|/\*.*?\*/)
|(?P<str>"(?:\\.|[^"\\\n])*")
|(?P<num>0x[0-9A-Fa-f]+(?:'[a-z0-9]+)?|\d[\d_]*(?:\.\d+)?(?:'[a-z0-9]+)?)
|(?P<chr>'(?:\\.|[^'\\\n])')
|(?P<id>[A-Za-z_][A-Za-z0-9_]*)
|(?P<op>[\[\]{}()<>&*|^~!=+\-/%.,;:?@]+)
|(?P<ws>\s+)
|(?P<etc>.)
""", re.S | re.X)

def hl_rin(src):
    out = []
    for m in RIN_TOK.finditer(src):
        kind, text = m.lastgroup, m.group()
        t = esc(text)
        if kind == "com": out.append(f'<span class="c-com">{t}</span>')
        elif kind in ("str", "chr"): out.append(f'<span class="c-str">{t}</span>')
        elif kind == "num": out.append(f'<span class="c-num">{t}</span>')
        elif kind == "id":
            rest = src[m.end():m.end()+24]
            if text in RIN_KW: out.append(f'<span class="c-kw">{t}</span>')
            elif text in RIN_TY: out.append(f'<span class="c-ty">{t}</span>')
            elif re.match(r"(?:<[^>\n]*>[A-Za-z_]\w*)?:\s*(?:static\s+)?(?:proc|struct|enum|union)\b", rest) or re.match(r":\s*(?:static\s+)?(?:proc|struct|enum|union)\b", rest):
                out.append(f'<span class="c-def">{t}</span>')
            else: out.append(t)
        else: out.append(t)
    return "".join(out)

PY_KW = set("from import def return if elif else for in not and or while with as class try except finally raise pass None True False lambda is continue break".split())
PY_TOK = re.compile(r'''(?P<com>\#[^\n]*)|(?P<str>"""(?:.|\n)*?"""|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')|(?P<num>\b\d+\b)|(?P<id>[A-Za-z_]\w*)|(?P<ws>\s+)|(?P<etc>.)''', re.S)
def hl_py(src):
    out = []
    for m in PY_TOK.finditer(src):
        kind, t = m.lastgroup, esc(m.group())
        if kind == "com": out.append(f'<span class="c-com">{t}</span>')
        elif kind == "str": out.append(f'<span class="c-str">{t}</span>')
        elif kind == "num": out.append(f'<span class="c-num">{t}</span>')
        elif kind == "id" and m.group() in PY_KW: out.append(f'<span class="c-kw">{t}</span>')
        else: out.append(t)
    return "".join(out)

def code_block(src, lang):
    body = hl_rin(src) if lang == "rin" else hl_py(src) if lang == "py" else esc(src)
    lines = body.split("\n")
    if lines and lines[-1] == "": lines.pop()
    rows = "".join(f'<span class="ln"><span class="no">{i}</span>{l or " "}</span>' for i, l in enumerate(lines, 1))
    return f'<pre class="code"><code>{rows}</code></pre>'

# ---------------------------------------------------------------- markdown
LINKS = {
    "0_from_kayan.md": "#from-kayan", "1_aos_vs_soa.md": "#aos-vs-soa", "2_archetype_table.md": "#archetype-table",
    "3_many_archetypes.md": "#many-archetypes", "4_entity_handles.md": "#entity-handles", "5_inspector.md": "#inspector",
    "6_kayan.md": "#kayan", "LICENSE": "#tools",
}
def link_target(url):
    base = url.split("/")[-1]
    if base in LINKS: return LINKS[base], False
    return url, url.startswith("http")

def inline(text):
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for p in parts:
        if p.startswith("`") and p.endswith("`") and len(p) > 1:
            out.append(f"<code>{esc(p[1:-1])}</code>"); continue
        p = esc(p)
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        def lk(m):
            href, ext = link_target(html.unescape(m.group(2)))
            attrs = ' target="_blank" rel="noopener"' if ext else ""
            return f'<a href="{esc(href)}"{attrs}>{m.group(1)}</a>'
        p = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lk, p)
        out.append(p)
    # links whose text is code: [`x`](y) were split; fix simple case
    s = "".join(out)
    s = re.sub(r"\[(<code>[^<]*</code>)\]\(([^)]+)\)", lambda m: f'<a href="{esc(link_target(m.group(2))[0])}">{m.group(1)}</a>', s)
    return s

def md(text, skip_title=False):
    lines = text.split("\n")
    out, para, i = [], [], 0
    def flush():
        nonlocal para
        if para: out.append("<p>" + inline(" ".join(l.strip() for l in para)) + "</p>"); para = []
    while i < len(lines):
        line = lines[i]
        if not line.strip(): flush(); i += 1; continue
        h = re.match(r"(#{1,4}) (.*)", line)
        if h:
            flush(); lvl = len(h.group(1))
            if not (skip_title and lvl == 1):
                out.append(f"<h{lvl+1}>{inline(h.group(2))}</h{lvl+1}>")
            i += 1; continue
        if line.startswith("    ") and not para:
            block = []
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                block.append(lines[i][4:]); i += 1
            while block and not block[-1].strip(): block.pop()
            out.append('<pre class="snip"><code>' + esc("\n".join(block)) + "</code></pre>"); continue
        if line.startswith("|"):
            flush(); rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            head, body = rows[0], [r for r in rows[2:]]
            t = '<div class="tablewrap"><table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            for r in body: t += "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table></div>"); continue
        lm = re.match(r"(\s*)(-|\d+\.) (.*)", line)
        if lm and not para:
            ordered = lm.group(2) != "-"
            items = []
            while i < len(lines):
                m2 = re.match(r"(\s*)(-|\d+\.) (.*)", lines[i])
                if m2: items.append([m2.group(3)]); i += 1; continue
                if lines[i].startswith("  ") and lines[i].strip() and items: items[-1].append(lines[i].strip()); i += 1; continue
                break
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join("<li>" + inline(" ".join(it)) + "</li>" for it in items) + f"</{tag}>"); continue
        para.append(line); i += 1
    flush()
    return "\n".join(out)

# ---------------------------------------------------------------- content
lessons = [
    ("aos-vs-soa", "1", "AoS vs SoA", "src/1.aos_vs_soa/aos_vs_soa", "docs/1_aos_vs_soa.md", "The same particles in three layouts, and what SIMD needs"),
    ("archetype-table", "2", "One archetype table", "src/2.archetype_table/archetype_table", "docs/2_archetype_table.md", "Columns, rows, spawn, swap-remove, systems over slices"),
    ("many-archetypes", "3", "Many archetypes", "src/3.many_archetypes/many_archetypes", "docs/3_many_archetypes.md", "One table type for every archetype: ids, signatures, queries"),
    ("entity-handles", "4", "Entity handles", "src/4.entity_handles/entity_handles", "docs/4_entity_handles.md", "Generational handles, slots, moving between archetypes"),
    ("inspector", "5", "The inspector", "src/5.inspector/inspector", "docs/5_inspector.md", "Printing and editing any entity from reflection records"),
    ("kayan", "6", "kayan", "src/6.kayan/kayan", "docs/6_kayan.md", "A small game, with structural changes deferred to a command buffer"),
]

def read(p): return (REPO / p).read_text(encoding="utf-8")
def nlines(s): return s.count("\n")

nav, views = [], []

# overview
readme = read("README.md")
nav.append(('overview', '', 'Overview', 'README and the layout behind lesson 1'))
diagram = '''
<figure class="memmap" aria-label="One 68-byte particle against 64-byte cache lines">
  <figcaption><span class="eyebrow">Lesson 1, to scale</span><span>One <code>particle</code> is 68 bytes. Movement reads the first 24.</span></figcaption>
  <div class="strip aos">
    <span class="f use" style="--b:12" title="position, 12 bytes">position</span><span class="f use" style="--b:12" title="velocity, 12 bytes">velocity</span><span class="f" style="--b:16" title="tint, 16 bytes">tint</span><span class="f" style="--b:4" title="age, 4 bytes"></span><span class="f" style="--b:4" title="lifetime, 4 bytes"></span><span class="f" style="--b:4" title="size, 4 bytes"></span><span class="f" style="--b:16" title="name, 16 bytes">name</span>
  </div>
  <div class="ruler"><span style="--at:0">0</span><span style="--at:24">24</span><span style="--at:64">64, end of a cache line</span><span style="--at:68">68</span></div>
  <div class="legend"><span><i class="sw use"></i>read by movement: position 12, velocity 12</span><span><i class="sw"></i>fetched anyway: tint 16, age 4, lifetime 4, size 4, name 16</span></div>
  <p class="figtext">In the array of structs, every cache line movement pulls in is about two thirds tint, age, life, size and name. In the struct of arrays, movement fetches only the position and velocity columns: <strong>6,291,456</strong> bytes a step instead of <strong>17,825,792</strong>.</p>
</figure>'''
views.append(f'''<section class="view" id="v-overview" data-view="overview">
<header class="vhead"><p class="eyebrow">rin · data-oriented design · six lessons</p><h1>rin-dod</h1>
<p class="lede">From one array of structs to a small archetype entity component system, written in rin and checked against the output each program must print.</p></header>
{diagram}
<div class="prose">{md(readme, skip_title=True)}</div>
</section>''')

# from kayan
nav.append(('from-kayan', '0', 'From kayan', 'What was kept, what changed, and why'))
views.append(f'''<section class="view" id="v-from-kayan" data-view="from-kayan" hidden>
<header class="vhead"><p class="eyebrow">Lesson 0 · review</p><h1>From kayan</h1><p class="path">docs/0_from_kayan.md</p></header>
<div class="prose">{md(read("docs/0_from_kayan.md"), skip_title=True)}</div></section>''')

for tok, num, title, base, doc, blurb in lessons:
    src = read(base + ".rin"); exp = read(base + ".expected"); guide = read(doc)
    nav.append((tok, num, title, blurb))
    imports = '<p class="note">Imports the world from <a href="#library"><code>includes/kayan.rin</code></a>.</p>' if "includes/kayan.rin" in src else ""
    views.append(f'''<section class="view" id="v-{tok}" data-view="{tok}" hidden>
<header class="vhead"><p class="eyebrow">Lesson {num}</p><h1>{esc(title)}</h1><p class="path">{base}.rin</p></header>
<div class="tabs" role="tablist" aria-label="{esc(title)} views">
  <button role="tab" type="button" class="tab" aria-selected="true" data-pane="guide">Guide</button>
  <button role="tab" type="button" class="tab" aria-selected="false" data-pane="code">Code <span class="count">{nlines(src)} lines</span></button>
  <button role="tab" type="button" class="tab" aria-selected="false" data-pane="output">Output <span class="count">{nlines(exp)} lines</span></button>
</div>
<div class="pane" data-pane="guide"><div class="prose">{md(guide, skip_title=True)}</div></div>
<div class="pane" data-pane="code" hidden>{imports}{code_block(src, "rin")}</div>
<div class="pane" data-pane="output" hidden><p class="note">What <code>{base.split("/")[-1]}</code> prints. <code>tools/check.py</code> fails the lesson if a single byte differs.</p><pre class="term"><code>{esc(exp)}</code></pre></div>
</section>''')

lib = read("includes/kayan.rin")
nav.append(('library', '', 'includes/kayan.rin', 'The world lessons 5 and 6 import'))
views.append(f'''<section class="view" id="v-library" data-view="library" hidden>
<header class="vhead"><p class="eyebrow">Library · built in lesson 4</p><h1>kayan.rin</h1><p class="path">includes/kayan.rin · {nlines(lib)} lines</p></header>
{code_block(lib, "rin")}</section>''')

tools_html = ""
for p, lang in (("tools/check.py", "py"), ("build.rin", "rin"), (".gitignore", "txt"), ("LICENSE", "txt")):
    s = read(p)
    tools_html += f'<h2 class="filehead">{p}</h2>' + code_block(s, lang)
nav.append(('tools', '', 'Build and check', 'check.py, build.rin, license'))
views.append(f'''<section class="view" id="v-tools" data-view="tools" hidden>
<header class="vhead"><p class="eyebrow">Tooling</p><h1>Build and check</h1><p class="path">tools/check.py runs every lesson and diffs its output</p></header>
{tools_html}</section>''')

def navitem(tok, num, title, blurb):
    n = f'<span class="num">{num}</span>' if num else '<span class="num dim">·</span>'
    return f'<a class="navlink" href="#{tok}" data-view="{tok}">{n}<span class="nt"><span class="ttl">{esc(title)}</span><span class="blurb">{esc(blurb)}</span></span></a>'

group1 = "".join(navitem(*n) for n in nav[:2])
group2 = "".join(navitem(*n) for n in nav[2:8])
group3 = "".join(navitem(*n) for n in nav[8:])

template = (REPO / "website" / "template.html").read_text(encoding="utf-8")
page = template.replace("{{NAV1}}", group1).replace("{{NAV2}}", group2).replace("{{NAV3}}", group3).replace("{{VIEWS}}", "\n".join(views))
OUT.write_text(page, encoding="utf-8", newline="\n")
print(f"wrote {OUT.relative_to(REPO).as_posix()} ({len(page)//1024} KB)")
