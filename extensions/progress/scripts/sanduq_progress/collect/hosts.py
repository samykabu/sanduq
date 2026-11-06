"""Host collector: reads the snapshots the hooks and statusline wrote (progress.host.v1)."""
from .. import snapshot


def collect(ctx):
    """Snapshots for this feature, orchestrators first by recency, with children sorted by start."""
    snaps = [s for s in snapshot.read_all(ctx) if s.get('bound_feature') in (None, ctx.feature)]
    return sorted(snaps, key=lambda s: (s.get('last_observed_at') or '', s.get('session_id') or ''), reverse=True)
