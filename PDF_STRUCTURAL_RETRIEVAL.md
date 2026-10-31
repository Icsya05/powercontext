# PDF retrieval through report candidates and financial structure

Long FinanceBench questions can lose their evidence pages before ranking: the
Memory lexical coverage floor rejects short statements which contain only a
small part of a long question. Narrative pages then occupy the result slots.

`search_pdf_pages` now discovers PDF report identities from the active entries
of the current scoped Memory. A named report, or the only PDF report in that
scope, supplies a short identifier query to public `Memory.search`. The query
retrieves actual persisted candidates without applying the original long
question as the admission filter. Ambiguous reports and identifiers without
searchable terms retain the existing query search path.

The report candidates are ranked with corpus-derived term weights, body
frequency, short title lines, and financial statement structure. A financial
notes heading must also have sufficient numeric content to receive the table
weight. A continuous physical-page position prior favors main report sections
over later exhibits. Bounded word prefixes provide an inflection channel.
No report names, question strings, answers, or evidence-page lists occur in
the implementation. Original PDF parsing and Source projection are unchanged.

Candidate identities and page positions come from stored PDF Sources. Returned
citations are built from real search hits, deduplicated by Source identity,
and read back through `memory.get`. The global Memory admission floor and
hybrid SQL implementation are unchanged.

## Measured retrieval

The local replay uses the five-report, 1,151-page, 24-question reconstruction
documented in `HANDOFF_CODEX.md`, with 32 question/page evidence pairs. It is a
local reconstruction, not a new official judge score.

| Report | Evidence pairs recalled | Recall@20 |
| --- | ---: | ---: |
| 3M | 4 / 5 | 0.8000 |
| Amazon | 3 / 3 | 1.0000 |
| AMD | 6 / 7 | 0.8571 |
| Boeing | 7 / 9 | 0.7778 |
| PepsiCo | 6 / 8 | 0.7500 |
| Total | 26 / 32 | 0.8125 |

Both the single scope containing all reports and the separate scope per report
produce these results through the real Runtime and citation readback. The
unmodified product at `9c8bc60e283f865076b24652bed2425bfcade426` produced
13/32 (0.4062) and 14/32 (0.4375), respectively. The lowest group is now 0.75
against the published 0.70 threshold.

The original `pdf_shape_lab.py` result of 0.6562 was also reproduced. That script
selects the report from the evaluation annotation and simulates admission;
its `pool=30` is a keyword count. The Runtime replay above is the product-path
check and does not pass annotations to the implementation.

## Validation and limits

- Existing PDF regressions: 8 passed.
- Additional workspace regressions: 3 passed. These cover a long question with
  no initial admitted candidates, document-name overlap without body overlap,
  and a valid document identifier consisting only of punctuation.
- Ruff 0.15.7 lint and formatting, scoped pre-commit checks, a focused ty 0.0.56
  type check, and `git diff --check` pass. The whole-repository type check was
  not run.
- Official full suite on the final source: **95 passed in 379.12 seconds**,
  using the supplied compose configuration (offline, 1 CPU, 2 GiB).

The candidate path reads the active scope once and retrieves all matching
report candidates. Its work grows with scope and report size; it has no
cross-request cache, so it does not reuse stale revisions or another scope's
entries. Larger production collections have not been benchmarked. Prefix
collisions and missed paraphrases remain possible, and six evidence pairs are
still missed in this local replay.

The PDF helper is the only changed product module. Official `competition/`
tests and data, the shared retrieval threshold, and the other task modules are
unchanged. No official submission is made by these checks. Remaining test
attempts are reserved for the user's explicit decision after reviewing history
and this validation.
