"""Budgeted, read-only retrieval over format-2 project memory.

Ranking order: exact ids and declared selectors, then inferred hints (routes, error codes and code paths
taken from entry text and provenance evidence), then one hop over relations, then lexical text matches.
Results are whole entries packed into a token budget with a continuation cursor. Inferred hints only rank
and recall entries; they never exclude one. An empty result is not evidence that nothing is affected.
"""

from __future__ import annotations

import base64
import json
import math
import re
from collections import Counter
from pathlib import Path

from git_state import ArchiveError
import memory_store as ms

METHODS = "GET|POST|PUT|PATCH|DELETE|HEAD"
# A route is a path after an HTTP method, or a backticked absolute path.
ROUTE_IN_TEXT = re.compile(rf"(?:\b({METHODS})\s+`?|`)(/[A-Za-z0-9_{{][A-Za-z0-9_./{{}}:*-]*)")
CODE_IN_TEXT = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
FILE_IN_TEXT = re.compile(r"`((?:src|tests|e2e|scripts|app|lib|packages)/[^`\s]+)`")
WORD = re.compile(r"[a-z0-9][a-z0-9_-]+")
SCORES = {"id": 100, "declared": 60, "route": 30, "route-prefix": 10, "error_code": 25, "path": 30,
          "path-dir": 15, "path-slice": 5, "relation": 0.4, "text": 6}
NOTE = ("No entry matched. That does not prove the change has no impact: widen the search (catalogs, --text) "
        "and inspect the code.")


def normalize_route(value: str) -> tuple[str | None, str]:
    value = value.strip().strip("`")
    method, _, path = value.partition(" ") if re.match(rf"^({METHODS})\s", value, re.I) else ("", "", value)
    path = path.strip().split("?", 1)[0].rstrip("/.,;:") or "/"
    path = re.sub(r"\{[^}/]*\}|:[A-Za-z_]\w*", "{}", path)
    return (method.upper() or None), path.lower()


def slice_dir(path: str) -> str | None:
    parts = path.split("/")
    if parts[0] in ("src", "tests") and len(parts) > 4:
        return "/".join(parts[:4])
    return None


class Index:
    """Hints derived from the current store; rebuilt per invocation, never committed."""

    def __init__(self, store: ms.Store):
        self.store = store
        self.routes: dict[str, set[tuple[str | None, str]]] = {}
        self.codes: dict[str, set[str]] = {}
        self.files: dict[str, set[str]] = {}
        self.incoming: dict[str, set[str]] = {}
        self.words: dict[str, Counter] = {}
        self.df: Counter = Counter()
        for eid, entry in store.entries.items():
            body = entry["title"] + "\n" + entry["text"]
            self.routes[eid] = {normalize_route(f"{m} {p}" if m else p) for m, p in ROUTE_IN_TEXT.findall(body)}
            self.codes[eid] = set(CODE_IN_TEXT.findall(body))
            evidence = {e["path"] for e in store.provenance.get(eid, {}).get("evidence", [])}
            self.files[eid] = evidence | set(FILE_IN_TEXT.findall(body))
            for ref in entry.get("relations", []):
                self.incoming.setdefault(ref, set()).add(eid)
            words = Counter(WORD.findall(body.lower()))
            words.update({w: 2 for w in WORD.findall(entry["title"].lower())})  # title words count triple
            self.words[eid] = words
            self.df.update(words.keys())
        self.avg_len = sum(sum(c.values()) for c in self.words.values()) / max(1, len(self.words))


def _declared(entry: dict, kind: str) -> list[str]:
    return [s["value"] for s in entry.get("selectors", []) if s["kind"] == kind]


def _bm25(index: Index, eid: str, terms: list[str]) -> float:
    counts, total, n = index.words[eid], sum(index.words[eid].values()), len(index.words)
    score = 0.0
    for term in terms:
        tf = counts.get(term, 0)
        if tf:
            idf = math.log(1 + (n - index.df[term] + 0.5) / (index.df[term] + 0.5))
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * total / index.avg_len))
    return score


