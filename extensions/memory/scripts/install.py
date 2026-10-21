"""Initialize Sanduq Memory without replacing other extensions or project policy."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import argparse

from git_state import ArchiveError, Repository, atomic_write, write_json

# Descriptions come from each command file's frontmatter, the same text extension.yml carries.
COMMANDS = ("init", "prepare", "run", "session", "enable", "impact", "status")
# Only hooks and the dispatcher call these; on Claude they leave the slash menu but stay callable.
HOOK_ONLY = ("prepare", "session")
# (event, command, description, first). extension.yml lists one command per event, so impact's
# before_specify binding lives only here. Order matters: templates iterate YAML order, not priority.
# An existing entry with `enabled: false` (Sanduq Workflow's reconcile disables session and prepare) is kept
# byte for byte, so its reconcile journal still matches. When a release changes one of these entries, the
# sequence is: Workflow `reconcile --restore`, then `speckit.memory.init`, then `reconcile --apply`.
HOOKS = (("before_specify", "impact", "Consult current product memory", True),
         ("before_specify", "session", "Process merged pending archives", True),
         ("before_analyze", "impact", "Consult current product memory", True),
         ("after_implement", "prepare", "Queue implemented work for archival after merge", False))
# Where each host reads project hooks, and the text that marks this extension's guard entry in them.
HOOK_FILES = {"claude": ".claude/settings.json", "codex": ".codex/hooks.json"}
GUARD_MARK = "memory/hooks/guard.py"
# Command bodies name commands the Copilot way; skill hosts register them with hyphens.
SKILL_NAMES = "Here `speckit.memory.<command>` is the skill `speckit-memory-<command>`.\n\n"
SESSION = """\n<!-- SANDUQ MEMORY SESSION START -->
At session start run `python .specify/extensions/memory/scripts/archive.py pending`; when it reports pending work or an interrupted run, follow `.specify/extensions/memory/commands/session.md`. In a Sanduq Workflow project (`.specify/workflow.yml` exists), Workflow's claim runs this check and returns the Memory commands to run; do not run it separately.
Before a new specification, branch or broad staging or commit workflow, `archive.py pending --gate` must pass.
For specification or impact analysis, follow `.specify/extensions/memory/commands/impact.md`.
Do not load project memory into ordinary implementation tasks.
<!-- SANDUQ MEMORY SESSION END -->
"""


def frontmatter(text: str) -> list[str]:
    """The lines between a file's opening and closing --- fences, or [] without frontmatter."""
    parts = text.replace("\r\n", "\n").split("---", 2)
    return parts[1].strip("\n").split("\n") if text.startswith("---") and len(parts) == 3 else []


def description(text: str, name: str) -> str:
    for line in frontmatter(text):
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip()
    raise ArchiveError(f"Command {name} has no frontmatter description.")


def spec_kit_keys(path: Path) -> list[str]:
    """Spec Kit's argument-hint and metadata block from an earlier render of this wrapper."""
    if not path.is_file() or path.is_symlink():
        return []
    kept, block = [], False
    for line in frontmatter(path.read_text(encoding="utf-8")):
        if line.startswith(("argument-hint:", "metadata:")):
            kept.append(line)
            block = line.startswith("metadata:")
        elif block and line.startswith((" ", "\t")):
            kept.append(line)
        else:
            block = False
    return kept


def guard_hook_outputs(repo: Repository, extension: Path) -> dict[str, bytes]:
    """Each host's hook file with this extension's guard merged in, replacing only an earlier guard entry."""
    python = "python" if os.name == "nt" else "python3"  # Windows' python3 is often the Store stub.
    template = (extension / "hooks/hooks.json").read_text(encoding="utf-8").replace("{python}", python)
    outputs = {}
    for name in HOOK_FILES.values():
        path = repo.path(name)
        raw = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
        try:
            data = json.loads(raw) if raw.strip() else {}
        except ValueError:
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
            raise ArchiveError(f"{name} is not a JSON object with a hooks object; fix it before enabling guard_hooks.")
        hooks = data.setdefault("hooks", {})
        for event, groups in json.loads(template)["hooks"].items():
            kept = []
            for group in hooks.get(event) if isinstance(hooks.get(event), list) else []:
                inner = group.get("hooks") if isinstance(group, dict) else None
                if isinstance(inner, list):
                    inner = [h for h in inner if not (isinstance(h, dict) and GUARD_MARK in str(h.get("command", "")))]
                    if not inner:
                        continue
                    group = {**group, "hooks": inner}
                kept.append(group)
            hooks[event] = kept + groups
        outputs[name] = (json.dumps(data, indent=2) + "\n").encode()
    return outputs


def hook(command: str, description: str) -> str:
    return ("  - extension: memory\n    command: speckit.memory." + command
            + "\n    enabled: true\n    optional: false\n    priority: 5\n    description: "
            + description + "\n    condition: null\n")


