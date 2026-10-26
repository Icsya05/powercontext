# Query-directed literal evidence selection

Spec: `competition/challenges/context-01-evidence-selection/instruction.md`.

Use inline execution. User authorized autonomous implementation without design questions, bounded by 20:30 Beijing on 2026-10-26.

## Design and constraints

Add a strict, default-false flag and immutable fragment results to the existing builder. In selection mode, rank literal sentence spans using query terms, corpus rarity and coverage, greedily pack relevant spans with exact full rendering cost, and preserve original scope/citation/character coordinates. Adjacent selected spans may merge using original text. Overlong sentences may contribute a query-centered literal window. No model calls, labels, hardcoded sample answers, dependency changes or official asset edits. Ordinary prepare remains on its existing path.

## Tasks

1. Add behavior tests: late evidence, query changes, scope identity, escaped Unicode byte budget, exact boundary, default compatibility and strict flag. Run them and official tests RED before implementation.
2. Implement request flag, fragment data and bounded builder path. Run new tests plus official evidence tests GREEN.
3. Run prepared-context and incremental regressions, Ruff and type checks; request one independent review; address demonstrated defects with RED/GREEN tests.
4. Commit and push a reviewable checkpoint with measured limits. Public tests do not establish hidden SciFact quality thresholds.

## Ledger

- Previous baseline evidence tests fail because PrepareContextRequest rejects evidence_selection.
- Lifecycle changes are on a separate worktree and do not change the builder interface; integrate only after its review.
- Ruling: lexical offline selection is a reproducible baseline within the fixed dependency set; hidden evidence quality remains unmeasured.

- Final: implementation commit 2a8947de passed 108 related tests and Ruff/ty. Independent review: no Critical/Important; reviewer ran 96 related tests and 48 extra cases. Combined code15edc33b passed95public +247focused/13skip.
- Final: minor (deferred): evidence_selection probe_budget counters follow ordinary selection; align the diagnostic path in a separate follow-up.
- Final: Ruling: generated HTTP flag parity is deferred because the binding task requires Python runtime/builder; remote clients cannot request this mode yet.
- Final: Ruling: hidden SciFact quality is unverified, and malformed candidate identities or latency guarantees outside the supplied workload are not claimed. No labels were read.