def rank(store: ms.Store, *, ids=(), routes=(), paths=(), error_codes=(), domains=(), text: str = "") -> list[dict]:
    index = Index(store)
    unknown = [d for d in domains if d not in store.domains]
    if unknown:
        raise ArchiveError(f"Unknown domain id(s) {unknown}; see specs/memory/taxonomy.json.")
    candidates = [eid for eid, e in store.entries.items() if not domains or e["domain"] in domains]
    hits: dict[str, dict] = {}

    def add(eid: str, by: str, value: str, confidence: str, score: float) -> None:
        hit = hits.setdefault(eid, {"score": 0.0, "reasons": []})
        hit["score"] += score
        hit["reasons"].append({"by": by, "value": value, "confidence": confidence})

    for eid in ids:
        if eid not in store.entries:
            raise ArchiveError(f"Unknown memory id {eid}." + (" It was retired." if eid in store.retired else ""))
        add(eid, "id", eid, "declared", SCORES["id"])
    for raw in routes:
        method, path = normalize_route(raw)
        for eid in candidates:
            entry = store.entries[eid]
            if any(normalize_route(v)[1] == path and normalize_route(v)[0] in (None, method) for v in _declared(entry, "route")):
                add(eid, "route", raw, "declared", SCORES["declared"])
                continue
            exact = [r for r in index.routes[eid] if r[1] == path and (method is None or r[0] in (None, method))]
            if exact:
                add(eid, "route", raw, "inferred", SCORES["route"])
            elif any(r[1].startswith(path + "/") or path.startswith(r[1] + "/") for r in index.routes[eid] if r[1].count("/") > 3):
                add(eid, "route-prefix", raw, "inferred", SCORES["route-prefix"])
    for code in error_codes:
        for eid in candidates:
            if code in _declared(store.entries[eid], "error_code") or code in _declared(store.entries[eid], "config_key"):
                add(eid, "error_code", code, "declared", SCORES["declared"])
            elif code in index.codes[eid]:
                add(eid, "error_code", code, "inferred", SCORES["error_code"])
    for raw in paths:
        query = raw.strip().strip("/").replace("\\", "/")
        query_slice = slice_dir(query) or query
        for eid in candidates:
            if any(query == v.strip("/") or v.strip("/").startswith(query + "/") for v in _declared(store.entries[eid], "path")):
                add(eid, "path", raw, "declared", SCORES["declared"])
                continue
            files = index.files[eid]
            if any(f == query or f.startswith(query + "/") for f in files):
                add(eid, "path", raw, "inferred", SCORES["path"])
            elif any(f.rsplit("/", 1)[0] == query.rsplit("/", 1)[0] for f in files if "/" in query):
                add(eid, "path-dir", raw, "inferred", SCORES["path-dir"])
            elif any(slice_dir(f) == query_slice for f in files if slice_dir(f)):
                add(eid, "path-slice", raw, "inferred", SCORES["path-slice"])
    terms = [w for w in dict.fromkeys(WORD.findall(text.lower()))]
    structured = bool(ids or routes or paths or error_codes)
    if terms:
        # Text adds new matches when structured criteria are absent or scarce; otherwise it only re-ranks them.
        widen = not structured or len(hits) < 3
        pool = candidates if widen else [eid for eid in candidates if eid in hits]
        scored = sorted(((eid, _bm25(index, eid, terms)) for eid in pool), key=lambda x: -x[1])
        top = scored[0][1] if scored else 0
        for eid, score in scored:
            if score > 0 and (not widen or score >= top * 0.2):
                add(eid, "text", text, "inferred", SCORES["text"] * score / max(top, 1e-9))
    if not structured and not terms and domains:
        for eid in candidates:
            add(eid, "domain", ",".join(domains), "declared", 1)
    direct = sorted(hits, key=lambda e: -hits[e]["score"])[:25]
    for eid in direct:
        neighbours = set(store.entries[eid].get("relations", [])) | index.incoming.get(eid, set())
        for other in neighbours:
            if other in store.entries and other not in hits and other in candidates:
                hits.setdefault(other, {"score": 0.0, "reasons": [], "via": True})
            if other in hits and hits[other].get("via"):
                hits[other]["score"] = max(hits[other]["score"], hits[eid]["score"] * SCORES["relation"])
                if not any(r["by"] == "relation" and r["value"] == eid for r in hits[other]["reasons"]):
                    hits[other]["reasons"].append({"by": "relation", "value": eid, "confidence": "declared"})
    ordered = sorted(hits, key=lambda e: (-round(hits[e]["score"], 6), e))
    return [{"id": eid, "score": round(hits[eid]["score"], 2), "reasons": hits[eid]["reasons"]} for eid in ordered]


