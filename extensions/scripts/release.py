#!/usr/bin/env python3
"""Prepare immutable pending releases, publish/verify assets, then promote catalogs.

No command changes source manifest versions. Maintainers review versions in
extensions/pending-releases.json before CI. Public catalogs change only in promote,
following successful remote asset verification.
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
from package import package, ROOT

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
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def command(args, root=ROOT):
    result = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding='utf-8')
    require(result.returncode == 0, 'Command failed: ' + ' '.join(args) + ': ' + result.stderr.strip())
    return result.stdout.strip()


def prepare(root=ROOT, development=False):
    pending = read(root / 'extensions/pending-releases.json')
    versions = pending['versions']
    clean = not command(['git','status','--porcelain','--untracked-files=all'],root)
    publishable = clean and pending.get('status') in ('ready', 'released')
    require(development or publishable, 'Release requires a clean checkout and pending status ready (use --development for a non-publishable preview)')
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
                      'sha256':built['sha256'],'updated_at':datetime.now(timezone.utc).isoformat()})
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
    if not plan['releases']: return {'promoted':[]}
    write(root/'catalog.json',plan['catalog']);write(root/'extensions/catalog.json',plan['catalog'])
    pending=read(root/'extensions/pending-releases.json')
    for release in plan['releases']: pending['versions'].pop(release['id'])
    pending['status']='released' if not pending['versions'] else 'pending'
    write(root/'extensions/pending-releases.json',pending)
    return {'promoted':[r['tag'] for r in plan['releases']]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','publish','promote'))
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--development',action='store_true',help='Prepare a preview which cannot be published')
    args=parser.parse_args()
    try:
        result=prepare(development=args.development) if args.action=='prepare' else publish(apply=args.apply) if args.action=='publish' else promote()
        print(json.dumps({k:v for k,v in result.items() if k!='catalog'},indent=2))
    except (ValueError,OSError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}));raise SystemExit(1)
