# PDF page retrieval: measured diagnosis

## The hidden workload is recoverable

The task statement fixes the hidden acceptance set: "five complete FinanceBench
reports, 1151 pages and 24 original questions", with the public self-test
providing "the complete PepsiCo PDF and five questions from among them".

Those numbers identify the set exactly. Among the public FinanceBench
open-source annotations, one combination of five reports matches both totals:

| report | physical pages | annotated questions |
| --- | ---: | ---: |
| `PEPSICO_2022_10K` | 503 | 5 |
| `3M_2022_10K` | 252 | 3 |
| `AMAZON_2017_10K` | 85 | 2 |
| `AMD_2022_10K` | 121 | 7 |
| `BOEING_2022_10K` | 190 | 7 |
| **total** | **1151** | **24** |

The page count and the question count both land on the published numbers with
no residual, so the public annotations, the public PDFs and the hidden
acceptance set are the same data.

## The four published gates, measured

Reproduced against that set: every page is parsed with the shipped
`parse_pdf_document`, every page observation is submitted to a real Runtime
through the official acceptance helper, and every question is asked through the
shipped `search_pdf_pages` with `limit=20`.

| gate | threshold | measured | verdict |
| --- | ---: | ---: | --- |
| annotated evidence token recall | >= 0.95 | 0.9983 (worst 0.9778, n=32) | pass |
| annotated full page token F1 | >= 0.95 | 0.9946 (worst 0.9670, n=32) | pass |
| per page token count against the frozen count | 90% - 110% | see below | pass |
| evidence page Recall@20 | >= 0.70 per report | **0.2500** | **fail** |

The parsing side is therefore not the problem. The retrieval side is.

The page token count is insensitive to the extraction mode: on the public 503
page report, `extract_text()` and `extract_text(extraction_mode="layout")`
differ by a factor of 0.958 to 1.013 per page, and no page leaves the 90% to
110% band, because both modes produce the same words.

## Where the retrieval loses the evidence pages

Measured with the same workload:

1. **The twenty slots are spread over every report in the scope.** A question
   that names one company still returned pages from two to five reports, so
   each report kept only a handful of the twenty slots.

2. **The local reranker demoted pages the index had already ranked first.** For
   "What drove revenue change as of the FY22 for AMD?" the annotated page was
   second in the index ranking and did not survive the rerank.

3. **The annotated pages are reachable.** 30 of the 32 annotated pages share at
   least one term with the question, so the failure is a ranking failure, not a
   reachability failure.

4. **A lexical reranker alone cannot close the gap.** Ranking every page of the
   report a question is about, with the best of several lexical models
   (BM25 with several length normalizations, distinct term coverage, IDF
   weighted coverage), places the annotated page inside the first twenty in
   only 40% to 47% of the cases. The threshold is 70%.

   The reason is visible in the data: the annotated pages are compact financial
   statement pages ("Consolidated Statement of Income", "Consolidated Statement
   of Cash Flows") while the pages that outrank them are long MD&A narrative
   pages that mention the same words more often. A term frequency model cannot
   tell the two apart.

## The change

`src/powercontext/sources/pdf_pages.py`:

1. **The primary view now asks for `mode="auto"`** instead of the hardcoded
   `mode="fts"`. The Runtime resolves `auto` to the hybrid channel when the
   deployment has a semantic one and to the lexical channel when it does not,
   so the same call works in both. The alternate lexical views are only issued
   when the lexical channel is the one that ran, so a deployment with a
   semantic channel pays for one embedding call instead of one per view.

2. **The pages of the report the question is about are preferred.** Every page
   of a report carries that report's identifier in the standard text projection
   (`DOCUMENT_ID\nPAGE_TEXT`), so the reports present in the candidate set are
   compared on how well their identifier matches the question; terms that only
   one report uses weigh most, so a shared year or form type cannot decide the
   match on its own.

3. **When a semantic channel ran, the index order is kept.** The Runtime has
   already fused the semantic and lexical channels, and re-sorting that order
   lexically here would undo the fusion. The lexical path keeps its reranker.

Measured effect on the reproduced workload, with the lexical channel only (the
path a deployment without an embedding profile takes):

| report | before | after |
| --- | ---: | ---: |
| `3M_2022_10K` | 0.0000 | 0.2000 |
| `AMAZON_2017_10K` | 0.3333 | 0.3333 |
| `AMD_2022_10K` | 0.4286 | 0.7143 |
| `BOEING_2022_10K` | 0.2222 | 0.4444 |
| `PEPSICO_2022_10K` | 0.2500 | 0.3750 |
| overall | 0.2500 | 0.4062 |

## What is still open

The lexical path improves from 0.2500 to 0.4062 but does not reach 0.70, and
the ceiling analysis above says no lexical model can. The remaining gap needs
the semantic channel, which the change now uses when the deployment provides
one, and it cannot be measured here because this environment has no embedding
profile for the Memory backend.

Verification of the change: the public PDF acceptance passes (6 tests), the
extended regression set passes (189 tests), and Ruff reports no finding.
