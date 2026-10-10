#!/usr/bin/env python3
"""Accept an Illustrate dependency-plan diagram and clear the pending dependency update only on success.

The candidate is an Illustrate dependency-graph HTML file whose wave nodes carry
`data-plan-node="<id>"` and whose edges carry `data-plan-from`/`data-plan-to`.
Acceptance runs Illustrate's own checks and exporter, a headless-browser render
check with screenshots, and (in managed projects) a recorded image review before
the pending marker is removed.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from workflow_policy import paths, load

RENDERER = 'illustrate'
VIEWPORTS = ((1280, 800), (1440, 900), (1920, 1080))
REQUIRED = 'Regenerate the dependency plan with Illustrate (/speckit-scope-plan), then run accept_plan.py.'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PlanParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes, self.edges = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('data-plan-node'):
            self.nodes.append({'id': attrs['data-plan-node']})
        if attrs.get('data-plan-from') or attrs.get('data-plan-to'):
            self.edges.append({'from': attrs.get('data-plan-from'), 'to': attrs.get('data-plan-to')})

    handle_startendtag = handle_starttag


def read_diagram(html):
    """Nodes and edges declared in the Illustrate HTML itself; the picture is the contract."""
    parser = PlanParser()
    parser.feed(Path(html).read_text(encoding='utf-8-sig'))
    ids = [n['id'] for n in parser.nodes]
    if not ids:
        raise ValueError('No data-plan-node elements; mark each wave node of the Illustrate dependency graph.')
    if len(ids) != len(set(ids)):
        raise ValueError('Each data-plan-node id must appear exactly once.')
    for edge in parser.edges:
        if edge['from'] not in ids or edge['to'] not in ids:
            raise ValueError(f'Edge {edge["from"]} -> {edge["to"]} must connect two declared data-plan-node ids.')
    return {'nodes': parser.nodes, 'edges': parser.edges}


def check_graph_mapping(graph, diagram, mapping, graph_hash):
    """Prove issue coverage and dependency reachability against the authored waves."""
    if mapping.get('graph_sha256') != graph_hash:
        raise ValueError('Plan mapping is stale; use the current dependency graph hash.')
    nodes = {x['id'] for x in diagram['nodes']}
    assigned = mapping.get('issue_to_node', {})
    work = {x['number']: x for x in graph['issues'] if not x.get('children') and x.get('kind') != 'epic'}
    if set(assigned) != {str(n) for n in work} or not set(assigned.values()) <= nodes:
        raise ValueError('Map every executable issue exactly once to an existing diagram node.')
    complete, active = set(), set()

    def visit(number):
        if number in active:
            raise ValueError('Dependency graph is cyclic; implementation waves cannot be scheduled.')
        if number in complete:
            return
        active.add(number)
        for dep in work[number]['dependencies']:
            if dep not in work:
                raise ValueError(f'Executable issue #{number} still depends on an aggregate or missing issue #{dep}.')
            visit(dep)
        active.remove(number)
        complete.add(number)
    for number in work:
        visit(number)
    edges = {n: set() for n in nodes}
    for edge in diagram['edges']:
        edges[edge['from']].add(edge['to'])
    for issue in work.values():
        for dep in issue['dependencies']:
            source, target = assigned[str(dep)], assigned[str(issue['number'])]
            if source == target:
                raise ValueError('Dependent issues cannot share one parallel implementation wave.')
            queue, seen = list(edges[source]), set()
            while queue:
                n = queue.pop()
                if n not in seen:
                    seen.add(n)
                    queue.extend(edges[n])
            if target not in seen:
                raise ValueError(f'Diagram omits dependency #{dep} -> #{issue["number"]}.')


BROWSER_PROBE = """() => {
  const svg = document.querySelector('svg');
  if (!svg) return {error: 'no <svg> rendered'};
  const box = e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; };
  return {svg: box(svg),
          nodes: [...document.querySelectorAll('[data-plan-node]')].map(e => ({id: e.dataset.planNode, ...box(e)})),
          edges: [...document.querySelectorAll('[data-plan-from]')].map(e => ({id: e.dataset.planFrom + '->' + e.dataset.planTo,
                  length: typeof e.getTotalLength === 'function' ? e.getTotalLength() : 0}))};
}"""


def check_layout(probe, viewport):
    """Visual assertions on one rendered viewport; returns a list of findings."""
    if probe.get('error'):
        return [f'{viewport}: {probe["error"]}']
    findings, svg = [], probe['svg']
    if svg['w'] <= 0 or svg['h'] <= 0:
        findings.append(f'{viewport}: diagram SVG has no visible size')
    nodes = probe['nodes']
    for n in nodes:
        if n['w'] <= 0 or n['h'] <= 0:
            findings.append(f'{viewport}: node {n["id"]} is not visible')
        elif n['x'] < svg['x'] - 1 or n['y'] < svg['y'] - 1 or n['x'] + n['w'] > svg['x'] + svg['w'] + 1 or n['y'] + n['h'] > svg['y'] + svg['h'] + 1:
            findings.append(f'{viewport}: node {n["id"]} falls outside the diagram')
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w'] and a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h']:
                findings.append(f'{viewport}: nodes {a["id"]} and {b["id"]} overlap')
    findings += [f'{viewport}: edge {e["id"]} has no drawn length' for e in probe['edges'] if e['length'] <= 0]
    return findings


def browser_check(html, folder, root):
    """Render the HTML in headless Chromium at desktop viewports, assert the layout, keep screenshots."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError('Playwright is required for the plan browser check: pip install playwright && playwright install chromium')
    folder.mkdir(parents=True, exist_ok=True)
    result = {'viewports': [], 'findings': [], 'screenshots': []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for width, height in VIEWPORTS:
                page = browser.new_page(viewport={'width': width, 'height': height})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                # An unreachable web font is not a render defect; script errors are.
                page.on('console', lambda m: errors.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
                page.goto(Path(html).resolve().as_uri())
                page.wait_for_load_state('networkidle')
                name = f'{width}x{height}'
                findings = check_layout(page.evaluate(BROWSER_PROBE), name) + [f'{name}: console error {e}' for e in errors]
                shot = folder / f'implementation-plan-{name}.png'
                page.screenshot(path=str(shot), full_page=True)
                page.close()
                result['viewports'].append(name)
                result['findings'] += findings
                result['screenshots'].append({'path': shot.relative_to(root).as_posix(), 'sha256': sha(shot)})
        finally:
            browser.close()
    return result


def validate_review(root, output, review):
    if review.get('html_sha256') != sha(output) or review.get('passed') is not True or not review.get('reviewer') or review.get('findings') != []:
        raise ValueError('Perceptual review must identify the current HTML, reviewer, and zero unresolved findings.')
    if not review.get('screenshots'):
        raise ValueError('Perceptual review requires actual screenshot evidence.')
    for item in review['screenshots']:
        image = (root / item['path']).resolve()
        if not image.is_relative_to(root.resolve()) or not image.is_file() or sha(image) != item['sha256']:
            raise ValueError('Perceptual screenshot evidence is missing, changed or outside the project.')


def migrate_pending(pending, artifact_directory):
    """Convert a marker left by the pre-1.6.0 renderer: keep it pending and require regeneration.

    Nothing is dropped. The original marker is kept inside the new one, and an unreviewed
    legacy receipt is moved aside so it can never be accepted as Illustrate evidence.
    Returns a recovery message, or None when the marker is already current.
    """
    marker = json.loads(pending.read_text(encoding='utf-8-sig'))
    if marker.get('renderer') == RENDERER:
        return None
    converted = {'operation': marker.get('operation'), 'issue': marker.get('issue'), 'renderer': RENDERER,
                 'required': REQUIRED, 'migrated_from': marker}
    receipt = artifact_directory / 'scope-plan-receipt.json'
    note = ''
    if receipt.is_file() and json.loads(receipt.read_text(encoding='utf-8-sig')).get('renderer') != RENDERER:
        legacy = receipt.with_name('scope-plan-receipt.legacy.json')
        receipt.replace(legacy)
        converted['legacy_receipt'] = legacy.name
        note = f' Its unreviewed receipt was kept as {legacy.name}.'
    pending.write_text(json.dumps(converted, indent=2), encoding='utf-8')
    return (f'PLAN_REGENERATION_REQUIRED: issue #{marker.get("issue")} has a pending dependency plan from the previous renderer.'
            f' It was converted and stays pending until an Illustrate plan is accepted.{note} {REQUIRED}')


def run_tool(receipt, name, command):
    run = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    receipt['commands'].append({'command': name, 'exit_code': run.returncode, 'stdout': run.stdout[-4000:], 'stderr': run.stderr[-4000:]})
    return run


def deliver(candidate, output, artifact_directory):
    """Copy accepted bytes to the plan file and its compatibility copy; failures never touch them earlier."""
    for target in {output.resolve(), (artifact_directory / 'implementation-plan.html').resolve()}:
        if target != candidate.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--html', type=Path, help='Illustrate dependency-graph candidate HTML')
    p.add_argument('--spec', type=Path, help='Deprecated alias of --html (removed in 1.7.0)')
    p.add_argument('--archify', help='Deprecated and ignored (removed in 1.7.0)')
    p.add_argument('--mapping', type=Path)
    p.add_argument('--illustrate', type=Path, help='Installed Illustrate skill directory (default .specify/extensions/illustrate/skill)')
    p.add_argument('--review', type=Path, help='Perceptual review of the delivered HTML, with screenshot hashes')
    p.add_argument('--migrate-only', action='store_true', help='Only convert a pending plan left by an earlier Scope version')
    args = p.parse_args(argv)
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()).resolve()
    pending = root / '.specify/scope/plan-pending.json'
    artifact_directory, output = paths(root)
    graph = artifact_directory / 'scope-dependencies.json'
    if not pending.exists() or not graph.exists():
        raise SystemExit('No published decomposition is awaiting a dependency-plan update.')
    message = migrate_pending(pending, artifact_directory)
    if message:
        print(message, file=sys.stderr)
    if args.migrate_only:
        print(message or 'Pending plan is current; nothing to migrate.')
        return
    if args.archify:
        print('--archify is deprecated and ignored; the plan is checked with Illustrate.', file=sys.stderr)
    if args.spec and not args.html:
        print('--spec is deprecated; use --html.', file=sys.stderr)
    candidate = (args.html or args.spec)
    if not candidate or not args.mapping:
        raise SystemExit('--html <candidate.html> and --mapping <mapping.json> are required.')
    candidate = candidate.resolve()
    if candidate.suffix.lower() != '.html':
        raise SystemExit(f'{candidate.name} is not an Illustrate HTML candidate; plans from the previous renderer must be regenerated. {REQUIRED}')
    graph_hash = sha(graph)
    mapping = json.loads(args.mapping.read_text(encoding='utf-8-sig'))
    try:
        check_graph_mapping(json.loads(graph.read_text(encoding='utf-8-sig')), read_diagram(candidate), mapping, graph_hash)
    except ValueError as exc:
        raise SystemExit(f'{exc} Pending marker retained.')
    receipt_path = artifact_directory / 'scope-plan-receipt.json'
    if args.review:
        receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.is_file() else {}
        if receipt.get('renderer') != RENDERER:
            raise SystemExit('No Illustrate plan receipt to review; run accept_plan.py without --review first.')
        if receipt.get('graph_sha256') != graph_hash or receipt.get('candidate_sha256') != sha(candidate) or not output.is_file() or receipt.get('html_sha256') != sha(output):
            raise SystemExit('Delivered plan changed after browser checks; regenerate before review acceptance.')
        review = json.loads(args.review.read_text(encoding='utf-8-sig'))
        try:
            validate_review(root, output, review)
        except ValueError as exc:
            raise SystemExit(f'{exc} Pending marker retained.')
        receipt['perceptual_review'] = review
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        deliver(output, output, artifact_directory)
        pending.unlink()
        print('Illustrate plan, browser checks and recorded perceptual review accepted.')
        return
    skill = (args.illustrate or root / '.specify/extensions/illustrate/skill').resolve()
    scripts = skill / 'scripts'
    if not all((scripts / s).is_file() for s in ('self_check.py', 'verify-geometry.py', 'export_diagram.py')):
        raise SystemExit(f'Illustrate (>=2.2.1) is not installed at {skill}; install it or pass --illustrate <skill-dir>.')
    receipt = {'renderer': RENDERER, 'graph_sha256': graph_hash, 'candidate_sha256': sha(candidate), 'commands': []}
    failed = pending.parent / 'plan-failed-receipt.json'

    def fail(reason):
        receipt['failure'] = reason
        failed.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        raise SystemExit(f'{reason}; pending marker retained and the previous plan is untouched. See {failed.relative_to(root).as_posix()}.')
    export_base = artifact_directory / 'implementation-plan'
    for name, command in (('self-check', [sys.executable, str(scripts / 'self_check.py'), str(candidate)]),
                          ('verify-geometry', [sys.executable, str(scripts / 'verify-geometry.py'), str(candidate)]),
                          ('export', [sys.executable, str(scripts / 'export_diagram.py'), str(candidate), '--output', str(export_base)])):
        run = run_tool(receipt, name, command)
        if run.returncode:
            fail(f'Illustrate {name} failed: {(run.stderr or run.stdout).strip()[:500]}')
    exports = {kind: export_base.with_suffix('.' + kind) for kind in ('svg', 'png')}
    if not all(f.is_file() for f in exports.values()):
        fail('Illustrate export did not produce both SVG and PNG')
    receipt['exports'] = {kind: {'path': f.relative_to(root).as_posix(), 'sha256': sha(f)} for kind, f in exports.items()}
    try:
        receipt['browser'] = browser_check(candidate, artifact_directory / 'plan-review', root)
    except Exception as exc:  # browser missing or crashed: fail closed, never hang on it
        fail(f'Browser check could not run: {exc}')
    if receipt['browser']['findings']:
        fail('Browser check findings: ' + '; '.join(receipt['browser']['findings'][:10]))
    if sha(graph) != graph_hash or sha(candidate) != receipt['candidate_sha256']:
        fail('Graph or candidate changed during acceptance')
    failed.unlink(missing_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate, output)
    receipt['html_sha256'] = sha(output)
    receipt['perceptual_review'] = 'Requires actual image-capable reviewer; not asserted by this script.'
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    if load(root):
        print('Illustrate checks, export and browser checks passed. Pending marker retained until image review; '
              'inspect the screenshots listed in the receipt and rerun with --review <review.json>.')
        return
    deliver(output, output, artifact_directory)
    pending.unlink()
    print('Illustrate checks, export and browser checks passed. Plan copies synchronized.')


if __name__ == '__main__':
    main()
