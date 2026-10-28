# T07 issue text

Variant A (below, "Body") is the paired-arm body, filed once per run so no run reuses another's issue, branch or feature folder. Only the
title suffix differs. `tools/file-issues.sh` files them all in one go and writes `logs/issues.tsv`.

Keep the title under 40 characters before the suffix: the feature folder is
`specs/<issue>-<title slug cut at 56 characters>`, and `tools/policy.py` derives the fixture
override key from it.

## Titles

| Run | Title |
| --- | --- |
| a1, a2 (in-session) | `Add initials and squeeze commands (T07 a1)`, `(T07 a2)` |
| b1, b2 (native) | `Add initials and squeeze commands (T07 b1)`, `(T07 b2)` |
| c1, c2 (external) | `Add initials and squeeze commands (T07 c1)`, `(T07 c2)` |
| fx-claude (Claude Code fixture) | `Add initials and squeeze commands (T07 fx-claude)` |
| fx-codex (Codex fixture) | `Add initials and squeeze commands (T07 fx-codex)` |

## Body

````markdown
Add two independent commands to textkit: `initials` and `squeeze`. Neither uses the other, so they
can be built and tested separately.

- Library: `textkit.core.initials(text) -> str`. Words are separated by whitespace. For each word,
  take its first letter or digit (skip any leading punctuation in that word); a word with no letter
  or digit contributes nothing. Return those characters upper-cased and joined with no separator.
  `initials("portable network graphics") == "PNG"`, `initials("  (big) 'apple' pie ") == "BAP"`,
  `initials("route 66 ... now") == "R6N"`, and empty or whitespace-only text returns `""`.
- Library: `textkit.core.squeeze(text) -> str`. Replace every run of whitespace (spaces, tabs,
  newlines) with a single space and remove leading and trailing whitespace.
  `squeeze("  a \t b\n\nc  ") == "a b c"`; empty or whitespace-only text returns `""`.
- CLI: `python -m textkit initials TEXT` and `python -m textkit squeeze TEXT` print the result and
  exit 0. `slugify` keeps working unchanged.
- Add unit tests for both functions and both commands, and a README usage line for each command.

Out of scope: stdin or file input, new flags, changing `slugify`.
````

## Body, variant B (fixture runs only, from the Workflow 2.0.2 batch)

The 2.0.1 Codex fixture (#93) was planned as one task (T001), so it could not show one task external
and one native. Variant B is variant A plus one paragraph asking for two separately testable tasks;
`tools/file-issues.sh` files it for `fx-claude` and `fx-codex` only, so the paired arms (a, b, c) keep
the same body as each other. Issues already filed (#72 to #80, #86 to #93) used variant A and are not
changed. `tools/validate.py` still marks a fixture INVALID when the plan ends with fewer than one
external and one native task attempt.

````markdown fixture
Add two independent commands to textkit: `initials` and `squeeze`. Neither uses the other, so they
can be built and tested separately.

- Library: `textkit.core.initials(text) -> str`. Words are separated by whitespace. For each word,
  take its first letter or digit (skip any leading punctuation in that word); a word with no letter
  or digit contributes nothing. Return those characters upper-cased and joined with no separator.
  `initials("portable network graphics") == "PNG"`, `initials("  (big) 'apple' pie ") == "BAP"`,
  `initials("route 66 ... now") == "R6N"`, and empty or whitespace-only text returns `""`.
- Library: `textkit.core.squeeze(text) -> str`. Replace every run of whitespace (spaces, tabs,
  newlines) with a single space and remove leading and trailing whitespace.
  `squeeze("  a \t b\n\nc  ") == "a b c"`; empty or whitespace-only text returns `""`.
- CLI: `python -m textkit initials TEXT` and `python -m textkit squeeze TEXT` print the result and
  exit 0. `slugify` keeps working unchanged.
- Add unit tests for both functions and both commands, and a README usage line for each command.

Plan this as at least two separately testable tasks: one task delivers `initials` (function, command,
tests and README line) and another delivers `squeeze` (function, command, tests and README line), so
either can be built and reviewed without the other.

Out of scope: stdin or file input, new flags, changing `slugify`.
````
