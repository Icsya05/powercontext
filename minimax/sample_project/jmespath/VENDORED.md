# Vendored business project: jmespath.py

This directory is an unmodified copy of the upstream project, except for the
change this submission performs on it (see `../before/` for the pre-change
snapshot and `../../evidence/` for the diff).

| Field | Value |
| --- | --- |
| Upstream | https://github.com/jmespath/jmespath.py |
| Commit | `2812594e69d43098ef60f81f4efc404c071b0418` |
| Version | 1.1.0 (`setup.py`) |
| License | MIT - the full text is in `LICENSE` |
| Vendored on | 2026-10-28 |

## Why this project

The MiniMax topic asks for a runnable business project with tests that a
development assistant can modify.  `jmespath.py` is a JSON query expression
library: small, pure Python, with a complete pytest suite and a JSON
compliance corpus.  A single feature addition can be expressed as a precise
specification, implemented in one module, and regression-tested against the
whole existing suite.

## What this submission changes here

* `jmespath/functions.py` - adds the `matches()` predicate described in
  `../../specs/jmespath-matches.md`.
* `tests/test_matches.py` - the new acceptance tests for that specification.

Everything else in this directory is upstream code, byte identical.

## How to run its tests

```bash
cd minimax/sample_project/jmespath
python -m pytest tests/ -q
```

Upstream commit metadata:

```
2812594e69d43098ef60f81f4efc404c071b0418
Thu Jan 22 11:29:18 2026 -0500
Merge branch 'release-1.1.0' into develop
```
