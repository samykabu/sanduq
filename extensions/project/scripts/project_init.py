#!/usr/bin/env python3
"""One-time setup for the 'project' extension: discover a GitHub Project (v2), map the lifecycle phases
to the board's Status columns (exact, then fuzzy, then optional auto-create) and write
.specify/extensions/project/config.json. A rerun keeps parentIssue, subIssues and stateFile (and hookMode
when no mode is passed). It never prompts.

Usage: project_init.py [--owner <login>] [--number <n>] [--owner-type user|org]
                       [--hooks-mode optional|required] [--auto-create-columns]
                       [--allow-status-reset] [--dry-run] [--json]

The PowerShell spellings (-Owner, -Number, -OwnerType, -HooksMode, -AutoCreateColumns, -NonInteractive,
-AllowStatusReset, -DryRun, -Json) are accepted too; --non-interactive is accepted and ignored.
--allow-status-reset changes columns even when the board's item statuses cannot be read; they are then cleared.

Exit codes: 0 written (printed under --dry-run); 1 error, or an item whose Status could not be set again;
2 bad flag value; 4 a missing choice, with `{"ok": false, "needs": [{flag, why, options}]}` as the last
stdout line. Standard library only; needs `gh` with the `project` scope.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import project_sync  # in a source checkout it also puts the shared helpers on sys.path
import sanduq_gh

FLAGS = {'--owner': '-Owner', '--number': '-Number', '--owner-type': '-OwnerType', '--hooks-mode': '-HooksMode',
         '--auto-create-columns': '-AutoCreateColumns', '--non-interactive': '-NonInteractive',
         '--allow-status-reset': '-AllowStatusReset', '--dry-run': '-DryRun', '--json': '-Json'}
POWERSHELL = {ps.lower(): bash for bash, ps in FLAGS.items()}
PHASES = ('open', 'analysis', 'engineer-review', 'ready', 'in-progress', 'in-review', 'done')
PALETTE = ('GRAY', 'BLUE', 'PURPLE', 'GREEN', 'YELLOW', 'ORANGE', 'PINK')
EXT_DIR = Path('.specify/extensions/project')
ITEMS = ('query{node(id:%s){... on ProjectV2{items(first:100%s,archivedStates:[ARCHIVED,NOT_ARCHIVED]){'
         'pageInfo{hasNextPage endCursor} nodes{id isArchived fieldValueByName(name:"Status"){'
         '... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}')


class Die(Exception):
    """An error: printed as `[project-init][error]`, exit 1."""


def info(message):
    print('[project-init] ' + message)


def warn(message):
    print('[project-init][warn] ' + message)


def gh(*args):
    """(returncode, output) through the Project sync runner (120 s timeout, 127 when gh is missing)."""
    return project_sync.gh_raw(list(args))


def gh_ok(message, *args):
    rc, out = gh(*args)
    if rc:
        raise Die(message + ': ' + out)
    return out


def graphql(query):
    return gh('api', 'graphql', '-f', 'query=' + query)


def norm(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def set_hook_mode(mode, dry_run):
    """Sets `optional:` on every project hook in .specify/extensions.yml, keeping its line endings."""
    path = Path('.specify/extensions.yml')
    if not path.is_file():
        raise Die(".specify/extensions.yml not found - install with 'specify extension add project' before init")
    lines = path.read_bytes().decode('utf-8').splitlines(keepends=True)
    inside, count = False, 0
    for index, line in enumerate(lines):
        body = line.rstrip('\r\n')
        if re.fullmatch(r'\s*-\s+extension:\s+project\s*', body):
            inside = True
            continue
        if re.match(r'\s*-\s+extension:\s+', body):
            inside = False
        match = inside and re.fullmatch(r'(\s*optional:\s*)(?:true|false)\s*', body)
        if match:
            lines[index] = match[1] + ('true' if mode == 'optional' else 'false') + line[len(body):]
            count += 1
            inside = False
    if not count:
        raise Die('no project sync hooks found in .specify/extensions.yml - reinstall the project extension and retry')
    if dry_run:
        info('DRYRUN would set %d project sync hook(s) to %s' % (count, mode))
        return
    path.write_bytes(''.join(lines).encode('utf-8'))
    info('set %d project sync hook(s) to %s' % (count, mode))


class Init:
    def __init__(self, args):
        self.args = args
        self.restore_failed = False

    def read_items(self, project_id):
        """[(id, archived, status)] of every item with a Status, archived ones too; (None, error) when unreadable."""
        saved, cursor = [], None
        while True:
            after = ',after:' + json.dumps(cursor) if cursor else ''
            rc, out = graphql(ITEMS % (json.dumps(project_id), after))
            try:
                items = json.loads(out)['data']['node']['items'] if rc == 0 else None
            except (ValueError, KeyError, TypeError):
                items = None
            if not items:
                return None, out or 'no answer'
            saved += [(node['id'], bool(node.get('isArchived')), node['fieldValueByName']['name'])
                      for node in items['nodes'] if (node.get('fieldValueByName') or {}).get('name')]
            if not items['pageInfo']['hasNextPage']:
                return saved, None
            cursor = items['pageInfo']['endCursor']

    def restore(self, project_id, field_id, saved, options, renamed):
        """Sets each saved item's Status again by name; an archived item is unarchived, set and archived again."""
        failures = []
        for item, archived, status in saved:
            option = options.get(renamed.get(status, status))
            label = item + (' (archived)' if archived else '')
            pair = 'projectId:%s,itemId:%s' % (json.dumps(project_id), json.dumps(item))
            if not option:
                failures.append("%s was '%s': no such column after the update" % (label, status))
                continue
            if archived:
                rc, out = graphql('mutation{unarchiveProjectV2Item(input:{%s}){item{id}}}' % pair)
                if rc:
                    failures.append("%s was '%s': %s" % (label, status, out))
                    continue
            rc, out = gh('project', 'item-edit', '--id', item, '--project-id', project_id, '--field-id', field_id,
                         '--single-select-option-id', option)
            ok = rc == 0
            if archived:
                again_rc, again = graphql('mutation{archiveProjectV2Item(input:{%s}){item{id}}}' % pair)
                if again_rc:
                    ok, out = False, out + '; left unarchived: ' + again
            if not ok:
                failures.append("%s was '%s': %s" % (label, status, out))
        info('restored Status on %d of %d item(s)' % (len(saved) - len(failures), len(saved)))
        for failure in failures:
            warn('item Status not restored, set it by hand: ' + failure)
        self.restore_failed = bool(failures)

    def run(self):
        args = self.args
        root = project_sync.git('rev-parse', '--show-toplevel')
        if not root:
            raise Die('not inside a git repository')
        os.chdir(root)
        default_path = Path(__file__).resolve().parents[1] / 'config.default.json'
        if not default_path.is_file():
            default_path = EXT_DIR / 'config.default.json'
        if not default_path.is_file():
            raise Die('config.default.json not found')
        defaults = json.loads(default_path.read_text(encoding='utf-8-sig'))
        out_path = EXT_DIR / 'config.json'
        existing = {}
        if out_path.is_file():
            try:
                existing = json.loads(out_path.read_text(encoding='utf-8-sig'))
            except ValueError:
                raise Die(out_path.as_posix() + ' is not valid JSON - fix or delete it, then rerun') from None
        managed = Path('.specify/workflow.yml').is_file()
        wanted_by_phase, required = defaults['phaseToStatus'], []
        if managed:
            done = subprocess.run([sys.executable, '.specify/extensions/workflow/scripts/workflow.py', 'project-defaults'],
                                  capture_output=True, text=True, encoding='utf-8')
            try:
                answer = json.loads(done.stdout) if done.returncode == 0 else None
            except ValueError:
                answer = None
            if not isinstance(answer, dict):
                raise Die('cannot read managed workflow phase defaults; run workflow doctor')
            wanted_by_phase, required = answer.get('phaseToStatus') or {}, list(answer.get('statuses') or [])

        rc, auth = gh('auth', 'status')
        if rc == 127:
            raise Die('gh CLI not installed')
        if rc:
            raise Die('gh not authenticated - run: gh auth login')
        if 'project' not in sanduq_gh.token_scopes(auth):  # 'read:project' alone cannot write the board
            raise Die("gh token lacks 'project' scope - run: gh auth refresh -h github.com -s project,read:project")

        owner = args.owner
        if not owner:
            rc, login = gh('api', 'user', '--jq', '.login')
            owner = '' if rc else login.strip()
        if not owner:
            raise Die('could not resolve owner - pass --owner')
        needs = []
        owner_type = args.owner_type
        if not owner_type:
            # 'gh project list' accepts org logins too, so only the account type tells the two apart
            rc, kind = gh('api', 'users/' + owner, '--jq', '.type')
            if rc or not kind.strip():
                needs.append({'flag': '--owner-type', 'why': 'cannot tell whether %s is a user or an organization' % owner,
                              'options': ['user', 'org']})
            owner_type = 'org' if kind.strip() == 'Organization' else 'user'
        number = args.number
        if not number or number <= 0:
            listed = json.loads(gh_ok('could not list projects for ' + owner, 'project', 'list', '--owner', owner,
                                      '--format', 'json') or '{}').get('projects') or []
            if not listed:
                raise Die('no projects for %s - create one or pass --number' % owner)
            if len(listed) == 1:
                number = listed[0]['number']
            else:
                needs.append({'flag': '--number', 'why': 'several projects for ' + owner,
                              'options': [{'number': p['number'], 'title': p.get('title', '')} for p in listed]})
        for need in needs:
            options = ', '.join('#%s %s' % (o['number'], o['title']) if isinstance(o, dict) else o for o in need['options'])
            print('[project-init] choice needed: %s: %s - ask which one and rerun with %s <value>'
                  % (need['why'], options, need['flag']))
        if needs:
            print(json.dumps({'ok': False, 'needs': needs}))
            return 4
        info('owner: %s (%s)' % (owner, owner_type))
        info('project #%s' % number)

        view = json.loads(gh_ok('cannot view project #%s' % number, 'project', 'view', str(number), '--owner', owner,
                                '--format', 'json'))
        project_id, project_url = view['id'], view.get('url', '')
        fields = json.loads(gh_ok('cannot list fields', 'project', 'field-list', str(number), '--owner', owner,
                                  '--format', 'json'))
        field = next((f for f in fields.get('fields', []) if f.get('name') == 'Status' and f.get('options')), None)
        if not field:
            raise Die("no single-select 'Status' field on project #%s" % number)
        board = [option['name'] for option in field['options']]
        options = {option['name']: option['id'] for option in field['options']}
        info('board Status columns: ' + ', '.join(board))

        phase_status, create = {}, {}  # create: name -> {color, from (a column renamed to it), phases}

        def map_column(phase, wanted, color):
            label = "phase '%s'" % phase if phase else "status '%s'" % wanted
            # managed: doctor and Scope compare exact names, so only an exact (case-sensitive) column matches
            match = next((c for c in board if c == wanted), None)
            if not match and not managed:
                match = next((c for c in board if c.lower() == wanted.lower()), None) or next(
                    (c for c in board if norm(c) and norm(wanted) and
                     (norm(c) == norm(wanted) or norm(wanted) in norm(c) or norm(c) in norm(wanted))), None)
            if match:
                if phase:
                    phase_status[phase] = match
                info('  %-16s -> %s' % (phase or 'status', match))
                return
            if wanted in create:  # one column per name
                create[wanted]['phases'] += [phase] if phase else []
                return
            # managed: a column that differs only in case or spacing is renamed rather than duplicated
            variant = next((c for c in board if norm(c) == norm(wanted)), None) if managed else None
            if args.auto_create_columns:
                create[wanted] = {'color': color, 'from': variant, 'phases': [phase] if phase else []}
            else:
                warn("%s has no column (wanted '%s') - that transition is a no-op until mapped; rerun with "
                     '--auto-create-columns to create it, or add the column on the board and rerun' % (label, wanted))

        for index, phase in enumerate(PHASES):
            if wanted_by_phase.get(phase):
                map_column(phase, wanted_by_phase[phase], PALETTE[index % len(PALETTE)])
        for name in required:
            map_column(None, name, 'GRAY')

        if create and args.dry_run:
            for name, entry in create.items():
                info("DRYRUN rename column '%s' to '%s'" % (entry['from'], name) if entry['from']
                     else "DRYRUN create column '%s'" % name)
        elif create:
            self.create_columns(project_id, field, create, options, phase_status)

        hooks_mode = 'required' if managed else args.hooks_mode
        if not hooks_mode:
            hooks_mode = existing.get('hookMode') if existing.get('hookMode') in ('optional', 'required') else 'optional'
            info('hook mode not supplied; using %s (rerun with --hooks-mode optional|required to choose)' % hooks_mode)
        if managed:
            info('Sanduq workflow owns lifecycle dispatch; preserving reconciled hook entries')
        else:
            set_hook_mode(hooks_mode, args.dry_run)

        mapped = {phase: phase_status[phase] for phase in PHASES if phase in phase_status}
        order = list(dict.fromkeys(mapped.values()))
        keep = lambda key: existing[key] if key in existing else defaults.get(key)
        config = {'owner': owner, 'ownerType': owner_type, 'hookMode': hooks_mode, 'projectNumber': int(number),
                  'projectId': project_id, 'projectUrl': project_url, 'statusFieldId': field['id'],
                  'statusOptions': options, 'phaseToStatus': mapped, 'statusOrder': order,
                  'parentIssue': keep('parentIssue'), 'subIssues': keep('subIssues'), 'stateFile': keep('stateFile')}
        text = json.dumps(config, indent=2, ensure_ascii=False) + '\n'
        if args.dry_run:
            info('DRYRUN would write %s:' % out_path.as_posix())
            print(text, end='')
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(text.encode('utf-8'))
            info('wrote ' + out_path.as_posix())
        info('done. Next: commit config.json, then dry-run: python %s/scripts/project_sync.py --phase open --dry-run'
             % EXT_DIR.as_posix())
        if args.json:
            print(json.dumps(config, ensure_ascii=False, separators=(',', ':')))
        return 1 if self.restore_failed else 0

    def create_columns(self, project_id, field, create, options, phase_status):
        """One option update (it replaces every option, so every id is new), with each item's Status saved
        by name before and set again after."""
        renamed = {entry['from']: name for name, entry in create.items() if entry['from']}
        rows = ['{name:%s,color:%s,description:""}' % (json.dumps(renamed.get(o['name'], o['name'])),
                                                        (o.get('color') or 'GRAY').upper()) for o in field['options']]
        rows += ['{name:%s,color:%s,description:""}' % (json.dumps(name), entry['color'])
                 for name, entry in create.items() if not entry['from']]
        # GraphQL, not `gh project item-list`, which leaves archived items out.
        saved, error = self.read_items(project_id)
        if error and self.args.allow_status_reset:
            saved = []
            warn("cannot read the board's items (%s); --allow-status-reset: their Status will be cleared" % error)
        elif error:
            raise Die("cannot read the board's items, so their Status could not be restored after the column change: "
                      '%s - fix access and rerun, or pass --allow-status-reset to accept that every item loses its Status'
                      % error)
        rc, out = graphql('mutation{updateProjectV2Field(input:{fieldId:%s,singleSelectOptions:[%s]}){projectV2Field{'
                          '... on ProjectV2SingleSelectField{options{id name}}}}}' % (json.dumps(field['id']), ','.join(rows)))
        try:
            fresh = json.loads(out)['data']['updateProjectV2Field']['projectV2Field']['options'] if rc == 0 else None
        except (ValueError, KeyError, TypeError):
            fresh = None
        if fresh is None:
            warn('column creation failed: ' + out)
            return
        options.clear()
        options.update({option['name']: option['id'] for option in fresh})
        self.restore(project_id, field['id'], saved, options, renamed)
        for name, entry in create.items():
            if name in options:
                phase_status.update({phase: name for phase in entry['phases']})
                info('  created & mapped %-16s -> %s' % (','.join(entry['phases']), name))


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     allow_abbrev=False)
    parser.add_argument('--owner')
    parser.add_argument('--number', type=int, default=0)
    parser.add_argument('--owner-type', choices=('user', 'org'))
    parser.add_argument('--hooks-mode', choices=('optional', 'required'))
    for flag in ('--auto-create-columns', '--non-interactive', '--allow-status-reset', '--dry-run', '--json'):
        parser.add_argument(flag, action='store_true')
    args, unknown = parser.parse_known_args([POWERSHELL.get(arg.lower(), arg) for arg in argv])
    for arg in unknown:
        warn('unknown arg: ' + arg)
    return args


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # column names are not ASCII-only
    args = parse(sys.argv[1:] if argv is None else argv)
    try:
        return Init(args).run()
    except (Die, RuntimeError) as exc:
        print('[project-init][error] ' + str(exc))
        return 1
    except (ValueError, KeyError, TypeError) as exc:
        print('[project-init][error] unexpected gh output: %s: %s' % (type(exc).__name__, exc))
        return 1


if __name__ == '__main__':
    sys.exit(main())
