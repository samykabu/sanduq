#!/usr/bin/env python3
"""Accept a real Archify plan and clear its pending dependency update only on success."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from workflow_policy import paths


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
    (artifact_directory / 'scope-plan-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    if output.resolve() != (artifact_directory / 'implementation-plan.html').resolve():
        shutil.copy2(output, artifact_directory / 'implementation-plan.html')
    pending.unlink()
    print('Archify delivery and browser checks passed. Plan copies synchronized.')


if __name__ == '__main__':
    main()
