"""Run the trace through every approach and count model-visible tokens."""
from . import approaches, counting, traces

APPROACHES = ("NEW", "MD-EDIT", "MD-EDIT-LEAN", "LEGACY", "MD-RENDER")


def _tally(messages, encoders):
    """Tokens per encoding plus bytes for a list of (tag, text) messages."""
    out = {name: sum(counting.count(enc, text) for _, text in messages) for name, enc in encoders.items()}
    out["bytes"] = sum(len(text.encode("utf-8")) for _, text in messages)
    out["skill"] = {name: sum(counting.count(enc, text) for tag, text in messages if tag.startswith(("skill", "protocol"))
                              for enc in [encoders[name]]) for name in encoders}
    return out


def compute():
    """Return the full result structure. Requires tiktoken."""
    encoders = counting.load()
    declared = encoders[counting.DECLARED]
    trace = traces.build()
    measure = lambda text: counting.count(declared, text)  # noqa: E731
    new_setup, new_events, render_events = approaches.real_cli_run(trace)
    raw = {
        "NEW": (new_setup, new_events),
        "MD-EDIT": (approaches.md_setup(), approaches.md_events(trace, measure)),
        "MD-EDIT-LEAN": (approaches.md_setup(), approaches.md_events(trace, measure, reads_required=False)),
        "MD-RENDER": ([], render_events),
    }
    if approaches.legacy_available():
        raw["LEGACY"] = approaches.legacy_setup_and_events(trace)
    results = {}
    for name in APPROACHES:
        if name not in raw:
            continue
        setup, events = raw[name]
        results[name] = {
            "setup": _tally(setup, encoders),
            "events": [dict(kind=e["kind"], **_tally(e["messages"], encoders), messages=len(e["messages"]) // 2) for e in events],
            "raw_setup": setup,
            "raw_events": events,
        }
    return {"trace": trace, "results": results, "encodings": list(encoders), "tiktoken": counting.tiktoken_version()}


def per_class(data, approach, encoding):
    """Sum tokens per class for one approach."""
    sums = {kind: 0 for kind in traces.CLASSES}
    for event in data["results"][approach]["events"]:
        sums[event["kind"]] += event[encoding]
    return sums


def prefix_totals(data, approach, encoding):
    total, out = 0, []
    for event in data["results"][approach]["events"]:
        total += event[encoding]
        out.append(total)
    return out
