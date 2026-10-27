# Evidence continuation and fitting-cost plan

Binding contract: competition/challenges/context-01-evidence-selection/instruction.md.
User authorizes autonomous optimization until the five-hour quota has 50% remaining; the weekly quota is not the requested stop condition.

## Design

1. Preserve exact centered-window selection while caching fixed JSON/citation/envelope byte overhead. Differential experiments compare the actual old and candidate fitters, including escape and coordinate boundaries. Existing public and focused suites protect compatibility; no new mock call-count or timing-threshold tests.
2. After query-driven selection has finished, consider the immediately following original sentence only when its opening explicitly refers back (for example, "These measurements"). Add it only if the complete rendered proposal fits. Never remove any selected interval. Preserve source, scope, revision, coordinates, and origin order. No online services, scoring labels, sample IDs, or dependency changes.
3. Add a failing public-builder regression for an unselected anaphoric continuation, then implement the smallest bounded extension. Cover no-fit retention, unrelated following text, scope identity, and default-off compatibility.
4. Verify related tests and all official public targets, record independent behavior/latency results and one fresh read-only review. Save a coherent checkpoint; don't imply hidden quality acceptance.

## Why this direction

Whole-sentence-first packing can trade away query coverage. This extension is performed after packing and accepts only supersets of selected source intervals, so it cannot reduce interval coverage or the specified evidence-token recall for the same inputs. It can consume otherwise unused bytes and does not guarantee finding all semantically relevant evidence.

## Ledger

- Base: 5897a335; tested product d458a7f3. Fixed-overhead prototype: 3,382 exact fitter comparisons and 64 public-builder synthetic cases unchanged; seven timing repetitions p50 2.77ms -> 2.06ms, p95 5.82ms -> 4.75ms. Independent reviewer ran 6,084 more comparisons, no introduced finding. Full 316/95 integration in progress.
- Ruling: the fitter is a behavior-preserving performance refactor; use old/new differential verification and existing public behavior tests rather than an unstable timing threshold or internal call-count test. New continuation behavior requires RED -> GREEN.

- Completed: db4e4ae3 fixed-overhead fitting, 448f5d0e continuation selection. Initial continuation regression RED -> GREEN. Intermediate unhashable ArtifactAddress map fixed with the complete six-field identity, with scopes/revisions covered.
- Final review: no introduced correctness findings; 250 independent builder cases retain every selected interval. Ruling: limited English anaphor recognition, abbreviation boundaries, and clipped-window extension opportunities remain heuristic limits; they do not remove baseline intervals. Cost: some eligible evidence can still be missed.
- Verification: 320 passed / 13 skipped plus all95 public tests, including CPUQuota100%/MemoryMax2GiB. Peak1322369024bytes, exit0. Canonical source verification428files. Hidden quality and platform submission remain unverified.
