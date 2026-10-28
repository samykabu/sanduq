"""Isolated CODEX_HOME for one T07 run, so a measured Codex session sees no user-global instructions.

usage: python codex-home.py prepare <clone> <home>   create/refresh <home>, print it
       python codex-home.py sync <home>              after a session: hand a refreshed login back
       python codex-home.py check <home>             self-check of <home> (no model call)

prepare copies only auth.json from the real CODEX_HOME (~/.codex unless $CODEX_HOME is set) and writes a
config.toml with just the model settings the PH-04 runs used (model, reasoning effort, verbosity, service
tier, read from the real config), hooks on (the project's Sanduq hooks), memories off, and the clone
trusted (so its .codex/ agents, config and hooks load), and every user skill under ~/.agents/skills
disabled (Codex reads that folder whatever CODEX_HOME or HOME say; the clone's own .agents/skills and the
built-in system skills stay). Not copied: AGENTS.md, skills, plugins and marketplaces, MCP servers,
rules, memories, sessions, notify. Approvals and sandbox come from the
runner's --dangerously-bypass-approvals-and-sandbox flag, not from config.

sync: a session may refresh the ChatGPT login and rotate its refresh token. When the isolated auth.json
changed and the real one is still the copy prepare took, the refreshed file is copied back, so the
owner's own Codex login is not left holding a revoked token.
"""
import hashlib
import json
import os
import shutil
import sys
import tomllib
from pathlib import Path

REAL = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
USER_SKILLS = Path.home() / '.agents/skills'
KEEP = ('model', 'model_reasoning_effort', 'model_verbosity', 'service_tier', 'model_provider')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def win(path):
    # Codex keys project trust by the lower-cased Windows path.
    return str(Path(path).resolve()).lower()


def prepare(clone, home):
    home.mkdir(parents=True, exist_ok=True)
    # Codex fetches curated plugins on start; drop any it left so each session starts without them.
    shutil.rmtree(home / 'plugins', ignore_errors=True)
    real_cfg = tomllib.loads((REAL / 'config.toml').read_text(encoding='utf-8'))
    lines = [f'{k} = {json.dumps(real_cfg[k])}' for k in KEEP if k in real_cfg]
    lines += ['', '[features]', 'hooks = true', 'memories = false', 'plugins = false', 'apps = false', '',
              f'[projects.{json.dumps(win(clone))}]', 'trust_level = "trusted"', '']
    for skill in sorted(USER_SKILLS.rglob('SKILL.md')):
        lines += ['[[skills.config]]', f'path = {json.dumps(skill.as_posix())}', 'enabled = false', '']
    (home / 'config.toml').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    shutil.copy2(REAL / 'auth.json', home / 'auth.json')
    (home / '.auth.orig.sha256').write_text(sha(REAL / 'auth.json'))
    check(home)
    print(home)


def sync(home):
    mine, orig, real = sha(home / 'auth.json'), (home / '.auth.orig.sha256').read_text().strip(), sha(REAL / 'auth.json')
    if mine != orig and real == orig:
        shutil.copy2(home / 'auth.json', REAL / 'auth.json')
        print('codex-home: refreshed login copied back to', REAL)


def check(home):
    names = {p.name for p in home.iterdir()}
    assert not names & {'AGENTS.md', 'AGENTS.override.md', 'plugins', 'rules', 'memories'}, names
    # Codex unpacks its built-in system skills into <home>/skills/.system; nothing else may be there.
    assert {p.name for p in (home / 'skills').iterdir()} <= {'.system'} if (home / 'skills').exists() else True
    cfg = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8'))
    assert not set(cfg) - set(KEEP) - {'features', 'projects', 'skills'}, cfg.keys()
    off = {c['path'] for c in cfg.get('skills', {}).get('config', []) if c['enabled'] is False}
    assert off == {p.as_posix() for p in USER_SKILLS.rglob('SKILL.md')}, 'user skills not all disabled'
    assert cfg['features'] == {'hooks': True, 'memories': False, 'plugins': False, 'apps': False}, cfg['features']
    assert (home / 'auth.json').exists()


if __name__ == '__main__':
    cmd, *args = sys.argv[1:]
    {'prepare': lambda: prepare(Path(args[0]), Path(args[1])), 'sync': lambda: sync(Path(args[0])),
     'check': lambda: check(Path(args[0]))}[cmd]()
