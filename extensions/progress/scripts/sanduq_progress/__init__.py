"""Sanduq Progress: a rebuildable projection of delivery progress. Stdlib only."""
SCHEMA_V2 = 'sanduq.progress.v2'
SCHEMA_V3 = 'sanduq.progress.v3'
SCHEMA = SCHEMA_V3  # the default projection; v2 is the compatibility document (`status --json --schema v2`)
VERSION = '1.2.0'