def add_hook(text: str, event: str, command: str, description: str, *, first: bool) -> str:
    """Edits only the `hooks:` mapping; every other top-level key (e.g. `settings:` after it) stays as it is."""
    head = re.search(r"^hooks:[ \t]*\n", text, re.M)
    if not head:
        return add_event_hook(text, event, command, description, first=first)
    rest = re.search(r"^\S", text[head.end():], re.M)
    end = head.end() + rest.start() if rest else len(text)
    return text[:head.end()] + add_event_hook(text[head.end():end], event, command, description, first=first) + text[end:]


def add_event_hook(text: str, event: str, command: str, description: str, *, first: bool) -> str:
    event_match = re.search(r"^  " + event + r":\s*$", text, re.M)
    block = hook(command, description)
    if not event_match:
        return (text if not text or text.endswith("\n") else text + "\n") + "  " + event + ":\n" + block
    start = event_match.end() + 1
    next_event = re.search(r"^  [a-z_]+:\s*$", text[start:], re.M)
    end = start + next_event.start() if next_event else len(text)
    section = text[start:end]
    own = re.compile(r"^  - extension: memory\n(?:(?!^  - |^  [a-z_]+:).*(?:\n|$))*", re.M)
    mine = [m.group() for m in own.finditer(section) if "command: speckit.memory." + command + "\n" in m.group()]
    if mine and all(re.search(r"^    enabled: false[ \t]*$", block, re.M) for block in mine):
        return text  # disabled on purpose (Workflow's reconcile or the owner): keep it exactly as it is
    section = own.sub(lambda match: "" if match.group() in mine else match.group(), section)
    section = block + section if first else section + block
    return text[:start] + section + text[end:]


def prepare_guards(repo: Repository) -> dict:
    patches = json.loads(repo.path(".specify/extensions/memory/scripts/guard-patches.json").read_text())
    outputs = {}
    for path, hunks in patches.items():
        target = repo.path(path)
        if not target.exists():
            continue
        original = target.read_bytes()
        text = original.decode("utf-8-sig").replace("\r\n", "\n")
        for hunk in hunks:
            before, after = hunk["before"], hunk["after"]
            if after in text:
                continue
            if text.count(before) != 1:
                raise ArchiveError(f"Unsupported/local-edited guard context: {path}. Preserve the file and adapt the guard explicitly.")
            text = text.replace(before, after, 1)
        if text == original.decode("utf-8-sig").replace("\r\n", "\n"):
            outputs[path] = original
        else:
            if b"\r\n" in original:
                text = text.replace("\n", "\r\n")
            outputs[path] = text.encode()
    if not any(path.startswith(".specify/scripts/") for path in outputs):
        raise ArchiveError("No supported Spec Kit feature script is installed.")
    return outputs


