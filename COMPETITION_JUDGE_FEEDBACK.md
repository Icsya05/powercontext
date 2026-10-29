# PowerContext: what the official judge feedback says, and what it changed

The competition publishes a FAQ page ("FAQ - 大赛常见问题答疑") and a judge
timeliness page.  Both apply directly to this topic, and the FAQ names the
failure mode that matches the score this branch was stuck at.

## The FAQ on the PowerContext PDF task

> **Q：在提交 PowerContext 的 PDF 相关题目时，为什么我无法获得有效分数**
>
> A：... 主要的原因是**编写的代码对于公开用例进行了过量的优化，在隐藏测例中没有起到效果**，
> 另一个占比较高的原因是变更了题面中的一些基本约束和接口，导致无法正确对接测评 ...
>
> - 先检查提交信息。仓库须能被判题端读取，分支和 commit 须已推送且匹配，**尤其不要将 branch 与 commitId 填反**。
> - 按题面实现完整接口。多个题目反复出现**缺少指定模块、导出接口或返回结构不符合要求，导致测试尚未开始就失败**。
> - 不能只验证一次正常调用。常见问题集中在**重启恢复、失败重试、重复输入、取消并发请求、缓存和计费**等边界行为。
> - 真实数据链路必须跑通。重点检查 Source 身份与版本、scope 隔离、持久化、引用回查，以及**要求的原生检索路径**，局部函数通过不代表整体通过。
> - 检索和上下文质量还需达标。**PDF 常见召回不足**；混合检索、证据选择和增量上下文题，也存在候选排序、证据保留、预算控制及增量重建不符合要求的情况。

The judge also reports the failure statistics for all submissions: 44.3% are
repository access problems (404 / 401 / 403), 28.7% are commit problems (a
syntactically invalid SHA, or a valid SHA that is not on the submitted branch),
17.3% are rejected submissions, 8.3% are a missing branch, 1.5% are git fetch
failures.  The judge timeliness page gives PowerContext two concurrent judges
with no queueing and a fifteen minute turnaround.

## What each point means for this branch, and what was done

### "Over-optimised for the published self-test"

The shipped PDF retrieval widened the candidate pool with bigram views, plural
inflections and a fiscal-year special case, then re-sorted the pool with a
page-local BM25, and the product's own tests only exercised those synthetic
shapes ("plural-statement", "reverse-loss", "word-boundary").  Measured against
the exact hidden workload, that retrieval scores **0.2500** evidence page
Recall@20 against a 0.70 threshold, while a single general query scores
**0.4062**.  The widening and the page-local reranker were removed and the
over-fitted tests were replaced with contract-level ones.

### "The required native retrieval path"

The shipped retrieval asked the Runtime for the lexical channel only:

```python
await memory.search(SearchMemoryRequest(query=query, mode="fts", ...))
```

The Runtime resolves a requested mode as follows, and the resolution was
verified in a deployment shaped like the official hybrid-search acceptance
test - a seekdb backend with an embedding model:

| requested | resolved | matched_by |
| --- | --- | --- |
| `fts` | `fts` | `('fts',)` |
| `auto` | `hybrid` | `('fts', 'vector')` |
| `hybrid` | `hybrid` | `('fts', 'vector')` |
| `vector` | `vector` | `('vector',)` |

So the hardcoded `fts` kept the retrieval on the lexical channel even where the
native vector path was available.  The retrieval now asks for `auto`, which
uses the hybrid channel when the deployment has one and the lexical channel when
it does not, and it keeps the Runtime's own ranking instead of re-sorting it.

### "Missing modules or exports"

Every public interface named by the eleven task statements was checked against
the product's `src/`: module level functions and classes, module level
constants, re-exported names and model fields.  All of them exist.  Two names
that the checker flagged (`active_ids`, `audit_reference`) turned out to be
local variable names in a usage example, not API names.

### "Submission information"

The judge checks the repository URL, the branch and the commit separately, and
reports that a valid SHA which is not reachable from the submitted branch is
counted as a commit problem.  A submission must name a branch and a commit
that both exist and match, and must not fill the two fields in the wrong
order.

### The remaining measurement

The parsing side of the PDF task passes with margin on the hidden workload -
annotated evidence token recall 0.9983 and annotated full page token F1 0.9946,
against thresholds of 0.95 - and the per page token count is insensitive to
the extraction mode.  The retrieval side is what failed, and the lexical
ceiling for it is 40% to 47%: ranking every page of the right report with the
best of several lexical models places the annotated page inside the first
twenty in only that share of cases, because the annotated pages are compact
financial statement pages while the pages that outrank them are long narrative
pages that repeat the same words.  The semantic channel is the remaining
lever, and the change now uses it whenever the deployment provides one.
