#!/usr/bin/env python3
"""Measure the managed workflow's cost for one small scripted feature (stream S0).

Loads the runtime from `<repo>/extensions/workflow/scripts/workflow.py`, builds the fixture consumer the
workflow unit tests build (plus a synthetic source tree), drives an effort-2 feature through the CLI
entry point in-process (start, claim/complete every stage, one spec edit after Execute and the cheapest
recovery the runtime offers, one pause, then Verify, Review, Ready and PR) and records per-command wall
time, stdout bytes and call counters, plus the static instruction bytes each stage loads.

No model is called: receipts are the minimal fixture receipts the unit tests use.

    python benchmark_front_half.py --repo <sanduq checkout> --out <json> [--tier lite|standard|full]
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import inspect
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

FEATURE = 'specs/001-example'
ISSUE = 'acme/app#10'
USAGE = {'session_id': 'host-without-telemetry'}  # the tests' unreliable usage: never pauses
TIER_SCORES = {'lite': 2, 'standard': 5, 'full': 13}
COUNTED = ('doctor', 'fingerprint_files', 'source_fingerprints', 'git')
RUNTIME_MODULES = ('wf_core', 'wf_identity', 'wf_fingerprints', 'wf_policy', 'wf_health', 'wf_receipts')
WORKFLOW_SKILL = 'extensions/workflow/skills/workflow/'
STAGE_EXTRAS = {
    'scope': ['extensions/scope/commands/run.md', 'extensions/scope/skills/scope-analyst/SKILL.ext.md',
              'extensions/scope/references/analysis-contract.md'],
    'specify': ['presets/scope-gate/commands/specify-gate.md', 'extensions/scope/commands/speckit.scope.guard.md',
                'extensions/scope/commands/speckit.scope.bind.md'],
    'clarify': ['extensions/scope/skills/github-clarification/SKILL.ext.md'],
    'execute': [WORKFLOW_SKILL + 'references/execution-assign.md', WORKFLOW_SKILL + 'references/execution-report.md',
                WORKFLOW_SKILL + 'references/reporting.md'],
}
# Workflow 1.15 prints the Execute protocol for the claimed mode inside the claim (`execute_protocol`), so
# those files are already counted in claim stdout and must not be counted again as static reads.
PROTOCOL_IN_CLAIM = {'execute'}
POINTER_SET = [WORKFLOW_SKILL + 'references/dispatcher-operations.md',
               WORKFLOW_SKILL + 'references/delegation-and-decisions.md']
LINK = re.compile(r'[A-Za-z0-9_./-]*references/[A-Za-z0-9_.-]+\.md')


def load_runtime(repo):
    path = repo / 'extensions/workflow/scripts/workflow.py'
    spec = importlib.util.spec_from_file_location('sanduq_workflow', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path.read_text(encoding='utf-8')


class Bench:
    def __init__(self, repo, root, tier, source_files):
        self.repo, self.root, self.tier = repo, root, tier
        self.w, self.source = load_runtime(repo)
        self.supports_profiles = 'effort_score' in self.source
        self.stages_take_tier = 'tier' in inspect.signature(self.w.stages).parameters
        self.counts = dict.fromkeys(COUNTED + ('git_subprocess',), 0)
        self.commands, self.claimed = [], []
        self.build_fixture(source_files)
        self.instrument()

    # Fixture: the same consumer test_workflow.py setUp/configure build, plus N source files.
    def build_fixture(self, source_files):
        w, root = self.w, self.root
        for args in [('init', '-q'), ('config', 'user.name', 'Test'), ('config', 'user.email', 'test@example.invalid'),
                     ('commit', '--allow-empty', '-qm', 'init')]:
            subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
        subprocess.run(['git', 'remote', 'add', 'origin', 'https://github.com/acme/app.git'], cwd=root, check=True)
        policy = w.default_policy(True, True)
        if self.supports_profiles:
            policy['profiles'] = {'enabled': True, 'lite': {'max_score': 3}, 'standard': {'max_score': 8}}
        path = root / '.specify/workflow.yml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(policy), encoding='utf-8')
        w.write(root / '.specify/init-options.json', {'integration': 'codex', 'ai_skills': True})
        w.write(root / '.specify/extensions/project/config.json', {
            'owner': 'acme', 'projectNumber': 1, 'projectId': 'P', 'statusFieldId': 'F',
            'stateFile': '.specify/project-sync-state.json', 'hookMode': 'required',
            'statusOptions': {n: n for n in ('Backlog', 'Feature Specification', 'Need Clarifications', 'Ready',
                                             'In progress', 'In review', 'Done')},
            'phaseToStatus': {'open': 'Feature Specification', 'analysis': 'Ready', 'engineer-review': 'Ready',
                              'ready': 'Ready', 'in-progress': 'In progress', 'in-review': 'In review', 'done': 'Done'},
        })
        (root / '.specify/extensions.yml').write_text('hooks: {}\n', encoding='utf-8')
        for preset in ('workflow', 'scope-gate', 'scope-brainstorm'):
            p = root / '.specify/presets' / preset / 'preset.yml'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('schema_version: "1.0"\n', encoding='utf-8')
        w.write(root / '.specify/presets/.registry',
                {'presets': {p: {'enabled': True} for p in ('workflow', 'scope-gate', 'scope-brainstorm')}})
        versions = {'scope': '1.11.0', 'project': '2.2.0', 'pr': '4.2.0', 'assure': '2.2.0', 'user-manual': '1.2.0'}
        w.write(root / '.specify/extensions/.registry',
                {'extensions': {n: {'version': v, 'enabled': True} for n, v in versions.items()}})
        for n, v in versions.items():
            p = root / '.specify/extensions' / n / 'extension.yml'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(yaml.safe_dump({'extension': {'id': n, 'version': v,
                                                       'repository': 'https://github.com/samykabu/sanduq',
                                                       'author': w.SANDUQ_AUTHOR}}),
                         encoding='utf-8')
        for command in w.COMMANDS.values():
            if command.startswith('workflow:'): continue
            p = root / '.agents/skills' / command.replace('.', '-') / 'SKILL.md'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture command', encoding='utf-8')
        for i in range(source_files):
            ext = '.py' if i % 2 else '.ts'
            p = root / 'src' / f'pkg{i // 50:02d}' / f'mod{i:04d}{ext}'
            p.parent.mkdir(parents=True, exist_ok=True)
            body = (f'def handler_{i}(value):\n    return value + {i}\n' if ext == '.py'
                    else f'export function handler{i}(value: number): number {{\n  return value + {i};\n}}\n')
            p.write_text(f'// module {i}\n' * (ext == '.ts') + body, encoding='utf-8')
        subprocess.run(['git', 'add', 'src'], cwd=root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', 'source'], cwd=root, check=True, capture_output=True)

    def instrument(self):
        w = self.w

        def counted(name, fn):
            def wrapper(*args, **kwargs):
                self.counts[name] += 1
                return fn(*args, **kwargs)
            return wrapper
        # The split runtime's modules (W9; absent before it) each bind what they import: wrap every binding.
        modules = [w] + [sys.modules[name] for name in RUNTIME_MODULES if name in sys.modules]
        for name in COUNTED:
            real = getattr(w, name)
            wrapper = counted(name, real)
            for module in modules:
                if getattr(module, name, None) is real:
                    setattr(module, name, wrapper)
        real_run = subprocess.run

        def run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and cmd and Path(str(cmd[0])).stem == 'git':
                self.counts['git_subprocess'] += 1
            return real_run(cmd, *args, **kwargs)
        subprocess.run = run

    # One CLI invocation, in-process, through the runtime's own main().
    def cli(self, phase, action, *args, stage=None, check=True):
        argv = ['workflow.py', '--root', str(self.root), action, '--feature', FEATURE, *args]
        before = dict(self.counts)
        out = io.StringIO()
        old_argv, sys.argv = sys.argv, argv
        started = time.perf_counter()
        try:
            with contextlib.redirect_stdout(out):
                code = self.w.main()
        except SystemExit as exc:
            code = exc.code
        finally:
            sys.argv = old_argv
        ms = (time.perf_counter() - started) * 1000
        text = out.getvalue()
        try:
            result = json.loads(text)
        except ValueError:
            result = {'raw': text}
        record = {'seq': len(self.commands) + 1, 'phase': phase, 'action': action, 'stage': stage,
                  'ms': round(ms, 1), 'stdout_bytes': len(text.encode('utf-8')), 'exit': code,
                  'counters': {k: self.counts[k] - before[k] for k in self.counts}}
        self.commands.append(record)
        if check and code and 'error' in result:
            raise RuntimeError(f'{action} {stage or ""} failed: {result["error"]}')
        return result

    def receipt(self, stage, merged=()):
        """test_workflow.py receipt(): minimal artifacts and evidence for `stage` (and merged stages)."""
        w, directory = self.w, self.root / FEATURE
        directory.mkdir(parents=True, exist_ok=True)
        index = max(w.BASE_STAGES.index(s) for s in (stage, *merged))
        inputs = []
        for name, first in (('spec.md', 'specify'), ('plan.md', 'plan'), ('tasks.md', 'tasks')):
            path = directory / name
            if index >= w.BASE_STAGES.index(first) and not path.exists():
                path.write_text('- [x] T001 Done behavior' if name == 'tasks.md' else '# Fixture ' + name,
                                encoding='utf-8')
            if first in merged: inputs.append(FEATURE + '/' + name)
        if index >= w.BASE_STAGES.index('specify') and not (directory / 'scope-source.json').exists():
            # `dependencies` (none) lets a lean PR receipt bind its lint; harmless where lean is off.
            # `score` is what Scope's gate verified (Workflow reads it instead of the issue's effort label).
            source = {'repo': 'acme/app', 'issue': 10, 'dependencies': []}
            if self.supports_profiles:
                source['score'] = TIER_SCORES[self.tier]
            w.write(directory / 'scope-source.json', source)
        if index >= w.BASE_STAGES.index('taskstoissues') and not (directory / 'workflow/task-issues.json').exists():
            w.write(directory / 'workflow/task-issues.json', {'repo': 'acme/app', 'parent': 10, 'feature': FEATURE,
                                                             'tasks': {'T001': {'number': 11, 'linked': True}}})
        evidence = FEATURE + '/evidence/' + stage + '.txt'
        p = self.root / evidence
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('actual fixture evidence', encoding='utf-8')
        receipt = {'stage': stage, 'summary': stage + ' tested', 'outcome': 'passed', 'inputs': [evidence, *inputs],
                   'evidence': [evidence], 'unresolved': 0, 'answers_applied': True, 'blocking_findings': 0,
                   'parent_issue': ISSUE, 'native_links_verified': True, 'images_verified': True,
                   'pr_url': 'https://github.com/acme/app/pull/11'}
        if stage == 'scope' and self.supports_profiles:
            receipt['effort_score'] = TIER_SCORES[self.tier]
        return receipt

    def file(self, name, value):
        # Outside the consumer: an untracked file there would change the source inventory.
        path = self.root.parent / ('bench-' + name)
        path.write_text(json.dumps(value), encoding='utf-8')
        return str(path)

    def step(self, phase, finalize=False):
        """Claim the next stage and complete it; returns the claimed stage or None."""
        usage = self.file('usage.json', USAGE)
        claim = self.cli(phase, 'claim', '--usage', usage, *(['--finalize'] if finalize else []))
        stage = claim.get('stage')
        self.commands[-1]['stage'] = stage
        if not stage:
            return None
        if 'token' not in claim:
            raise RuntimeError('claim returned no token: ' + json.dumps(claim)[:500])
        command = claim.get('command') or ''
        self.claimed.append({'phase': phase, 'stage': stage, 'command': command, 'merged': claim.get('merged') or [],
                             'protocol_in_claim': 'execute_protocol' in claim})
        receipt = self.receipt(stage, claim.get('merged') or ())
        if stage == 'pr' and 'environment' in claim:
            receipt.update(self.lean_pr_evidence())
        if command == 'workflow:lint':
            if self.lint_record(claim['token']):
                return stage
            # Lint asked for a model Analyze: the contract's fallback, and a model pass.
            receipt['command'] = self.claimed[-1]['command'] = self.w.COMMANDS['analyze']
        receipt = self.file('receipt.json', receipt)
        self.cli(phase, 'complete', '--token', claim['token'], '--receipt', receipt, stage=stage)
        return stage

    def lean_pr_evidence(self):
        """Lean execution binds the PR receipt to the exact body and its recomputed closing-reference lint."""
        body, body_label, lint_label = 'Closes #10' + chr(10), FEATURE + '/evidence/pr-body.md', FEATURE + '/evidence/pr-lint.json'
        (self.root / body_label).write_bytes(body.encode('utf-8'))
        lint = self.w.execution_tools.pr_lint(body, 'acme/app', 10, [])
        self.w.write(self.root / lint_label, lint)
        return {'pr_body_file': body_label, 'pr_lint_file': lint_label, 'pr_body_sha256': lint['body_sha256'],
                'evidence': [FEATURE + '/evidence/pr.txt', body_label, lint_label]}

    def lint(self, phase, *extra):
        """Run lint.py in the fixture (a separate process, so its counters are not counted); None when absent."""
        script = self.repo / 'extensions/workflow/scripts/lint.py'
        if not script.is_file():
            return None
        started = time.perf_counter()
        result = subprocess.run([sys.executable, str(script), '--root', str(self.root), '--feature', FEATURE, '--json', *extra],
                                cwd=self.root, capture_output=True, text=True)
        self.commands.append({'seq': len(self.commands) + 1, 'phase': phase, 'action': 'lint', 'stage': 'analyze',
                              'ms': round((time.perf_counter() - started) * 1000, 1),
                              'stdout_bytes': len(result.stdout.encode('utf-8')), 'exit': result.returncode,
                              'counters': dict.fromkeys(self.counts, 0)})
        if result.returncode:
            self.commands[-1]['note'] = (result.stdout + result.stderr)[-400:]
        return result

    def lint_record(self, token):
        """New runtime: analyze runs as `workflow:lint`; record it through lint.py when it can."""
        result = self.lint(self.claimed[-1]['phase'], '--record', '--token', token)
        return bool(result and result.returncode == 0
                    and self.w.read(self.root / FEATURE / 'workflow/checkpoint.json')['active'] is None)

    def lint_entry(self):
        """revalidate-upstream entry for a lint-run Analyze: the fresh lint result as evidence and `lint` field."""
        result = self.lint('recovery')
        report = json.loads(result.stdout) if result and result.returncode == 0 else {}
        if not report.get('ok') or report.get('needs_model_analyze'):
            raise RuntimeError('lint cannot stand in for Analyze: ' + json.dumps(report)[:300])
        evidence = FEATURE + '/evidence/lint-upstream.json'
        (self.root / evidence).write_text(result.stdout, encoding='utf-8')
        return {'summary': 'workflow:lint passed', 'evidence': [evidence],
                'inputs': [FEATURE + '/spec.md', FEATURE + '/plan.md', FEATURE + '/tasks.md'],
                'lint': {'ok': True, 'findings': len(report['findings'])}}

    def advance(self, phase, until):
        for _ in range(3 * len(self.w.BASE_STAGES)):  # a stage that keeps going stale must fail, not loop
            last = self.claimed[-1]['stage'] if self.claimed else None
            stage = self.step(phase, finalize=last == 'ready')
            if stage is None:
                raise RuntimeError(f'runtime offered no stage before {until} in {phase}')
            if stage == until:
                return
        raise RuntimeError(f'{until} not reached in {phase}: ' + ', '.join(c['stage'] for c in self.claimed[-8:]))

    def recover(self):
        """Cheapest recovery after the spec edit: revalidate-upstream (Specify..TasksToIssues) when the runtime
        has it, then re-claim whatever stays stale (Execute); otherwise re-claim every invalidated stage."""
        if 'revalidate-upstream' not in self.source:
            self.advance('recovery', 'execute')
            return 'per-stage-reclaim'
        try:
            through = ('--through', 'taskstoissues')
            plan = self.cli('recovery', 'revalidate-upstream', *through, '--plan')
            needed = plan.get('needs_receipt')
            if needed is None:
                raise RuntimeError('revalidate-upstream --plan: ' + json.dumps(plan)[:300])
            merged = {c['stage']: c['merged'] for c in self.claimed}  # plan carries tasks on lite/standard
            stages = {s: {k: v for k, v in self.receipt(s, merged.get(s, ())).items()
                          if k in ('summary', 'evidence', 'inputs')} for s in needed}
            commands = {c['stage']: c['command'] for c in self.claimed}
            if 'analyze' in stages and commands.get('analyze') == 'workflow:lint':
                stages['analyze'] = self.lint_entry()
            self.cli('recovery', 'revalidate-upstream', *through, '--receipt', self.file('upstream.json', {'stages': stages}))
            self.claimed.append({'phase': 'recovery', 'stage': 'revalidate-upstream', 'command': 'revalidate-upstream',
                                 'merged': sorted(stages)})
            path = 'revalidate-upstream'
        except RuntimeError as exc:
            self.recovery_error = str(exc)
            path = 'per-stage-reclaim (revalidate-upstream failed)'
        self.advance('recovery', 'execute')
        return path

    def run(self):
        self.recovery_error = None
        self.cli('start', 'start', '--issue', ISSUE)
        self.advance('first-pass', 'execute')
        spec = self.root / FEATURE / 'spec.md'
        spec.write_text(spec.read_text(encoding='utf-8') + '\nThe checkout message names the retry window.\n',
                        encoding='utf-8')
        self.cli('recovery', 'next')
        path = self.recover()
        self.cli('pause', 'pause', '--reason', 'benchmark handoff')
        self.advance('finish', 'pr')
        return path


def instruction_load(repo, claimed):
    """Static instruction bytes per stage from the checkout's skill, references, presets and commands."""
    def rel(path):
        return path.relative_to(repo).as_posix()

    def resolve(owner, link):
        if link.startswith('.specify/extensions/'):
            candidates = [repo / ('extensions/' + link[len('.specify/extensions/'):])]
        elif link.startswith(('extensions/', 'presets/')):
            candidates = [repo / link]
        else:
            link = link.lstrip('./')
            candidates = [owner.parent / link, owner.parent.parent / link, owner.parent.parent.parent / link,
                          repo / WORKFLOW_SKILL / link]
        return next((c.resolve() for c in candidates if c.is_file()), None)

    per_stage, direct, missing = {}, set(), set()
    seen = []
    for item in claimed:
        stage, command = item['stage'], item['command']
        if stage in per_stage or stage == 'revalidate-upstream':
            continue
        extras = [] if stage in PROTOCOL_IN_CLAIM and item.get('protocol_in_claim') else STAGE_EXTRAS.get(stage, [])
        names = [WORKFLOW_SKILL + 'SKILL.ext.md', WORKFLOW_SKILL + 'references/stage-' + stage + '.md',
                 WORKFLOW_SKILL + 'references/receipt-rules.md', *extras]
        overlay = 'presets/workflow/commands/' + command + '.md'
        if (repo / overlay).is_file(): names.append(overlay)
        files = {}
        for name in names:
            path = repo / name
            if path.is_file():
                files[name] = path.stat().st_size
                direct.add(path.resolve())
                seen.append(path)
            else:
                missing.add(name)
        per_stage[stage] = {'bytes': sum(files.values()), 'files': files}
    shared = {}
    for name in POINTER_SET:
        path = repo / name
        if path.is_file():
            shared[name] = path.stat().st_size
            direct.add(path.resolve())
            seen.append(path)
        else:
            missing.add(name)
    linked = {}
    for owner in dict.fromkeys(seen):
        for link in LINK.findall(owner.read_text(encoding='utf-8', errors='replace')):
            target = resolve(owner, link)
            if target is None:
                missing.add(link)
            elif target not in direct and rel(target) not in linked:
                linked[rel(target)] = target.stat().st_size
    total = sum(s['bytes'] for s in per_stage.values()) + sum(shared.values()) + sum(linked.values())
    return {'per_stage': per_stage, 'pointer_set_once': shared, 'linked_once': linked,
            'missing': sorted(missing), 'total_bytes': total, 'total_tokens': total // 4}


def size(path):
    return path.stat().st_size if path.is_file() else None


def measure(repo, tier='full', source_files=750):
    repo = Path(repo).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        consumer = Path(tmp).resolve() / 'app'
        consumer.mkdir()
        bench = Bench(repo, consumer, tier, source_files)
        real_run = subprocess.run
        started = time.perf_counter()
        try:
            recovery = bench.run()
        finally:
            subprocess.run = real_run  # instrument() replaced it for this measurement only
        wall = (time.perf_counter() - started) * 1000
        workflow_dir = bench.root / FEATURE / 'workflow'
        state = bench.w.read(workflow_dir / 'checkpoint.json')
        files = {'checkpoint_bytes': size(workflow_dir / 'checkpoint.json'),
                 'handoff_bytes': size(workflow_dir / 'handoff.md'),
                 'lifecycle_bytes': size(workflow_dir / 'lifecycle.jsonl')}
    cmds = bench.commands
    stage_claims = [c for c in bench.claimed if c['stage'] != 'revalidate-upstream']

    def by(action, key):
        return sum(c[key] for c in cmds if c['action'] == action)
    totals = {
        'commands': len(cmds), 'wall_ms': round(wall, 1), 'command_ms': round(sum(c['ms'] for c in cmds), 1),
        'stdout_bytes': sum(c['stdout_bytes'] for c in cmds),
        'claim_stdout_bytes': by('claim', 'stdout_bytes'), 'complete_stdout_bytes': by('complete', 'stdout_bytes'),
        'claims': sum(1 for c in cmds if c['action'] == 'claim'),
        'stages_run': len(stage_claims),
        'model_passes': sum(1 for c in bench.claimed if not c['command'].startswith('workflow:')),
        'recovery_stages': sum(1 for c in bench.claimed if c['phase'] == 'recovery'),
        **{k: sum(c['counters'][k] for c in cmds) for k in bench.counts},
        **files,
    }
    instructions = instruction_load(repo, bench.claimed)
    totals['instruction_bytes'] = instructions['total_bytes']
    totals['instruction_tokens'] = instructions['total_tokens']
    head = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip()
    tier_applied = bench.supports_profiles or bench.stages_take_tier
    return {
        'meta': {
            'repo': str(repo), 'repo_head': head, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'python': sys.version.split()[0], 'source_files': source_files, 'tier_requested': tier,
            'tier_applied': tier_applied,
            'tier_note': (f'profiles enabled; scope receipt effort_score={TIER_SCORES[tier]}' if bench.supports_profiles
                          else 'runtime has no profiles or tiered stages; --tier ignored'),
            'final_tier': (state.get('profile') or {}).get('tier'),
            'recovery_path': recovery, 'recovery_error': bench.recovery_error,
            'assumptions': ['tokens = bytes / 4', 'fixture receipts and artifacts from test_workflow.py; no model calls',
                            'stdout bytes are the CLI JSON printed by the runtime main(), run in-process',
                            'model_passes counts claimed stages whose command does not start with workflow: '
                            '(one revalidate-upstream operation counts as one pass)',
                            'counters wrap module-level functions; git_subprocess counts every git subprocess.run'],
        },
        'stage_sequence': bench.claimed,
        'commands': cmds,
        'totals': totals,
        'instructions': instructions,
    }


def markdown(result):
    t = result['totals']
    lines = ['| metric | value |', '| --- | --- |'] + [f'| {k} | {v} |' for k, v in t.items()]
    lines += ['', '| stage | instruction bytes | tokens |', '| --- | --- | --- |']
    lines += [f'| {s} | {v["bytes"]} | {v["bytes"] // 4} |' for s, v in result['instructions']['per_stage'].items()]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--repo', type=Path, required=True, help='Sanduq checkout whose runtime is measured')
    parser.add_argument('--out', type=Path, required=True, help='JSON output path')
    parser.add_argument('--tier', choices=sorted(TIER_SCORES), default='full')
    parser.add_argument('--source-files', type=int, default=750)
    args = parser.parse_args(argv)
    result = measure(args.repo, args.tier, args.source_files)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(markdown(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
