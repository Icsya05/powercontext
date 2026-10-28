# 证据目录

这个目录里的每个文件都是**真实运行产生的**，不是手工写的。

| 文件 | 是什么 | 谁生成的 |
| --- | --- | --- |
| `raw/*.jsonl` | 模块自己写的原始事件记录（4446+ 条） | `sddctx/evidence.py`，每次命令运行都追加 |
| `patches/*.patch` | MiniMax 产出的补丁，**按尝试顺序编号** | `sddctx/runner.py: apply_patch` |
| `code-diff.patch` | 交付代码与修改前快照的差异 | `validation/write_artifacts.py` |
| `test-before-*.txt` | 修改前跑验收命令的完整输出 | `validation/reproduce_evidence.py` |
| `test-after-*.txt` | 修改后跑验收命令的完整输出 | 同上 |
| `test-before.txt` | 第一次尝试（实现有 bug）时的目标测试输出 | 手工存档 |
| `attempt-1-test-failure.txt` | 第一次尝试的失败输出，回灌给了模型 | 手工存档 |
| `feedback-attempt2.txt` / `feedback-test-r3.txt` | 回灌给 MiniMax 的失败信息 | 手工存档 |
| `minimax-usage.md` | 每次 MiniMax 调用的 request_id 与 token 用量 | `validation/write_artifacts.py` |
| `seekdb-queries.md` | 模块实际执行过的 seekdb 语句（去重） | 同上 |
| `state-from-powercontext.json` | 从 PowerContext 读回的任务状态快照 | 同上 |
| `context-T-2026-001.json` | 组装出来的开发上下文（结构化） | `sddctx context --out` |
| `reproduce-summary.json` / `reproduce.md` | 重建证据链的机器可读结果 | `validation/reproduce_evidence.py` |
| `acceptance.md` | 六项必做项的核验报告 | `validation/check_acceptance.py` |

## patches/ 里的四个文件

它们是 MiniMax 的**四次真实尝试**，编号就是尝试顺序：

| 文件 | 对应调用 | 结果 |
| --- | --- | --- |
| `20261028-222327.patch` | 第 5 次调用（第一次出补丁） | 套上了，但缺 `import re`，目标测试报 `NameError` |
| `20261028-222712.patch` | 第 6 次调用 | 套不上：diff 基于破损代码，且上下文行写错 |
| `20261028-222849.patch` | 第 7 次调用 | 仍然套不上 |
| `20261028-223255.patch` | 第 8 次调用 | **最终采用**：内容正确；模型写错了 hunk 行数，由 `git apply --recount` 修正后套上 |

## raw/ 里有什么

`raw/*.jsonl` 每行一个 JSON 事件，`kind` 区分类型：

| kind | 含义 |
| --- | --- |
| `seekdb.query` | 一次 seekdb 语句、参数与结果行数 |
| `seekdb.schema` | 建表与索引的结果 |
| `minimax.call` | 一次 MiniMax 调用：request_id、token 用量、完整回答 |
| `patch.requested` / `patch.applied` | 补丁请求与应用结果（含失败原因） |
| `testgen.requested` / `testgen.written` | 目标测试文件的生成 |
| `test.run` | 一次验收命令的执行（命令、退出码、输出） |
| `powercontext.call` | 一次 PowerContext API 调用（请求与响应） |
| `context.built` | 组装出的上下文摘要 |
| `state.saved` / `outcome.recorded` | 任务状态与步骤结果的写入 |

> 这些记录里**不含任何凭据**：MiniMax 的 API Key 不会被写进任何一条记录，
> seekdb 的连接参数也只记录在 `.env`（已 gitignore）里。
