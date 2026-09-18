#!/usr/bin/env python3
"""Accept a real Archify plan and clear its pending dependency update only on success."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from workflow_policy import paths, load


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            if dep not in work:
                raise ValueError(f'Executable issue #{issue["number"]} still depends on an aggregate or missing issue #{dep}.')
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archify', required=True, type=Path)
    p.add_argument('--spec', required=True, type=Path)
    p.add_argument('--mapping', required=True, type=Path)
    p.add_argument('--review', type=Path, help='Perceptual review of the already-delivered HTML, with screenshot hashes')
    args = p.parse_args()
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    pending = root / '.specify/scope/plan-pending.json'
    artifact_directory, output = paths(root)
    graph = artifact_directory / 'scope-dependencies.json'
    if not pending.exists() or not graph.exists():
        raise SystemExit('No published decomposition is awaiting a dependency-plan update.')
    graph_hash = sha(graph)
    spec = args.spec.resolve()
    data = json.loads(spec.read_text(encoding='utf-8-sig'))
    if data.get('diagram_type') != 'workflow' or data.get('meta', {}).get('quality_profile') != 'showcase':
        raise SystemExit('Expected a showcase Archify workflow candidate.')
    mapping = json.loads(args.mapping.read_text(encoding='utf-8-sig'))
    check_graph_mapping(json.loads(graph.read_text(encoding='utf-8-sig')), data, mapping, graph_hash)
    receipt_path = artifact_directory / 'scope-plan-receipt.json'
    if args.review:
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt.get('graph_sha256') != graph_hash or receipt.get('spec_sha256') != sha(spec) or receipt.get('html_sha256') != sha(output):
            raise SystemExit('Delivered plan changed after browser checks; regenerate before review acceptance.')
        review = json.loads(args.review.read_text(encoding='utf-8-sig'))
        validate_review(root, output, review)
        receipt['perceptual_review'] = review
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        if output.resolve() != (artifact_directory / 'implementation-plan.html').resolve():
            shutil.copy2(output, artifact_directory / 'implementation-plan.html')
        pending.unlink()
        print('Archify delivery, browser checks and recorded perceptual review accepted.')
        return
    receipt = {'graph_sha256': graph_hash, 'spec_sha256': sha(spec), 'commands': []}
    for tail in [('validate', 'workflow', str(spec), '--quality', 'showcase', '--json'),
                 ('deliver', 'workflow', str(spec), str(output), '--quality', 'showcase', '--json'),
                 ('visual-check', str(output), '--json')]:
        run = subprocess.run(['node', str(args.archify.resolve()), *tail], capture_output=True, text=True, encoding='utf-8')
        receipt['commands'].append({'command': tail[0], 'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr})
        if run.returncode:
            (pending.parent / 'plan-failed-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            raise SystemExit(f'Archify {tail[0]} failed; pending marker retained. {run.stderr}')
    if sha(graph) != graph_hash or sha(spec) != receipt['spec_sha256']:
        raise SystemExit('Graph or candidate changed during acceptance; pending marker retained.')
    receipt['html_sha256'] = sha(output)
    receipt['perceptual_review'] = 'Requires actual image-capable reviewer; not asserted by this script.'
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    if load(root):
        print('Archify delivery and browser checks passed. Pending marker retained until image review; rerun with --review <review.json>.')
        return
    if output.resolve() != (artifact_directory / 'implementation-plan.html').resolve():
        shutil.copy2(output, artifact_directory / 'implementation-plan.html')
    pending.unlink()
    print('Archify delivery and browser checks passed. Plan copies synchronized.')


def validate_review(root, output, review):
    if review.get('html_sha256') != sha(output) or review.get('passed') is not True or not review.get('reviewer') or review.get('findings') != []:
        raise ValueError('Perceptual review must identify the current HTML, reviewer, and zero unresolved findings.')
    if not review.get('screenshots'):
        raise ValueError('Perceptual review requires actual screenshot evidence.')
    for item in review['screenshots']:
        image = (root / item['path']).resolve()
        if not image.is_relative_to(root.resolve()) or not image.is_file() or sha(image) != item['sha256']:
            raise ValueError('Perceptual screenshot evidence is missing, changed or outside the project.')


if __name__ == '__main__':
    main()
