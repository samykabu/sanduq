# Regenerate: python docs/diagrams/build_overview_diagrams.py docs/diagrams
"""Generate product-map and lifecycle-overlay (html + static svg + animated svg).

ponytail: one generator so the animated final frame is byte-identical to the static drawing;
the animated file only adds a reduced-motion-gated <style> block.
"""
import sys
from pathlib import Path
from html import escape

OUT = Path(sys.argv[1])
SANS = "'IBM Plex Sans', 'Noto Sans Arabic', system-ui, sans-serif"
MONO = "'IBM Plex Mono', 'Noto Sans Arabic', ui-monospace, monospace"
SERIF = "'IBM Plex Serif', 'Noto Naskh Arabic', serif"
FONTS = "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&amp;family=IBM+Plex+Sans:wght@400;500;600&amp;family=IBM+Plex+Serif:ital,wght@0,400;1,400&amp;family=Noto+Naskh+Arabic:wght@400;500;600&amp;family=Noto+Sans+Arabic:wght@400;500;600&amp;display=swap"
LIGHT = dict(paper="#f6f8fc", paper2="#ffffff", ink="#15233c", muted="#4f6078", soft="#6b7a90",
             rule="#c7d2e2", accent="#2563eb", tint="rgba(37,99,235,0.09)", link="#1d4ed8")
DARK = dict(paper="#101827", paper2="#17233a", ink="#f5f7fb", muted="#b6c2d4", soft="#8796ac",
            rule="#40506a", accent="#6ea0ff", tint="rgba(110,160,255,0.14)", link="#8ab4ff")


def tokens(t):
    return ';'.join(f'--{k}:{v}' for k, v in t.items())


BASE_CSS = (
    f"svg{{{tokens(LIGHT)}}}"
    f"@media (prefers-color-scheme: dark){{svg{{{tokens(DARK)}}}}}"
    f"text{{font-family:{SANS};fill:var(--ink)}}"
    f".m{{font-family:{MONO};fill:var(--muted)}}"
    f".e{{font-family:{MONO};fill:var(--soft);letter-spacing:.08em}}"
    ".bg{fill:var(--paper)}.zone{fill:none;stroke:var(--rule)}"
    ".box{fill:var(--paper2);stroke:var(--rule)}.focal{fill:var(--tint);stroke:var(--accent)}"
    ".mask{fill:var(--paper)}"
    ".c{fill:none;stroke:var(--muted);stroke-width:1.5}.opt{stroke-dasharray:5 4}"
    ".lk{fill:none;stroke:var(--link);stroke-width:1.5}"
    ".mh{fill:none;stroke:var(--muted)}.mhl{fill:none;stroke:var(--link)}"
)


def defs():
    return ('<defs>'
            '<marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
            '<path class="mh" d="M0 1 L7 4 L0 7"/></marker>'
            '<marker id="arl" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
            '<path class="mhl" d="M0 1 L7 4 L0 7"/></marker></defs>')


def node(x, y, w, h, name, subs, cls='box', size=16):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="{cls}"/>']
    cx = x + w / 2
    lines = 1 + len(subs)
    top = y + h / 2 - (lines - 1) * 9 + 5
    out.append(f'<text x="{cx:g}" y="{top:g}" text-anchor="middle" font-size="{size}" font-weight="600">{escape(name)}</text>')
    for i, s in enumerate(subs):
        out.append(f'<text class="m" x="{cx:g}" y="{top + 19 + i * 16:g}" text-anchor="middle" font-size="12">{escape(s)}</text>')
    return ''.join(out)


def g(step, body):
    return f'<g class="s s{step}">{body}</g>'


def svg(slug, w, h, title, desc, body, css):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" '
            f'aria-labelledby="{slug}-title {slug}-desc"><title id="{slug}-title">{escape(title)}</title>'
            f'<desc id="{slug}-desc">{escape(desc)}</desc>{defs()}<style>{css}</style>'
            f'<rect class="bg" width="{w}" height="{h}"/>{body}</svg>')


