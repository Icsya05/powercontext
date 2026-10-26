# Hybrid retrieval portable handoff

## Checkout and task

- Branch: `competition/hybrid-single-sql`.
- Starting commit: `8e9a4bc667f894ba2d7ade133c9b80e01f2b7234` (the parent competition integration baseline).
- Binding challenge: `competition/challenges/retrieval-02-hybrid-search/instruction.md`.
- Plan: `docs/superpowers/plans/2026-10-26-hybrid-single-sql.md`.
- Scope: only Memory persistence candidate search; no runtime application, worker, configuration, official acceptance, workload, or baseline files changed.
- The parent agent owns final fresh review, integration, branch publication and the overall competition handoff. No merge or push was performed by this implementer.

## Implementation

`CompositeMemoryIndex.search()` delegates hybrid requests to an index advertising native hybrid capability. Other compositions and FTS/vector-only requests retain their existing paths.

`OceanBaseMemoryVectorIndex` now provides a single native hybrid candidate statement: independently limited FTS and ANN branches combined with UNION ALL, followed by exact entry-version text lookup and stable channel/distance/identity ordering. Both branches filter scope and requested Memory artifact IDs before their limits. Existing vector completeness and outer backend head checks remain in use. `memory_channel_hits` still maps old projection revisions to the validated current requested reference. Fusion and embedding admission remain unchanged.

The tagged vector branch materializes an uncorrelated scalar JSON array of eligible `(artifact, entry)` objects inside the same statement. JSON_CONTAINS becomes a one-time expression inside the native vector pre-filter. It handles any/all/absent tags and exact identity pairs without retrieving IDs into Python. The FTS branch retains the established correlated tag count filter.

## Root cause and verified fix

The first implementation used the existing correlated tag count predicate in the ANN branch. A new real seekdb regression with six tied vectors, candidate_limit=2 and tags assigned to the last two sorted entry IDs returned FTS=2/vector=0 for `match="any"`. EXPLAIN showed:

```text
TOP-N SORT
  SUBPLAN FILTER (correlated tag count)
    VECTOR INDEX ADAPTIVE SCAN (PRE-FILTER)
```

The ANN operator took its top K before the external subplan filtered those rows, without refilling tagged neighbors. An uncorrelated tuple IN subquery still appeared as an external SUBPLAN FILTER and reproduced the failure. The scalar JSON membership fix instead places this predicate directly on the vector scan:

```text
VECTOR INDEX ADAPTIVE SCAN (PRE-FILTER)
filter([m.scope_id = ...], [m.memory_artifact_id = ...],
       [JSON_CONTAINS(coalesce(:3, JSON_ARRAY()),
        JSON_OBJECT('artifact', m.memory_artifact_id, 'entry', m.entry_id))])
```

Actual real-backend results with that fix: untagged FTS/vector=2/2; any=2/2; all=1/1; absent=0/0. Repeated results equal the initial channel identities/order. Every EXPLAIN contains both TEXT RETRIEVAL SCAN and VECTOR INDEX.

## Verification already executed

- Original public acceptance RED: `1 failed in 60.37s`, assertion `len(native) == 1` observed 0.
- First native UNION implementation public GREEN: `1 passed in 46.81s`, including append/old projections/current refs, revision, deactivate/reactivate, tags, isolation, repeated identity, FTS/vector-only and both native EXPLAIN operators.
- Added tag regression RED: `1 failed in 54.94s`, vector channel 0 instead of 2 for selected any-tags. A diagnostic rerun reproduced the same issue with the plan above.
- Fixed scalar-membership real regression GREEN: `1 passed in 47.91s` (all four tag cases, both native indexes, bounds, scope/artifact isolation, stable ties).
- Affected existing Memory/persistence tests: `93 passed, 15 skipped in 30.42s`.
- Ruff check: `All checks passed!`; Ruff format check: `3 files already formatted`.
- Targeted `ty check --python /home/ocean/.venvs/powercontext-2026/bin/python ...`: `All checks passed!`.
- Full project pytest was attempted, not claimed green: `5 skipped, 110 errors during collection in 99.85s`. The fixed competition environment lacks optional product-suite dependencies `fastapi`, `fastmcp`, `langchain_core`, `markdown_it`, `platformdirs`, `powercontext_langchain`, and `typer`. Do not install or change the fixed competition dependency set just to conceal this limit.

Final reruns on the scalar-membership implementation both passed:

- `make -C competition test-hybrid`: `1 passed in 46.43s`.
- The focused command below, including the new real backend regression: `94 passed, 15 skipped in 65.51s`.
- Final Ruff check/format and targeted ty check all passed before those reruns.

## Reproduce on another computer

Use Linux x86_64, Python 3.12 (verified 3.12.3), the unmodified `competition/requirements.txt`, and exactly `pylibseekdb==1.3.0.post4`. The official `competition/README.md` and Docker recipe define the offline test environment. Source is loaded from this checkout via PYTHONPATH, not an unrelated installed package.

```bash
# From this product checkout; provision competition/.venv using the published
# instructions, or link to an already prepared environment with the fixed deps.
make -C competition test-hybrid

PYTHONPATH=src:competition PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  competition/.venv/bin/python -m pytest -q -p pytest_asyncio.plugin \
  tests/builtin/persistence/test_seekdb_hybrid.py \
  tests/builtin/artifacts/memory \
  tests/builtin/persistence/test_memory.py \
  tests/builtin/persistence/test_sqlite_memory_vector_index.py \
  tests/builtin/persistence/test_oceanbase_profile.py \
  tests/builtin/persistence/test_seekdb_profile.py
```

On the original machine: WSL distribution `Ubuntu-24.04`, Linux user `ocean`, shared venv `/home/ocean/.venvs/powercontext-2026`; this checkout's `competition/.venv` is an ignored symlink to it. No dependency installation was needed. WSL fake-DNS network access is blocked, so use the already installed dependencies. Embedded seekdb uses a local non-loopback eth0 address; official Docker startup alternatively provisions its container-local dummy address. Do not restart/shutdown WSL, change global networking/security, or touch the independent existing seekdb services on 2881/2883. Tests create their own temporary embedded database and close it.

## Remaining work and limits

1. Parent: integrate the verified branch and perform fresh whole-bundle review. Check the composition capability dispatch and tagged scalar pre-filter deliberately.
2. Run the official private full-corpus quality/cost evaluation when available. Its 173-document, 20-query, three-scope qrels/embeddings are unavailable here; no Recall@10/MRR@10/0.95 recall/500ms p50 score or competition points are claimed from the public sample.
3. Large eligible tag sets materialize one native JSON membership array per statement. Correctness is verified on the regression; high-cardinality tag latency/storage behavior is unbenchmarked. The optimizer may choose its native adaptive pre-filter vector scan strategy for small datasets.
4. Full product suite requires the optional development dependencies in a separate development environment; current competition dependencies cannot collect it. The focused affected tests and actual embedded backend tests are the available evidence.
5. Standalone generic vector-only requests deliberately keep their previous SQL; their existing tagged path uses exact native L2 ordering. The new native hybrid provider is wired through the normal OceanBase/seekdb composite, whose FTS partner initializes the shared text index.

No implementation blocker remains after the scalar tag fix. Do not weaken tests or read private judge assets to fill the unavailable quality evidence.
