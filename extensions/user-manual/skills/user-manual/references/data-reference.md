# Data reference and ER diagrams

In the private Technical Reference, document every discovered entity/table and every column/property:
name, purpose, physical/logical type, length or precision, nullability, default, generated behavior,
primary/foreign keys, unique/index membership, constraints, relationships, retention, enumeration,
and sensitive-data classification. List every enumeration name, stored representation, allowed value,
plain meaning, and deprecated value.

Derive facts from migrations, ORM metadata, schema files, contracts, or explicitly authorized
development-schema inspection. Never query or reproduce production rows.

Generate one system ER overview showing module ownership and cross-module relationships. Generate
smaller module ER diagrams with readable entity detail. If the full column set cannot fit, keep the
diagram structural and link each entity to its complete Markdown data dictionary.