def install(root: Path, target_branch: str | None = None) -> dict:
    repo = Repository(root)
    extension = repo.path(".specify/extensions/memory")
    for installed in sorted(repo.path(".specify/extensions").iterdir()):
        if installed.name == "memory" or not installed.is_dir():
            continue
        if (installed / "scripts/archive.py").is_file() and (installed / "archive-policy.json").is_file():
            raise ArchiveError("Existing specification archive tooling remains installed. Do not replace it until the owner confirms cutover.")
    guards = prepare_guards(repo)
    policy_path = repo.path(".specify/memory-policy.json")
    if policy_path.exists():
        policy = json.loads(policy_path.read_text(encoding="utf-8-sig"))
        from archive import Archive
        Archive(root)  # Validate an existing project policy before any writes.
        if target_branch and target_branch != policy.get("target_branch"):
            raise ArchiveError("Existing policy is preserved; review and edit target_branch explicitly before re-initializing.")
    else:
        policy = json.loads((extension / "archive-policy.json").read_text())
        if target_branch:
            repo.git("check-ref-format", "--branch", target_branch)
            policy["target_branch"] = target_branch
    for path in policy.get("guard_paths", []):
        if path not in guards:
            raise ArchiveError(f"Previously installed guard is missing: {path}. Restore it before initialization.")
    policy["guard_paths"] = sorted(guards)
    if not isinstance(policy.get("guard_hooks", False), bool):
        raise ArchiveError("guard_hooks in .specify/memory-policy.json must be true or false.")
    hook_files = guard_hook_outputs(repo, extension) if policy.get("guard_hooks") else {}
    config = repo.path(".specify/extensions.yml")
    text = config.read_text(encoding="utf-8").replace("\r\n", "\n") if config.exists() else "installed:\nhooks:\n"
    text = re.sub(r"^installed: \[\]$", "installed:", text, flags=re.M)
    if not re.search(r"^- memory\s*$", text, re.M):
        if "installed:\n" not in text:
            raise ArchiveError("Existing extensions.yml has no supported installed list; preserve it and register manually.")
        text = text.replace("installed:\n", "installed:\n- memory\n", 1)
    if not re.search(r"^hooks:\s*$", text, re.M):
        raise ArchiveError("Existing extensions.yml has no hooks mapping.")
    for name in COMMANDS:
        if not (extension / "commands" / (name + ".md")).is_file():
            raise ArchiveError(f"Missing command: {name}")
    registry_path = repo.path(".specify/extensions/.registry")
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {"schema_version": "1.0", "extensions": {}}
    # Spec Kit --dev can register owned command files as links. Replace only
    # these known wrapper links, never follow a link into another project.
    owned_links = []
    for name in COMMANDS:
        wrappers = [f"{host}/skills/speckit-memory-{name}/SKILL.md" for host in (".agents", ".claude")]
        wrappers += [f".github/{kind}/speckit.memory.{name}.{suffix}.md" for kind, suffix in (("agents", "agent"), ("prompts", "prompt"))]
        for relative in wrappers:
            parent = repo.path(str(Path(relative).parent).replace("\\", "/"))
            target = parent / Path(relative).name
            if target.is_symlink():
                if not target.resolve().is_relative_to(extension.resolve()):
                    raise ArchiveError(f"Owned wrapper points outside this extension: {relative}")
                owned_links.append(target)
            else:
                repo.path(relative)
    for target in owned_links:
        target.unlink()
    manifest = (extension / "extension.yml").read_text(encoding="utf-8")
    version = re.search(r"^\s+version:\s*[\"']?([^\"'\s]+)", manifest, re.M)
    if not version:
        raise ArchiveError("extension.yml has no extension version.")
    sources = {name: (extension / "commands" / (name + ".md")).read_text(encoding="utf-8") for name in COMMANDS}
    summaries = {name: description(sources[name], name) for name in COMMANDS}
    for path, data in guards.items():
        atomic_write(repo.path(path), data)
    write_json(policy_path, policy)
    for path, data in hook_files.items():
        atomic_write(repo.path(path), data)
    for name in COMMANDS:
        summary, body = summaries[name], sources[name].split("---", 2)[2].strip() + "\n"
        skill = "speckit-memory-" + name
        for host in (".agents", ".claude"):
            path = repo.path(host + "/skills/" + skill + "/SKILL.md")
            head = ["name: " + skill, "description: " + summary, "compatibility: Spec Kit project with Python 3.11+ and Git"]
            head += spec_kit_keys(path) + (["user-invocable: false"] if host == ".claude" and name in HOOK_ONLY else [])
            atomic_write(path, ("---\n" + "\n".join(head) + "\n---\n\n" + SKILL_NAMES + body).encode())
        agent = "speckit.memory." + name
        atomic_write(repo.path(".github/agents/" + agent + ".agent.md"),
                     ("---\ndescription: " + summary + "\n---\n\n<!-- Extension: memory -->\n" + body).encode())
        atomic_write(repo.path(".github/prompts/" + agent + ".prompt.md"), ("---\nagent: " + agent + "\n---\n").encode())
    for event, command, note, first in HOOKS:
        text = add_hook(text, event, command, note, first=first)
    atomic_write(config, text.encode())
    registry["extensions"]["memory"] = {
        **registry["extensions"].get("memory", {}),
        "version": version.group(1), "enabled": True, "priority": 5,
        "manifest_hash": "sha256:" + hashlib.sha256((extension / "extension.yml").read_bytes()).hexdigest(),
        "registered_commands": {host: ["speckit.memory." + n for n in COMMANDS] for host in ("codex", "claude", "copilot")},
        "registered_skills": ["speckit-memory-" + n for n in COMMANDS],
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(registry_path, registry)
    for name in ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"):
        path = repo.path(name)
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        if "<!-- SANDUQ MEMORY SESSION START -->" in original:
            updated = re.sub(r"\n?<!-- SANDUQ MEMORY SESSION START -->.*?<!-- SANDUQ MEMORY SESSION END -->\n?",
                             SESSION, original, flags=re.S)
            atomic_write(path, updated.encode())
        else:
            atomic_write(path, (original.rstrip() + "\n" + SESSION).encode())
    from archive import Archive
    return {"commands": list(COMMANDS), "hosts": ["codex", "claude", "copilot"], "automatic_enabled": Archive(root).pending()["enabled"], "policy": str(policy_path), "guards": list(guards),
            "guard_hooks": sorted(hook_files)}


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--root", default=".")
        parser.add_argument("--target-branch")
        args = parser.parse_args()
        print(json.dumps(install(Path(args.root), args.target_branch)))
    except (ArchiveError, OSError, ValueError, KeyError) as error:
        print(json.dumps({"success": False, "error": str(error)}))
        sys.exit(1)
