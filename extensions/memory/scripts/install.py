"""Initialize Sanduq Memory without replacing other extensions or project policy."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import argparse

from git_state import ArchiveError, Repository, atomic_write, write_json

COMMANDS = {
    "init": "Configure project memory, verification checks and lifecycle integrations",
    "prepare": "Queue implemented work for archival after merge",
    "run": "Archive selected verified feature specifications",
    "session": "Process approved pending archives in this local session",
    "enable": "Review and enable automatic archival policy",
    "impact": "Consult current product knowledge for specification impact",
    "status": "Inspect pending archival and recovery state",
}
SESSION = """\n<!-- SANDUQ MEMORY SESSION START -->
At the start of each local agent session, run
`python .specify/extensions/memory/scripts/archive.py pending` from the repository root.
If enabled pending work or an interrupted run exists, follow
`.specify/extensions/memory/commands/session.md` before starting a new specification.
Automatic archival runs only after local merge into the configured target branch under the approved policy.
Before a new specification, branch or broad staging/commit workflow, run
`python .specify/extensions/memory/scripts/archive.py pending --gate`.
A nonzero exit stops that workflow until archive recovery, a writer or number guards are resolved.
For specification creation or impact analysis, follow
`.specify/extensions/memory/commands/impact.md` to read relevant central-memory entries.
Do not load the central product-memory document into ordinary implementation tasks.
<!-- SANDUQ MEMORY SESSION END -->
"""


def hook(command: str, description: str) -> str:
    return ("  - extension: memory\n    command: speckit.memory." + command
            + "\n    enabled: true\n    optional: false\n    priority: 5\n    description: "
            + description + "\n    condition: null\n")


def add_hook(text: str, event: str, command: str, description: str, *, first: bool) -> str:
    event_match = re.search(r"^  " + event + r":\s*$", text, re.M)
    block = hook(command, description)
    if not event_match:
        return text.rstrip() + "\n  " + event + ":\n" + block
    start = event_match.end() + 1
    next_event = re.search(r"^  [a-z_]+:\s*$", text[start:], re.M)
    end = start + next_event.start() if next_event else len(text)
    section = text[start:end]
    own = re.compile(r"^  - extension: memory\n(?:(?!^  - |^  [a-z_]+:).*(?:\n|$))*", re.M)
    section = own.sub(lambda match: "" if "command: speckit.memory." + command + "\n" in match.group() else match.group(), section)
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
    if repo.path(".specify/extensions/engage-archive").exists():
        raise ArchiveError("The Engage extension remains installed. Do not migrate this project until the owner confirms cutover.")
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
    for path, data in guards.items():
        atomic_write(repo.path(path), data)
    write_json(policy_path, policy)
    for name, description in COMMANDS.items():
        command = extension / "commands" / (name + ".md")
        if not command.is_file():
            raise ArchiveError(f"Missing command: {name}")
        body = command.read_text(encoding="utf-8").split("---", 2)[2].strip() + "\n"
        skill = "speckit-memory-" + name
        wrapper = ("---\nname: " + skill + "\ndescription: " + description
                   + "\ncompatibility: Spec Kit project with Python 3.11+ and Git\n---\n\n" + body)
        for host in (".agents", ".claude"):
            atomic_write(repo.path(host + "/skills/" + skill + "/SKILL.md"), wrapper.encode())
        agent = "speckit.memory." + name
        atomic_write(repo.path(".github/agents/" + agent + ".agent.md"),
                     ("---\ndescription: " + description + "\n---\n\n<!-- Extension: memory -->\n" + body).encode())
        atomic_write(repo.path(".github/prompts/" + agent + ".prompt.md"), ("---\nagent: " + agent + "\n---\n").encode())
    # Order matters: templates iterate YAML order, not numeric priority.
    text = add_hook(text, "before_specify", "impact", "Consult current product memory", first=True)
    text = add_hook(text, "before_specify", "session", "Process merged pending archives", first=True)
    text = add_hook(text, "before_analyze", "impact", "Consult current product memory", first=True)
    text = add_hook(text, "after_implement", "prepare", "Queue implemented work for archival after merge", first=False)
    atomic_write(config, text.encode())
    registry["extensions"]["memory"] = {
        **registry["extensions"].get("memory", {}),
        "version": "1.0.0", "enabled": True, "priority": 5,
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
    return {"commands": list(COMMANDS), "hosts": ["codex", "claude", "copilot"], "automatic_enabled": Archive(root).pending()["enabled"], "policy": str(policy_path), "guards": list(guards)}


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
