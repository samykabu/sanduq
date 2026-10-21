#!/usr/bin/env python3
"""Bump source versions, prepare immutable pending releases, publish/verify assets, then promote catalogs.

`check-bumps` (lint) fails when a package's shipped files changed without a version bump (X23).
Only `bump <id> <version>` changes source versions: it writes every copy (extension.yml, the
extensions/README.md row, Workflow's dependencies.json pins, pending-releases.json) and leaves
status `ready` to a maintainer. Public catalogs change only in promote, following successful
remote asset verification; promote also drops "(pending release)" from the root CHANGELOG
headings that name a promoted version.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import yaml
from packaging.version import Version
from package import package, package_files, ROOT

REPO = 'samykabu/sanduq'
URL = 'https://github.com/' + REPO


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition: raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps(value).encode('utf-8'))  # LF on every OS


def dumps(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + '\n'


PENDING_MARK = ' (pending release)'
NAMED_VERSION = re.compile(r'([A-Za-z][A-Za-z-]*(?: [A-Z][A-Za-z-]*)*) (\d+\.\d+\.\d+)\b')


def heading_versions(heading):
    """{extension id: version} named in a changelog heading ("User Manual 1.6.0" -> user-manual)."""
    return {name.lower().replace(' ', '-'): version for name, version in NAMED_VERSION.findall(heading)}


def bump(name, version, root=ROOT):
    """Write `version` into every source copy of extension `name`; all files or none."""
    require(re.fullmatch(r'[a-z][a-z0-9-]*', name or ''), 'Invalid extension ID')
    require(re.fullmatch(r'\d+\.\d+\.\d+', version or ''), 'Bump requires X.Y.Z version')
    manifest_path = root / 'extensions' / name / 'extension.yml'
    require(manifest_path.is_file(), 'Unknown extension: ' + name)
    text = manifest_path.read_bytes().decode('utf-8')
    old = str(yaml.safe_load(text)['extension']['version'])
    require(Version(version) >= Version(old), f'{name}: {version} is lower than the source version {old}')
    # Replace only the value on the extension block's version line, so comments and key order survive.
    # `\r?` keeps a CRLF working copy (core.autocrlf) working; every byte but the version stays as it was.
    block = re.search(r'^extension:\r?\n(?:[ \t]+.*\n|\r?\n)*', text, re.M)
    require(block, f'{manifest_path}: no extension block')
    line = re.compile(r'^([ \t]+version:[ \t]*)(["\']?)' + re.escape(old) + r'\2', re.M)
    new_block, count = line.subn(lambda m: m.group(1) + m.group(2) + version + m.group(2), block.group(0), count=1)
    require(count == 1, f'{manifest_path}: version line not found')
    changes = {manifest_path: text[:block.start()] + new_block + text[block.end():]}
    require(str(yaml.safe_load(changes[manifest_path])['extension']['version']) == version, 'Manifest rewrite failed')
    index = root / 'extensions/README.md'
    if index.is_file():
        row = re.compile(r'^(\| \[' + re.escape(name) + r'\]\(' + re.escape(name) + r'/README\.md\) \| )[^|]+( \|)', re.M)
        changes[index], count = row.subn(lambda m: m.group(1) + version + m.group(2), index.read_bytes().decode('utf-8'))
        require(count == 1, f'{index}: no version row for {name}')
    deps_path = root / 'extensions/workflow/dependencies.json'
    if deps_path.is_file():
        deps = read(deps_path)

        def pin(node):
            for key, value in node.items():
                if isinstance(value, dict):
                    pin(value)
                elif key == name and isinstance(value, str):
                    node[key] = version
        for section in ('required', 'selected', 'optional'):
            pin(deps.get(section) or {})
        changes[deps_path] = dumps(deps)
    pending_path = root / 'extensions/pending-releases.json'
    pending = read(pending_path)
    pending['versions'][name] = version
    if pending.get('status') in ('ready', 'released'):
        pending['status'] = 'implementation-in-progress'  # a new version needs review before `ready`
    changes[pending_path] = dumps(pending)
    written = []
    for path, content in changes.items():
        if path.read_bytes() != content.encode('utf-8'):
            path.write_bytes(content.encode('utf-8'))
            written.append(path.relative_to(root).as_posix())
    return {'id': name, 'from': old, 'to': version, 'written': written}


# Human documentation at a package's top level; nested README.md or CHANGELOG.md (templates, presets, skills) is
# agent input and stays covered (X23).
UNVERSIONED = re.compile(r'[^/]+/(?:README\.md|CHANGELOG\.md|LICENSE|docs/.+)')


def inventory_sha256(name, root=ROOT):
    """sha256 of the behaviour a package ships: every packaged file, injected helpers and bundled presets
    included, except UNVERSIONED. CRLF hashes as LF, so a Windows working copy agrees with CI."""
    lines = sorted(member + '\0' + hashlib.sha256(content.replace(b'\r\n', b'\n')).hexdigest()
                   for member, content in package_files(name, root).items() if not UNVERSIONED.fullmatch(member))
    return hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()


def check_bumps(root=ROOT):
    """X23: a package whose shipped behaviour differs from its catalog entry needs a version above the catalog's,
    in its manifest or in pending-releases.json. An entry without `inventory_sha256` is skipped with a notice."""
    catalog = read(root / 'catalog.json')['extensions']
    pending = read(root / 'extensions/pending-releases.json').get('versions') or {}
    failures, notices = [], []
    for manifest in sorted((root / 'extensions').glob('*/extension.yml')):
        name, entry = manifest.parent.name, catalog.get(manifest.parent.name)
        if entry is None:
            continue  # never released: nothing to compare with
        version = str(yaml.safe_load(manifest.read_text(encoding='utf-8'))['extension']['version'])
        if any(v and Version(v) > Version(entry['version']) for v in (version, pending.get(name))):
            continue
        if not entry.get('inventory_sha256'):
            notices.append(f'{name} {entry["version"]}: no inventory_sha256 in catalog.json; its next release records it')
        elif inventory_sha256(name, root) != entry['inventory_sha256']:
            failures.append(f'{name}: shipped files changed since {entry["version"]} was released; '
                            f'run `release.py bump {name} <X.Y.Z>`')
    return {'ok': not failures, 'failures': failures, 'notices': notices}


def clear_pending_headings(released, root=ROOT):
    """Drop the pending marker from root CHANGELOG headings that name a version in `released`."""
    path = root / 'CHANGELOG.md'
    if not path.is_file():
        return []
    lines = path.read_bytes().decode('utf-8').split('\n')
    cleared = []
    for i, line in enumerate(lines):
        if line.startswith('## ') and line.endswith(PENDING_MARK) and \
                set(heading_versions(line).items()) & set(released.items()):
            lines[i] = line[:-len(PENDING_MARK)]
            cleared.append(lines[i])
    if cleared:
        path.write_bytes('\n'.join(lines).encode('utf-8'))
    return cleared


def command(args, root=ROOT):
    result = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding='utf-8')
    require(result.returncode == 0, 'Command failed: ' + ' '.join(args) + ': ' + result.stderr.strip())
    return result.stdout.strip()


def prepare(root=ROOT, development=False):
    pending = read(root / 'extensions/pending-releases.json')
    versions = pending['versions']
    clean = not command(['git','status','--porcelain','--untracked-files=all'],root)
    status = pending.get('status')
    publishable = clean and status in ('ready', 'released')
    if not development:
        require(clean, 'Release requires a clean checkout; commit or stash local changes (use --development for a non-publishable preview)')
        require(status in ('ready', 'released'), f'Release requires pending status ready or released; it is {status!r}. Reviewed work stays unpublished until a maintainer marks it ready (use --development for a non-publishable preview)')
    catalog = read(root / 'catalog.json')
    require(catalog == read(root / 'extensions/catalog.json'), 'Public catalogs differ')
    releases = []
    for name, version in versions.items():
        require(re.fullmatch(r'[a-z][a-z0-9-]*', name), 'Invalid extension ID')
        require(re.fullmatch(r'\d+\.\d+\.\d+', version), 'Release requires X.Y.Z version')
        doc = yaml.safe_load((root / 'extensions' / name / 'extension.yml').read_text(encoding='utf-8'))
        meta = doc['extension']
        require((meta['id'], str(meta['version']), meta['repository']) == (name, version, URL), 'Pending manifest mismatch: ' + name)
        old = catalog['extensions'].get(name)
        require(not old or Version(version) > Version(old['version']), 'Pending version must exceed published version: ' + name)
        built = package(name, root=root)
        entry = dict(old or {})
        entry.update({key: meta.get(key, '') for key in ('name','id','version','description','author','license')})
        entry.update({'repository':URL,'homepage':URL+'/tree/main/extensions/'+name,
                      'documentation':URL+'/blob/main/extensions/'+name+'/README.md',
                      'changelog':URL+'/blob/main/extensions/'+name+'/CHANGELOG.md',
                      'download_url':f'{URL}/releases/download/{name}-v{version}/{name}.zip',
                      'requires':doc.get('requires',{}),'provides':{'commands':len(doc.get('provides',{}).get('commands',[])), 'hooks':len(doc.get('hooks',{}))},
                      'tags':doc.get('tags',[]),'category':meta.get('category','process'),
                      'effect':meta.get('effect','read-write'),'verified':False,
                      'sha256':built['sha256'],'inventory_sha256':inventory_sha256(name,root),'updated_at':datetime.now(timezone.utc).isoformat()})
        catalog['extensions'][name] = entry
        releases.append({'id':name,'version':version,'tag':name+'-v'+version,'asset':name+'.zip',
                         'archive':(Path('dist')/(name+'.zip')).as_posix(),'sha256':built['sha256']})
    catalog['updated_at'] = datetime.now(timezone.utc).isoformat()
    result = {'schema_version':1,'publishable':publishable and not development,'source_commit':command(['git','rev-parse','HEAD'],root),
              'catalog_before_sha256':sha(root/'catalog.json'),'pending_sha256':sha(root/'extensions/pending-releases.json'),
              'releases':releases,'catalog':catalog}
    write(root/'dist/release-plan.json', result)
    return result


def gh_json(args, root=ROOT):
    return json.loads(command(['gh',*args],root))


def verify_asset(release, root=ROOT):
    local = root / release['archive']
    require(sha(local) == release['sha256'], 'Local archive changed after prepare')
    info = gh_json(['release','view',release['tag'],'--repo',REPO,'--json','isDraft,assets'],root)
    require(not info['isDraft'], 'Release is still draft: ' + release['tag'])
    require(len([a for a in info['assets'] if a['name']==release['asset']]) == 1, 'Missing or duplicate release asset')
    folder = Path(tempfile.mkdtemp(prefix='verify-release-',dir=root/'dist'))
    require(folder.resolve().is_relative_to((root/'dist').resolve()), 'Invalid verification directory')
    command(['gh','release','download',release['tag'],'--repo',REPO,'--pattern',release['asset'],'--dir',str(folder)],root)
    require(sha(folder/release['asset']) == release['sha256'], 'IMMUTABLE_ASSET_MISMATCH: bump the version; never clobber')
    return {'tag':release['tag'],'sha256':release['sha256'],'verified':True}


def publish(root=ROOT, apply=False):
    plan = read(root/'dist/release-plan.json')
    require(plan['source_commit']==command(['git','rev-parse','HEAD'],root), 'Source commit changed since prepare')
    if not apply: return {'applied':False,'releases':plan['releases']}
    require(plan.get('publishable'), 'Development preview cannot be published')
    # List all published/draft releases once. A failure is not interpreted as absence.
    pages = gh_json(['api',f'repos/{REPO}/releases?per_page=100','--paginate','--slurp'],root)
    existing = {r['tag_name'] for page in pages for r in page}
    verified = []
    for release in plan['releases']:
        require(sha(root/release['archive']) == release['sha256'], 'Local archive changed after prepare')
        if release['tag'] not in existing:
            notes=root/'dist'/(release['id']+'-release-notes.md')
            notes.write_text(f"{release['id']} {release['version']}\n\nInstall this immutable package:\n\n"
                             f"`specify extension add {release['id']} --from {URL}/releases/download/{release['tag']}/{release['asset']}`\n\n"
                             f"SHA-256: `{release['sha256']}`\n",encoding='utf-8')
            command(['gh','release','create',release['tag'],str(root/release['archive']),'--repo',REPO,
                     '--target',plan['source_commit'],'--title',release['id']+' '+release['version'],
                     '--notes-file',str(notes)],root)
        verified.append(verify_asset(release,root))
    receipt={'plan_sha256':sha(root/'dist/release-plan.json'),'assets':verified}
    write(root/'dist/release-verification.json',receipt)
    return receipt


def promote(root=ROOT, verifier=verify_asset):
    plan=read(root/'dist/release-plan.json');receipt=read(root/'dist/release-verification.json')
    require(plan.get('publishable'), 'Development preview cannot be promoted')
    require(command(['git','rev-parse','HEAD'],root) == plan['source_commit'], 'Source commit changed since prepare')
    require(receipt['plan_sha256']==sha(root/'dist/release-plan.json'),'Release verification belongs to another plan')
    require(sha(root/'catalog.json')==plan['catalog_before_sha256'],'Public catalog changed since prepare')
    require(sha(root/'extensions/pending-releases.json')==plan['pending_sha256'],'Pending releases changed since prepare')
    expected={r['tag']:r['sha256'] for r in plan['releases']}
    require({r['tag']:r['sha256'] for r in receipt['assets'] if r.get('verified')}==expected,'Not every asset is verified')
    for release in plan['releases']: verifier(release,root)
    if not plan['releases']: return {'promoted':[],'written':[]}
    write(root/'catalog.json',plan['catalog']);write(root/'extensions/catalog.json',plan['catalog'])
    pending=read(root/'extensions/pending-releases.json')
    for release in plan['releases']: pending['versions'].pop(release['id'])
    pending['status']='released' if not pending['versions'] else 'pending'
    write(root/'extensions/pending-releases.json',pending)
    cleared=clear_pending_headings({r['id']:r['version'] for r in plan['releases']},root)
    # The release job stages exactly these paths (release-extensions.yml; test_release_promote.py checks it).
    written=['catalog.json','extensions/catalog.json','extensions/pending-releases.json']+(['CHANGELOG.md'] if cleared else [])
    return {'promoted':[r['tag'] for r in plan['releases']],'changelog_headings_released':cleared,'written':written}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('bump','prepare','publish','promote','check-bumps'))
    parser.add_argument('target',nargs='*',metavar='ID VERSION',help='bump only: extension id and new X.Y.Z version')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--development',action='store_true',help='Prepare a preview which cannot be published')
    args=parser.parse_args()
    try:
        require(len(args.target)==(2 if args.action=='bump' else 0),'bump takes an extension id and a version; other actions take none')
        result=bump(*args.target) if args.action=='bump' else prepare(development=args.development) if args.action=='prepare' else publish(apply=args.apply) if args.action=='publish' else check_bumps() if args.action=='check-bumps' else promote()
        print(json.dumps({k:v for k,v in result.items() if k!='catalog'},indent=2))
        if result.get('ok') is False: raise SystemExit(1)
    except (ValueError,OSError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}));raise SystemExit(1)