def motion_css(steps, step_ms, extra=''):
    # ponytail: CSS-only one-shot reveal (<5s), fill-mode both so the end state is the static frame.
    delays = ''.join(f'.s{i}{{animation-delay:{(i - 1) * step_ms}ms}}' for i in range(1, steps + 1))
    return ('@media (prefers-reduced-motion: no-preference){'
            '.s{animation:rv 480ms cubic-bezier(.2,.8,.2,1) both}'
            '@keyframes rv{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}'
            f'{delays}{extra}}}')


def write(slug, w, h, title, desc, body, steps, step_ms, extra_motion='', note=''):
    static = svg(slug, w, h, title, desc, body, BASE_CSS)
    animated = svg(slug, w, h, title, desc, body, BASE_CSS + motion_css(steps, step_ms, extra_motion))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    (OUT / f'{slug}.svg').write_text(xml + static + '\n', encoding='utf-8', newline=chr(10))
    (OUT / f'{slug}.animated.svg').write_text(xml + animated + '\n', encoding='utf-8', newline=chr(10))
    page = (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><link rel="stylesheet" href="{FONTS}">'
            f'<style>body{{margin:24px;background:#f6f8fc;color:#15233c;font-family:{SANS}}}'
            f'@media (prefers-color-scheme: dark){{body{{background:#101827;color:#f5f7fb}}}}'
            f'h1{{font-family:{SERIF};font-weight:400}}.diagram{{overflow-x:auto}}'
            f'svg{{width:100%;min-width:{w}px;max-width:{w}px;display:block}}p{{max-width:72ch;line-height:1.5}}</style>'
            f'<h1>{escape(title)}</h1><p>{escape(desc)}</p><div class="diagram">{static}</div>'
            f'<p>Editable Illustrate source. Theme: Cobalt Porcelain, light and dark. {escape(note)} '
            f'Exports: <code>{slug}.svg</code> (static) and <code>{slug}.animated.svg</code> '
            f'(same drawing plus a one-time reveal, off when reduced motion is requested).</p></html>\n')
    (OUT / f'{slug}.html').write_text(page, encoding='utf-8', newline=chr(10))