def _cursor(root: str, offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"root": root, "offset": offset}).encode()).decode().rstrip("=")


def _offset(cursor: str | None, root: str) -> int:
    if not cursor:
        return 0
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, TypeError) as error:
        raise ArchiveError("Invalid cursor.") from error
    if data.get("root") != root:
        raise ArchiveError("Memory changed since this cursor was issued; run the query again without --cursor.")
    return int(data["offset"])


def render_entry(store: ms.Store, eid: str) -> str:
    entry = store.entries[eid]
    head = f"## {eid} · {entry['kind']} · {store.label(entry['domain'])}\n\n**{entry['title']}**\n\n"
    return head + entry["text"] + "\n"


def evidence_status(store: ms.Store, eid: str, repo_root: Path) -> dict:
    paths = {e["path"] for e in store.provenance.get(eid, {}).get("evidence", [])}
    present = sum(1 for p in paths if (repo_root / p).exists())
    return {"present": present, "missing": len(paths) - present}


def query(store: ms.Store, repo_root: Path, *, budget: int = 8000, cursor: str | None = None, **criteria) -> dict:
    root = ms.memory_root(repo_root)
    ranked = rank(store, **criteria)
    offset = _offset(cursor, root)
    page, used = [], 0
    for item in ranked[offset:]:
        block = render_entry(store, item["id"])
        cost = ms.tokens(block)
        if page and used + cost > budget:
            break
        page.append({**item, "domain": store.entries[item["id"]]["domain"], "kind": store.entries[item["id"]]["kind"],
                     "title": store.entries[item["id"]]["title"],
                     "evidence": evidence_status(store, item["id"], repo_root), "markdown": block})
        used += cost
    end = offset + len(page)
    returned = {p["id"] for p in page}
    unreturned = sorted({r for p in page for r in store.entries[p["id"]].get("relations", [])} - returned)
    result = {"memory_root": root, "criteria": {k: v for k, v in criteria.items() if v},
              "matched": len(ranked), "offset": offset, "returned": len(page), "remaining": len(ranked) - end,
              "truncated": end < len(ranked), "cursor": _cursor(root, end) if end < len(ranked) else None,
              "tokens": used, "budget": budget, "token_method": "chars/4",
              "unreturned_relations": unreturned, "entries": page}
    if not ranked:
        result["note"] = NOTE
    return result


def to_markdown(result: dict) -> str:
    lines = [f"<!-- memory root {result['memory_root'][:12]} · matched {result['matched']} · returned {result['returned']} "
             f"from offset {result['offset']} · {result['tokens']}/{result['budget']} tokens ({result['token_method']}) -->", ""]
    if result.get("note"):
        lines += [result["note"], ""]
    for item in result["entries"]:
        reasons = "; ".join(f"{r['by']}={r['value']} ({r['confidence']})" for r in item["reasons"])
        ev = item["evidence"]
        lines += [item["markdown"].rstrip(), "",
                  f"_matched by {reasons}; evidence present {ev['present']}, missing {ev['missing']}_", ""]
    if result["truncated"]:
        lines.append(f"{result['remaining']} more match(es). Continue with `--cursor {result['cursor']}`.")
    if result["unreturned_relations"]:
        lines.append("Related entries not returned: " + ", ".join(result["unreturned_relations"]) + ".")
    return "\n".join(lines).rstrip() + "\n"
