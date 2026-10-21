"""Sanduq Progress: a rebuildable projection of delivery progress. Stdlib only."""
SCHEMA_V2 = 'sanduq.progress.v2'
SCHEMA_V3 = 'sanduq.progress.v3'
SCHEMA = SCHEMA_V3  # the projection; v2 names the internal base document it is built on, which no command prints
VERSION = '1.2.0'