# ---------------------------------------------------------------- product map
def product_map():
    W = 1000
    X = [56, 288, 520, 752]
    BW = 196
    cx = [x + BW // 2 for x in X]
    R1, R2, R3, BH = 104, 232, 364, 68
    b = []
    # step 1: extension zone
    b.append(g(1, '<rect x="24" y="48" width="952" height="404" rx="8" class="zone"/>'
                  '<text class="e" x="48" y="80" font-size="12">THIS REPOSITORY · 9 SPEC KIT EXTENSIONS (SCOPE IS A RETIRED SHIM) AND 3 PRESETS</text>'))
    # step 2: Illustrate hub
    b.append(g(2, node(56, R3, 892, 64, 'Illustrate',
                       ['themed diagrams and charts · works alone · includes the Illustrate skill'], 'focal', 17)))
    # step 3: the four extensions that require Illustrate + their arrows (Scope is part of Workflow from 2.0.0)
    arrows = ''.join(f'<path class="c" d="M{c} {R2 + BH} V{R3 - 2}" marker-end="url(#ar)"/>' for c in cx)
    b.append(g(3, arrows
               + node(X[0], R2, BW, BH, 'Workflow', ['issue to verified PR', 'includes Scope, 3 presets'])
               + node(X[1], R2, BW, BH, 'Assure', ['QA analysis', 'tester walkthrough'])
               + node(X[2], R2, BW, BH, 'PR', ['feature docs, PR text', 'review feedback'])
               + node(X[3], R2, BW, BH, 'User Manual', ['application manual', 'includes its skill'])))
    # step 4: Workflow uses Progress when installed
    b.append(g(4, f'<path class="c opt" d="M{cx[0]} {R2} V{R1 + BH // 2} H{X[1] - 2}" marker-end="url(#ar)"/>'
                  + node(X[1], R1, BW, BH, 'Progress', ['progress report', 'no extension needed'])))
    # step 5: PR optionally uses Assure and User Manual
    y = R2 + BH // 2
    b.append(g(5, f'<path class="c opt" d="M{X[2]} {y} H{X[1] + BW + 2}" marker-end="url(#ar)"/>'
                  f'<path class="c opt" d="M{X[2] + BW} {y} H{X[3] - 2}" marker-end="url(#ar)"/>'))
    # step 6: standalone extensions
    b.append(g(6, node(X[2], R1, BW, BH, 'Project', ['GitHub Project sync', 'no extension needed'])
                  + node(X[3], R1, BW, BH, 'Memory', ['memory and spec archive', 'no extension needed'])))
    # step 7: sanduq-skills repository, its three bundles and what each one copies in
    SZ, SB = 516, 552
    b.append(g(7, '<rect x="24" y="' + str(SZ) + '" width="712" height="140" rx="8" class="zone"/>'
                  f'<text class="e" x="48" y="{SZ + 26}" font-size="12">SANDUQ-SKILLS REPOSITORY · 6 PORTABLE SKILLS, NO SPEC KIT</text>'
                  + node(X[0], SB, BW, 96, 'illustration-tools', ['illustrate', 'to Illustrate'])
                  + node(X[1], SB, BW, 96, 'dev-tools', ['user-manual', 'github-wiki-publish', 'to User Manual'])
                  + node(X[2], SB, BW, 96, 'agent-tools', ['delegate-task', 'progress-report', 'planning-majlis', 'to Workflow and Progress'])))
    # step 8: vendoring and marketplace
    lx = 386
    b.append(g(8, f'<path class="lk" d="M{lx} {SZ} V{452 + 2}" marker-end="url(#arl)"/>'
                  f'<rect class="mask" x="{lx + 8}" y="{476}" width="232" height="18"/>'
                  f'<text class="m" x="{lx + 14}" y="{489}" font-size="12">COPIED AT A PINNED RELEASE</text>'
                  f'<path class="lk" d="M736 {SZ + 70} H{780 - 2}" marker-end="url(#arl)"/>'
                  + node(780, SZ + 30, 168, 80, 'sanduq', ['plugin marketplace', 'for Claude hosts'], 'box', 16)))
    # legend (step 8 too, keeps steps <= 8)
    L = 692
    leg = (f'<line x1="24" y1="{L}" x2="976" y2="{L}" class="zone"/>'
           f'<path class="c" d="M48 {L + 28} H88" marker-end="url(#ar)"/><text class="m" x="98" y="{L + 32}" font-size="12">requires</text>'
           f'<path class="c opt" d="M200 {L + 28} H240" marker-end="url(#ar)"/><text class="m" x="250" y="{L + 32}" font-size="12">uses when installed</text>'
           f'<path class="lk" d="M432 {L + 28} H472" marker-end="url(#arl)"/><text class="m" x="482" y="{L + 32}" font-size="12">copied into, or listed by</text>'
           f'<rect x="700" y="{L + 20}" width="28" height="16" rx="3" class="focal"/><text class="m" x="738" y="{L + 32}" font-size="12">shared by four extensions</text>')
    b.append(g(8, leg))
    H = L + 56
    write('product-map', W, H, 'What is in the box',
          'Nine Spec Kit extensions and three presets live in this repository. Scope is part of Workflow from '
          'Workflow 2.0.0, so the scope package is a retired shim with no code and is not drawn; the presets ship with Workflow. Workflow, Assure, PR and User Manual require '
          'Illustrate; PR uses Assure and User Manual when they are installed; Workflow uses Progress when it is '
          'installed; Project, Memory and Progress need no other extension. The separate sanduq-skills repository '
          'holds six portable skills in three plugin bundles: illustration-tools (illustrate), dev-tools '
          '(user-manual, github-wiki-publish) and agent-tools (delegate-task, progress-report, planning-majlis). '
          'Four of them are copied in at a pinned release: illustrate into Illustrate, user-manual into User '
          'Manual, delegate-task into Workflow and progress-report into Progress. The sanduq marketplace lists '
          'the three bundles as plugins.',
          ''.join(b), 8, 520,
          note='Arrows point from a product to what it needs.')


# ----------------------------------------------------------- lifecycle overlay
M, O = 'mand', 'opt'
PHASES = [
    ('Specify', 'speckit.specify', [('workflow.scope-guard', M), ('memory.session', M)],
     [('workflow.scope-bind', M), ('project.sync', O), ('workflow.scope-after-specify', M)]),
    ('Clarify', 'speckit.clarify', [], []),
    ('Plan', 'speckit.plan', [('workflow.scope-plan-guard', M)], [('project.sync', O)]),
    ('Tasks', 'speckit.tasks', [], [('assure.analyze', O), ('progress.init', O), ('project.sync', O),
                                    ('user-manual.analyze', O)]),
    ('Analyze', 'speckit.analyze', [('memory.impact', M)], [('project.sync', O)]),
    ('Implement', 'speckit.implement', [('assure.analyze', O), ('project.sync', O)],
     [('assure.document', O), ('memory.prepare', M), ('pr.generate', O), ('progress.refresh', O),
      ('project.sync', O), ('user-manual.update', O), ('workflow.scope-reconcile', M)]),
    ('After merge, release', 'you run these', [], [('memory.run', 'cmd'), ('user-manual.release', 'cmd')]),
]


def chip(x, y, label, kind, w=212):
    cls = {'mand': 'chip', 'opt': 'chip opt', 'cmd': 'chip cmd'}[kind]
    weight = ' font-weight="600"' if kind == 'mand' else ''
    tcls = 'ct' if kind == 'mand' else 'm'
    return (f'<rect x="{x}" y="{y}" width="{w}" height="28" rx="4" class="{cls}"/>'
            f'<text class="{tcls}" x="{x + 12}" y="{y + 19}" font-size="13"{weight}>{escape(label)}</text>')


def lifecycle():
    W = 1090
    BX, PX, PW, AX = 40, 284, 176, 496   # before column, phase column, after columns
    CW, ACW, GAP = 212, 232, 12  # after chips fit workflow.scope-after-specify
    RG = 40   # gap between phase rows; feedback loops run through these gaps, clear of every chip
    b = [g(1, '<text class="e" x="40" y="36" font-size="12">BEFORE THE PHASE</text>'
              f'<text class="e" x="{PX + PW // 2}" y="36" font-size="12" text-anchor="middle">SPEC KIT PHASE</text>'
              f'<text class="e" x="{AX}" y="36" font-size="12">AFTER THE PHASE</text>')]
    y = 64
    prev_bottom = None
    rows = {}
    for i, (name, cmd, before, after) in enumerate(PHASES, start=1):
        a_rows = (len(after) + 1) // 2
        rh = max(52, len(before) * 36 - 8, a_rows * 36 - 8)
        parts = []
        if prev_bottom is not None:
            parts.append(f'<path class="c" d="M{PX + PW // 2} {prev_bottom} V{y - 2}" marker-end="url(#ar)"/>')
        mid = y + rh / 2
        if before:
            by = mid - (len(before) * 36 - 8) / 2
            for k, (lab, kind) in enumerate(before):
                parts.append(chip(BX, by + k * 36, lab, kind))
            parts.append(f'<path class="c" d="M{BX + CW} {mid:g} H{PX - 2}" marker-end="url(#ar)"/>')
        if after:
            ay = mid - (a_rows * 36 - 8) / 2
            parts.append(f'<path class="c" d="M{PX + PW} {mid:g} H{AX - 2}" marker-end="url(#ar)"/>')
            for k, (lab, kind) in enumerate(after):
                parts.append(chip(AX + (k % 2) * (ACW + GAP), ay + (k // 2) * 36, lab, kind, ACW))
        if not before and not after:
            parts.append(f'<text class="m" x="{AX}" y="{mid + 4:g}" font-size="13">no hooks</text>')
        last = i == len(PHASES)
        parts.append(f'<g class="ph">{node(PX, y, PW, rh, name, [cmd], "box ph-box cmdph" if last else "box ph-box", 16)}</g>')
        b.append(g(i + 1 if i < 7 else 8, ''.join(parts)))
        rows[name] = (y, y + rh)
        prev_bottom = y + rh
        y += rh + RG
    # Feedback loops (step 8). Each leaves a phase box from its bottom edge, runs right along the gap
    # below it to a lane past the after-chips, climbs, and enters the target phase from the gap above it.
    fx, fy = PX + PW - 30, PX + PW - 14   # exit and entry x on the phase boxes (clear of the main arrow)
    gap_above = lambda name: rows[name][0] - RG / 2
    ana_out = rows['Analyze'][1] + RG / 2 - 6
    imp_in = gap_above('Implement') + 6
    imp_out = rows['Implement'][1] + RG / 2
    la, lb = 1010, 1050
    loops = (
        # Analyze -> Plan: fix what Analyze found, then run it again
        f'<path class="lk" d="M{fx} {rows["Analyze"][1]} V{ana_out:g} H{la} V{gap_above("Plan"):g} H{fy} V{rows["Plan"][0] - 2}" marker-end="url(#arl)"/>'
        f'<text class="lb" x="{AX}" y="{gap_above("Plan") - 6:g}" font-size="12">Analyze found a gap: fix the spec, plan or tasks, then run Analyze again</text>'
        # Implement -> Implement: review feedback or a failed check re-runs the after-implement hooks
        f'<path class="lk" d="M{fx} {rows["Implement"][1]} V{imp_out:g} H{lb} V{imp_in:g} H{fy} V{rows["Implement"][0] - 2}" marker-end="url(#arl)"/>'
        f'<text class="lb" x="{AX}" y="{imp_out - 6:g}" font-size="12">Review feedback or a failed check: fix, then run Implement again so these hooks refresh</text>')
    b.append(g(8, loops))
    L = y - 4
    leg = (f'<line x1="24" y1="{L}" x2="976" y2="{L}" class="zone"/>'
           + chip(40, L + 18, 'mandatory: runs', 'mand', 176)
           + chip(232, L + 18, 'optional: asks first', 'opt', 192)
           + chip(440, L + 18, 'command, not a hook', 'cmd', 196)
           + f'<path class="lk" d="M656 {L + 32} H696" marker-end="url(#arl)"/>'
           + f'<text class="m" x="706" y="{L + 37}" font-size="12">loops back. Names drop the speckit. prefix.</text>')
    b.append(g(8, leg))
    H = L + 64
    css_extra = ('.lb{fill:var(--muted)}.chip{fill:var(--paper2);stroke:var(--ink);stroke-width:1.25}'
                 '.chip.opt{stroke:var(--muted);stroke-width:1;stroke-dasharray:4 3}'
                 '.chip.cmd{fill:none;stroke:var(--soft);stroke-width:1;stroke-dasharray:1 3}'
                 '.cmdph{stroke-dasharray:1 3}'
                 f'.ct{{font-family:{MONO};fill:var(--ink)}}')
    # phase "lights up": accent stroke while entering, settling on the static stroke.
    light = ('.ph-box{animation:lit 1200ms ease-out both}'
             '@keyframes lit{0%,45%{stroke:var(--accent);fill:var(--tint)}100%{stroke:var(--rule);fill:var(--paper2)}}'
             + ''.join(f'.s{i} .ph-box{{animation-delay:{(i - 1) * 560}ms}}' for i in range(2, 9)))
    global BASE_CSS
    base = BASE_CSS
    BASE_CSS = base + css_extra
    write('lifecycle-overlay', W, H, 'Hooks on the Spec Kit lifecycle',
          'Each Spec Kit phase with the extension hooks that run before and after it, as the manifests declare '
          'them. Specify, Plan and Analyze have mandatory guard and memory hooks; Tasks and Implement carry '
          'the optional QA, manual, progress, board-sync and PR hooks; Clarify has none. Two loops go back: '
          'when Analyze finds a gap you fix the spec, plan or tasks and run Analyze again, and when PR review '
          'feedback or a failed check needs a fix, running Implement again makes the after-implement hooks refresh '
          'the documentation; a fix made outside Implement does not run them. After '
          'merge and at release you run the Memory archive and User Manual release commands yourself.',
          ''.join(b), 8, 560, extra_motion=light,
          note='Derived from the manifest table in docs/reference/hooks.md; init and the managed Workflow can change modes.')
    BASE_CSS = base


# ------------------------------------------------------ managed workflow stages
# (stage, who does the work, kind) — kind 'sel' = only when QA or User Manual was selected at init
STAGES = [
    ('Scope', 'workflow.scope-run', ''),
    ('Specify', 'speckit.specify · memory.session', ''),
    ('Clarify', 'workflow.clarify · answers on the issue', ''),
    ('Plan', 'speckit.plan', ''),
    ('Tasks', 'speckit.tasks or SuperSpec tasks', ''),
    ('QA analysis', 'assure.analyze', 'sel'),
    ('Manual analysis', 'user-manual.analyze', 'sel'),
    ('Analyze', 'speckit.analyze · memory.impact', ''),
    ('Task issues', 'speckit.taskstoissues', ''),
    ('Execute', 'speckit.implement · workers · progress', ''),
    ('Verify', 'workflow:verification · your real tests', ''),
    ('Review', 'workflow:review · against spec and tests', ''),
    ('QA documentation', 'assure.document', 'sel'),
    ('Manual update', 'user-manual.update', 'sel'),
    ('Ready', 'workflow:gates · tasks, issues, docs', ''),
    ('PR', 'pr.generate · Illustrate diagrams', ''),
    ('CI and merge', 'pr.review-feedback, when you allow it', 'after'),
    ('After merge', 'memory archive · user-manual.release', 'after'),
]
# (number, from, to, lane x, exit offset, entry offset, legend text)
RETURNS = [
    (1, 'Clarify', 'Clarify', None, 0, 0, 'Clarify waits until the questions on the issue are answered, then resumes.'),
    (2, 'Analyze', 'Plan', 676, 0, 0, 'Analyze finds a blocking gap: fix the spec, plan or tasks.'),
    (3, 'Execute', 'Specify', 736, -21, 0, 'A spec or plan edited mid-build: revalidate-upstream re-records the stale stages.'),
    (4, 'Verify', 'Execute', 616, -6, 21, 'Checks fail: fix in Execute, then Verify again.'),
    (5, 'Review', 'Execute', 646, 0, 7, 'A blocking review finding: fix, then Verify and Review again.'),
    (6, 'Ready', 'Verify', 676, 0, 6, 'Code or docs changed after Verify: Verify, Review and Ready are revalidated.'),
    (7, 'CI and merge', 'Verify', 706, 0, 14, 'A failed CI check or PR review comments: fix on the branch, rerun the affected checks, revalidate Verify, Review and Ready, update the PR.'),
]


def wrap(text, width):
    out, line = [], ''
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f'{line} {word}'.strip()
    return out + [line]


def stages():
    W = 1180
    CX, CW = 40, 318          # "who does the work" column
    SX, SW = 380, 196         # stage column
    LX = 776                  # legend column
    RH, PITCH, EH = 34, 46, 64  # row height, row pitch, Execute height
    b = [g(1, '<text class="e" x="40" y="36" font-size="12">WHO DOES THE WORK</text>'
              f'<text class="e" x="{SX + SW // 2}" y="36" font-size="12" text-anchor="middle">STAGE</text>'
              f'<text class="e" x="{LX}" y="36" font-size="12">WHAT SENDS WORK BACK</text>')]
    rows, y = {}, 56
    for name, who, kind in STAGES:
        h = EH if name == 'Execute' else RH
        rows[name] = (y, y + h)
        y += h + (PITCH - RH)
    steps = {name: 2 + i * 5 // len(STAGES) for i, (name, _, _) in enumerate(STAGES)}
    prev = None
    for name, who, kind in STAGES:
        top, bot = rows[name]
        mid = (top + bot) / 2
        parts = []
        if prev is not None:
            parts.append(f'<path class="c" d="M{SX + SW // 2} {rows[prev][1]} V{top - 2}" marker-end="url(#ar)"/>')
        cls = {'': 'box', 'sel': 'box opt', 'after': 'box cmdph'}[kind]
        parts.append(f'<rect x="{SX}" y="{top}" width="{SW}" height="{bot - top}" rx="6" class="{cls}"/>'
                     f'<text x="{SX + SW // 2}" y="{mid + 5:g}" text-anchor="middle" font-size="15" font-weight="600">{escape(name)}</text>')
        parts.append(f'<rect x="{CX}" y="{mid - 13:g}" width="{CW}" height="26" rx="4" class="chip"/>'
                     f'<text class="ct" x="{CX + 10}" y="{mid + 4:g}" font-size="12">{escape(who)}</text>'
                     f'<path class="c" d="M{CX + CW} {mid:g} H{SX - 2}" marker-end="url(#ar)"/>')
        b.append(g(steps[name], ''.join(parts)))
        prev = name
    # return paths (step 7): lanes first, then each stub over a paper mask so a crossing reads as a bridge
    lanes, stubs, badges, legend = [], [], [], []
    for n, src, dst, lane, out_off, in_off, text in RETURNS:
        if lane is None:  # self-loop on the right edge
            top, bot = rows[src]
            m = (top + bot) / 2
            lanes.append(f'<path class="lk" d="M{SX + SW} {m - 8:g} H{SX + SW + 26} V{m + 8:g} H{SX + SW + 2}" marker-end="url(#arl)"/>')
            badges.append((SX + SW + 40, m, n))
        else:
            ys = (rows[src][0] + rows[src][1]) / 2 + out_off
            yd = (rows[dst][0] + rows[dst][1]) / 2 + in_off
            lanes.append(f'<path class="lk" d="M{lane} {ys:g} V{yd:g}"/>')
            for yy, arrow in ((ys, False), (yd, True)):
                stubs.append(f'<rect class="mask" x="{SX + SW + 2}" y="{yy - 3:g}" width="{lane - SX - SW - 4}" height="6"/>')
                if arrow:
                    stubs.append(f'<path class="lk" d="M{lane} {yy:g} H{SX + SW + 2}" marker-end="url(#arl)"/>')
                else:
                    stubs.append(f'<path class="lk" d="M{SX + SW} {yy:g} H{lane}"/>')
            badges.append((lane, ys + (yd - ys) * (0.25 if n == 5 else 0.5), n))
        legend.append((n, text))
    badge_svg = ''.join(f'<circle cx="{x}" cy="{yy:g}" r="10" class="badge"/>'
                        f'<text x="{x}" y="{yy + 4:g}" text-anchor="middle" font-size="12" font-weight="600" class="bt">{n}</text>'
                        for x, yy, n in badges)
    ly, leg = 64, []
    for n, text in legend:
        leg.append(f'<circle cx="{LX + 10}" cy="{ly - 4}" r="10" class="badge"/>'
                   f'<text x="{LX + 10}" y="{ly}" text-anchor="middle" font-size="12" font-weight="600" class="bt">{n}</text>')
        for k, line in enumerate(wrap(text, 46)):
            leg.append(f'<text x="{LX + 30}" y="{ly + k * 17}" font-size="13">{escape(line)}</text>')
        ly += 17 * len(wrap(text, 46)) + 14
    b.append(g(7, ''.join(lanes) + ''.join(stubs) + badge_svg + ''.join(leg)))
    # key (step 8)
    ky = ly + 16
    key = (f'<rect x="{LX}" y="{ky}" width="44" height="22" rx="4" class="box opt"/>'
           f'<text class="m" x="{LX + 56}" y="{ky + 16}" font-size="12">only when QA or User Manual is selected at init</text>'
           f'<rect x="{LX}" y="{ky + 34}" width="44" height="22" rx="4" class="box cmdph"/>'
           f'<text class="m" x="{LX + 56}" y="{ky + 50}" font-size="12">after the PR, with your permission</text>'
           f'<text class="m" x="{LX}" y="{ky + 84}" font-size="12">Command names drop the speckit. prefix.</text>'
           f'<text class="m" x="{LX}" y="{ky + 101}" font-size="12">The lite tier runs Scope, Specify, Clarify, Plan,</text>'
           f'<text class="m" x="{LX}" y="{ky + 118}" font-size="12">Execute, Verify and PR only. The standard tier</text>'
           f'<text class="m" x="{LX}" y="{ky + 135}" font-size="12">folds Tasks into Plan and lints Analyze.</text>'
           f'<text class="m" x="{LX}" y="{ky + 160}" font-size="12">With a board configured, Project sync moves the</text>'
           f'<text class="m" x="{LX}" y="{ky + 177}" font-size="12">card after each stage. Memory, when installed,</text>'
           f'<text class="m" x="{LX}" y="{ky + 194}" font-size="12">also runs when Execute completes.</text>')
    b.append(g(8, key))
    H = max(y, ky + 212) + 8
    css_extra = ('.chip{fill:var(--paper2);stroke:var(--rule)}'
                 f'.ct{{font-family:{MONO};fill:var(--ink)}}'
                 '.opt{stroke-dasharray:5 4}.cmdph{stroke-dasharray:1 3}'
                 '.badge{fill:var(--paper2);stroke:var(--link);stroke-width:1.5}.bt{fill:var(--link)}')
    global BASE_CSS
    base = BASE_CSS
    BASE_CSS = base + css_extra
    write('workflow-stages', W, H, 'Managed Workflow stages and what sends work back',
          'The managed Workflow runs one feature from Scope to a pull request, one claimed stage at a time. '
          'The left column names the command or extension that does each stage\'s work: Workflow for Scope and '
          'Clarify, Spec Kit for Specify, Plan, Tasks, Analyze and Execute, Memory at Specify and Analyze, '
          'Assure and User Manual for the selected QA and manual stages, Workflow runtime stages for Verify, '
          'Review and Ready, '
          'PR for the pull request and its review feedback, and Memory and User Manual again after merge. '
          'Seven numbered paths send work back: Clarify waits for answers on the issue; Analyze returns a '
          'blocking gap to Plan; a spec or plan edited mid-build makes revalidate-upstream re-record the stale '
          'stages; failed checks and blocking review findings return to Execute; failed CI and PR review '
          'comments are fixed on the branch and revalidate Verify, Review and Ready; '
          'and a change after Verify revalidates Verify, Review and Ready.',
          ''.join(b), 8, 480,
          note='Derived from docs/workflow/stages.md and the recovery reference; the lite tier skips stages.')
    BASE_CSS = base


product_map()
lifecycle()
stages()
