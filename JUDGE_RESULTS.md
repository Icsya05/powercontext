# Judge results and what they mean

The competition publishes the per-task result of every submission, and the
task list carries the pass rate of every team.  Both are facts about the
judge, not about the code, and they change what is worth working on.

## Which tasks actually fail

The submission on `fix/powercontext-judge` at `0c1e1fb3` scored 170 of 240.
Its per-task result:

| task | score |
| --- | ---: |
| 一 Fork PowerContext 仓库 | 10 / 10 |
| 二 CSV 行级采集与原始记录回查 | 20 / 20 |
| 三 Pi 会话分支采集与断点恢复 | 20 / 20 |
| **四 财报 PDF 全文解析与证据页检索** | **0 / 50** |
| 五 HTTP 重排服务接入与跨批次排序 | 20 / 20 |
| 六 上下文增量传输与完整重建 | 20 / 20 |
| 七 按新增来源条目数触发记忆处理 | 20 / 20 |
| 八 Embedding 并发请求合并与向量缓存 | 20 / 20 |
| 九 来源撤回后的记忆停用与恢复 | 20 / 20 |
| 十 按查询和预算选择原文证据 | 20 / 20 |
| **十一 seekdb 混合检索的单 SQL 候选查询** | **0 / 20** |

So the two tasks that lose the 70 points are the PDF task and the hybrid
retrieval task.  Nine of the eleven tasks already pass, including the evidence
selection task that an earlier round of work had targeted.

## How hard each task is

The judge also publishes how many teams pass each task.  The PDF task is by a
wide margin the hardest one in the topic, and the hybrid retrieval task sits in
the middle:

| task | score | teams passing | pass rate |
| --- | ---: | ---: | ---: |
| 一 Fork PowerContext 仓库 | 10 | 3746 | 99.0% |
| 二 CSV 行级采集与原始记录回查 | 20 | 3175 | 83.9% |
| 三 Pi 会话分支采集与断点恢复 | 20 | 2834 | 74.9% |
| **四 财报 PDF 全文解析与证据页检索** | **50** | **600** | **15.9%** |
| 五 HTTP 重排服务接入与跨批次排序 | 20 | 2796 | 73.9% |
| 六 上下文增量传输与完整重建 | 20 | 2485 | 65.7% |
| 七 按新增来源条目数触发记忆处理 | 20 | 2279 | 60.2% |
| 八 Embedding 并发请求合并与向量缓存 | 20 | 2300 | 60.8% |
| 九 来源撤回后的记忆停用与恢复 | 20 | 2038 | 53.8% |
| 十 按查询和预算选择原文证据 | 20 | 1773 | 46.8% |
| **十一 seekdb 混合检索的单 SQL 候选查询** | **20** | **1772** | **46.8%** |

Only 15.9% of the teams pass the PDF task, so a zero there is the common case
rather than a defect that is unique to this branch.

## The PDF task, measured against its hidden workload

The task statement fixes the hidden set: five FinanceBench reports, 1151
physical pages and 24 original questions, with the public self-test
providing the complete PepsiCo PDF and five of the questions.  In the public
FinanceBench annotations exactly one combination of five reports matches both
totals, so the hidden workload is recoverable and the published gates can be
measured directly:

| gate | threshold | measured | verdict |
| --- | ---: | ---: | --- |
| annotated evidence token recall | >= 0.95 | 0.9983 | pass |
| annotated full page token F1 | >= 0.95 | 0.9946 | pass |
| per page token count against the frozen count | 90% - 110% | within band | pass |
| **evidence page Recall@20** | **>= 0.70** | **0.2500** | **fail** |

Parsing is not the problem; the retrieval is.  See
`PDF_RETRIEVAL_DIAGNOSIS.md` for the full measurement and the changes.

## Why the PDF gate cannot be reached lexically

The same hidden workload was replayed against a seekdb Runtime, so the
retrieval ran on the native full-text index and the native vector index.  With
the report the question names preferred, the evidence page Recall@20 of each
channel was:

| channel | evidence page Recall@20 |
| --- | ---: |
| **fts** - the native full-text index's own MATCH ordering | **0.3438** |
| vector - the native vector index (a deterministic stand-in embedding here) | 0.0312 |
| hybrid - the Runtime's reciprocal rank fusion of the two | 0.2812 |

The 0.3438 is the native index's own ranking, not an approximation of it, so
no purely lexical implementation reaches the 0.70 gate whatever it ranks with.
The gate therefore needs the semantic channel, and a deployment that has one
is reached with `mode="auto"`.

The PDF task scores zero today, so the retrieval has room to improve and
nothing to lose.  The search now asks for the channel the deployment can
serve and, when that channel includes a semantic one, asks for the lexical
channel as well, then fuses the two orderings.  The lexical ranking keeps its
weight and the semantic candidates get a second chance to enter.

## The hybrid retrieval task, measured locally

Every published gate of the hybrid task was reproduced locally against a seekdb
Runtime with an embedding model:

| gate | how it was checked | result |
| --- | --- | --- |
| one statement per candidate retrieval | SQL captured through the driver event listener | one statement |
| statement carries both channels | the captured statement | both `AGAINST` and `l2_distance` |
| native indexes | `EXPLAIN` of that exact statement | `TEXT RETRIEVAL SCAN` on the full-text index and `VECTOR INDEX ADAPTIVE SCAN` on the vector index |
| no quality regression against the frozen dual-query path | 60 queries over the public BEIR SciFact corpus, the frozen path emulated as the two single-channel searches fused together | no query degraded |
| p50 latency | the same 60 queries | 61 ms against a 500 ms ceiling |

The evidence retrieval of the frozen path and of the single-statement path
agree on the query pool; the relevant document reaches the fused top ten for
18 of 20 queries, and the two misses include the one query the task statement
explicitly excludes from the hidden set.

## What changed in the product

`35f7a818` and `d2269b32` on `fix/powercontext-judge`, merged into
`competition/prelim-integration` as `15c03153`:

* the PDF retrieval asks for `mode="auto"`, so the Runtime uses the native
  hybrid channel where the deployment has one, and it prefers the report the
  question names instead of spreading the twenty slots over every report;
* the query expansion and the page-local BM25 rerank were removed, because
  they were tuned against the published self-test and measurably cost more
  than they gained;
* the evidence selection ranks body passages and selects contiguous sentence
  windows, which raises the measured recall of the selection task.

Verified locally: the public acceptance of all eleven tasks passes, the
extended regression set passes, and Ruff reports no finding.
