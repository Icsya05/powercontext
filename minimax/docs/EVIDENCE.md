# 技术使用记录

> 官方赛题「提交材料 → 技术使用记录」要求的交付物：
> MiniMax 开发记录、数据库查询记录、PowerContext 状态写入与复用记录。

本文件里的每个数字都来自模块自己写的原始记录
（`../evidence/raw/*.jsonl`，共 4446 条事件），不是手工抄写的。

---

## 1. MiniMax 开发记录

### 1.1 调用一览

模型：`MiniMax-M3`；端点：`https://api.minimaxi.com/v1/chat/completions`（OpenAI 兼容）。

| # | 时间 | 用途 | request_id | prompt tokens | completion tokens | 其中 reasoning |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 21:55:48 | `doctor` 连通性自检 | `073131e3d08ed3e4ee6625246e88955f` | 198 | 12 | 8 |
| 2 | 21:56:48 | `doctor` 连通性自检 | `073132202ce811a8d445908a43686809` | 198 | 10 | 6 |
| 3 | 22:04:32 | **生成目标测试** `tests/test_matches.py` | `073133a2c2b27255e8b8242a9887f883` | 10 914 | 8 192 | 7 633 |
| 4 | 22:19:35 | **重写目标测试**（上一次被输出预算截断） | `07313718b044cff4413f7ad7fe602a67` | 10 914 | 8 475 | 7 752 |
| 5 | 22:23:27 | **生成实现补丁**（第 1 版） | `073137f831081b11882252e452739c01` | 10 907 | 13 368 | 13 136 |
| 6 | 22:27:12 | **修正实现补丁**（第 2 版，带失败反馈） | `07313903440ea21ed089543400102f40` | 13 715 | 6 613 | 6 409 |
| 7 | 22:28:49 | **修正实现补丁**（第 3 版，带失败反馈） | `07313971e3c2dc50510f73a39a5ef99c` | 14 878 | 6 304 | 6 035 |
| 8 | 22:32:55 | **修正实现补丁**（第 4 版，带失败反馈 + 完整文件原文） | `07313a5bec51c59d72b86e7092cd7c84` | 18 328 | 6 715 | 6 460 |
| 9 | 22:36:54 | **修正目标测试**（R3 用例的转义 bug） | `07313b64674a225f54f73db239e8b4ea` | 17 513 | 3 348 | 2 626 |

合计：**prompt 97 565 tokens，completion 53 037 tokens**（其中 reasoning 51 377）。

完整的问答原文见 [`../evidence/minimax-usage.md`](../evidence/minimax-usage.md)。

### 1.2 模型实际做了什么

| 产物 | 来源调用 | 说明 |
| --- | --- | --- |
| `minimax/sample_project/jmespath/tests/test_matches.py` | #3、#4、#9 | 按 `SPEC-JP-FN-001` 的 R1–R6 写的验收测试，一需求一用例 |
| `minimax/sample_project/jmespath/jmespath/functions.py` 的 `matches()` 实现 | #5、#6、#7、#8 | 由 #5 首次产出，经 #6–#8 三轮反馈修正 |

最终落到仓库里的代码差异（[`../evidence/code-diff.patch`](../evidence/code-diff.patch)）：

```diff
--- a/minimax/sample_project/before/jmespath/functions.py
+++ b/minimax/sample_project/jmespath/jmespath/functions.py
@@ -1,5 +1,6 @@
 import math
 import json
+import re

 from jmespath import exceptions
 from jmespath.compat import string_type as STRING_TYPE
@@ -226,6 +227,14 @@
     def _func_starts_with(self, search, suffix):
         return search.startswith(suffix)

+    @signature({'types': ['string']}, {'types': ['string']})
+    def _func_matches(self, subject, pattern):
+        try:
+            return re.search(pattern, subject) is not None
+        except re.error:
+            raise exceptions.JMESPathTypeError(
+                'matches', pattern, 'string', ['string'])
+
     @signature({'types': ['array', 'string']})
```

### 1.3 迭代过程（真实发生过的问题）

模型不是一次就写对的，下面是每一轮的问题与修正 —— 这些都留在原始记录里：

| 轮次 | 现象 | 原因 | 修正 |
| --- | --- | --- | --- |
| #3 | 生成的文件在第 62 行被截断 | `max_tokens=8192` 被推理段（7 633 tokens）吃光 | 把预算提到 32 768，并接受语言标记的代码围栏 |
| #5 | 补丁套上了，但目标测试报 `NameError: name 're' is not defined` | 没有加 `import re` | 把测试失败输出回灌给模型（#6） |
| #6 | 补丁**套不上**（`patch does not apply`） | diff 是基于 #5 那版破损代码做的，还把 `jmespath.compat` 写成了 `jmespath.utils` | 先回滚再重新导入，让模型对着**原始文件**做 diff（#7） |
| #7 | 仍然套不上 | 同上，且上下文里的 import 块索引不完整 | 给上下文补上「待改文件的完整原文」，并把 `import re` 单独作为一条索引项（#8） |
| #8 | `git apply` 报 `corrupt patch` | 模型写错了 hunk 头的行数（声明 6 行，实际 5 行） | 模块改用 `git apply --recount`，由 git 自行重算行数 → 应用成功 |
| #9 | 目标测试 R3 用例报 `LexerError` | 测试自己写错了转义：反引号里是 JSON，`\+` 不是合法 JSON 转义 | 把 LexerError 回灌给模型，模型重写了整个测试文件（没有削弱断言） |

> 第 8 轮之后没有再请求新的实现补丁：最终采用的补丁就是 #8 产出的那份，
> 由 `validation/reproduce_evidence.py` 在重建证据链时重新应用。

---

## 2. 数据库查询记录

数据库：**seekdb**（`oceanbase/seekdb:1.4.0-100000172026082615`），
库 `sdd_context`，认证 `root@sys@127.0.0.1:2881`。

### 2.1 规模

| 表 | 行数 | 内容 |
| --- | --- | --- |
| `sdd_spec` | 12 | `SPEC-JP-FN-001` 的 R1–R6 / B1–B3 / A1–A3 |
| `sdd_code` | 335 | 业务工程的 import 块、函数、类、方法 |
| `sdd_test` | 87 | 业务工程与新增目标测试的每一个用例 |

三张表都建了中文全文索引：

```sql
CREATE FULLTEXT INDEX idx_sdd_spec_fts ON sdd_spec (content) WITH PARSER ik;
CREATE FULLTEXT INDEX idx_sdd_code_fts ON sdd_code (content) WITH PARSER ik;
CREATE FULLTEXT INDEX idx_sdd_test_fts ON sdd_test (content) WITH PARSER ik;
```

### 2.2 模块实际跑过的语句

整个开发过程一共执行了 **4 363 条 seekdb 语句**（含导入时的逐行 upsert）。
去重后的语句清单见 [`../evidence/seekdb-queries.md`](../evidence/seekdb-queries.md)。

其中**真正用于构造上下文**的是全文检索：

```sql
SELECT * FROM sdd_spec WHERE MATCH(content) AGAINST (%s) ORDER BY updated_at DESC LIMIT %s
SELECT * FROM sdd_code WHERE MATCH(content) AGAINST (%s) ORDER BY updated_at DESC LIMIT %s
SELECT * FROM sdd_test WHERE MATCH(content) AGAINST (%s) ORDER BY updated_at DESC LIMIT %s
```

以及按任务声明的文件精确取回：

```sql
SELECT * FROM sdd_code WHERE file_path = %s ORDER BY source_line
SELECT * FROM sdd_test WHERE file_path = %s ORDER BY source_line
SELECT * FROM sdd_spec WHERE spec_id = %s ORDER BY section_id
```

### 2.3 检索结果确实进了上下文

`sddctx context` 的真实输出（节选，完整版见
[`../evidence/context-T-2026-001.json`](../evidence/context-T-2026-001.json)）：

```text
Retrieval : keyword='matches signature types string predicate filter JMESPathTypeError regex'
            specs=12 code=49 tests=8
            (modes: spec=fulltext, code=fulltext, test=fulltext)
```

三种检索模式都是 `fulltext`，说明走的是 seekdb 的中文全文索引，
不是 LIKE 扫描。

### 2.4 规格更新后重新导入会跟着变

`validation/check_acceptance.py` 的 `context-follows-spec-edit` 检查自动做了这件事：

1. 在 `specs/jmespath-matches.md` 的 R2 标题里插入标记 `PROBE-EDIT-9137`；
2. 重新执行 `import`；
3. 重新组装上下文，检查新标记出现在检索结果里；
4. 还原规格文件并重新导入。

结果：**PASS** —— 上下文用的是更新后的内容，不是固定答案。

---

## 3. PowerContext 状态写入与复用记录

服务：**PowerContext 1.4.1**（PyPI），`http://127.0.0.1:8000`，SQLite 后端，
MCP 端点同时在 `http://127.0.0.1:8000/mcp`。
健康检查 `{"status":"ready", ... "inference.generation":"ready" ...}`。

### 3.1 写入用到的 API

| API | 用途 |
| --- | --- |
| `POST /v1/scopes` | 为任务建一个独立 Scope（幂等键 `sddctx:T-2026-001`） |
| `POST /v1/work/contracts/create` | 记录任务的委托基线（目标、事实、范围内、范围外、完成标准） |
| `POST /v1/work/outcomes/record` | 记录每一步的结果（状态、检查项、剩余工作） |
| `POST /v1/memory/remember` | 写入任务状态（`kind = sdd.task.state`） |
| `POST /v1/memory/search` | **读回**任务状态 |

### 3.2 写入的内容

Work Contract（任务基线）的字段：

```json
{
  "schema": "powercontext.work-contract.v1",
  "trust": "untrusted_input",
  "objective": "Implement matches(subject, pattern) in jmespath/functions.py per SPEC-JP-FN-001.",
  "facts": [{"text": "jmespath.py 1.1.0 implements all 23 JMESPath 1.0 builtins but has no regex predicate.",
             "basis": "declared", "evidence": []}],
  "in_scope": ["jmespath/functions.py", "tests/test_matches.py"],
  "exclusions": ["lexer.py", "parser.py", "visitor.py", "ast.py"],
  "completion_criteria": ["pytest tests/test_matches.py passes", "pytest tests/ stays green"],
  "authorization_notes": [], "open_questions": []
}
```

Task Outcome（每步结果）记录了验收命令与退出码：

```json
{
  "schema": "powercontext.task-outcome.v1",
  "status": "succeeded",
  "checks": [
    {"name": "python -m pytest tests/test_matches.py -q", "status": "passed", "details": "exit 0"},
    {"name": "python -m pytest tests/ -q", "status": "passed", "details": "exit 0"}
  ],
  "remaining_work": []
}
```

### 3.3 读回来（重启后复用）

原子记忆里的任务状态原文（`sdd.task.state`）：

```json
{
  "task_id": "T-2026-001",
  "step": "patched-and-tested",
  "finished": [
    "MiniMax wrote the acceptance test tests/test_matches.py",
    "MiniMax patch applied to the working tree",
    "python -m pytest tests/test_matches.py -q passed",
    "python -m pytest tests/ -q passed"
  ],
  "todo": [],
  "verification": [
    "python -m pytest tests/test_matches.py -q -> exit 0 (passed)",
    "python -m pytest tests/ -q -> exit 0 (passed)",
    "python -m pytest tests/test_matches.py -q -> exit 1 (failed, feature not implemented)",
    "python -m pytest tests/ -q -> exit 1 (failed, feature not implemented)"
  ],
  "patch_applied": true,
  "tests_passed": true
}
```

完整快照：[`../evidence/state-from-powercontext.json`](../evidence/state-from-powercontext.json)。

### 3.4 复用确实发生了

`validation/check_acceptance.py` 的 `state-reuse` 检查：

1. 用一个**独立的进程**通过 `POST /v1/memory/search` 读回状态；
2. 把读到的状态交给上下文组装（`build_context(..., state=state)`）；
3. 检查上下文里出现了「已完成 / 待办 / 已验证」三类内容。

结果：**PASS**（`used_in_context: true`）。

也就是说，模块重启之后，**上一次跑完的进展和验证结果会重新进入送给 MiniMax 的上下文**。

---

## 4. 六项必做项的核验结果

`python -m validation.check_acceptance` 的输出（完整报告：
[`../evidence/acceptance.md`](../evidence/acceptance.md)）：

| 官方验收项 | 检查名 | 结果 |
| --- | --- | --- |
| 能够运行 | `runnable` | **PASS** —— seekdb、PowerContext、MiniMax 与模块自身全部可用 |
| MiniMax 实际参与 | `minimax-involved` | **PASS** —— 9 次模型调用有记录，4 个补丁文件在盘上，实现确实落在交付文件里且与修改前快照不同 |
| 上下文正确 | `context-correct` | **PASS** —— 12 条规格 / 49 个代码符号 / 8 个用例，每个来源都在磁盘上核对过 |
| 上下文正确（规格更新后重新导入） | `context-follows-spec-edit` | **PASS** —— 改规格再导入，检索结果随之改变 |
| 数据库实际参与 | `database-involved` | **PASS** —— seekdb 里 12/335/87 行，4 357 条语句被记录，其中 24 条是全文检索 |
| 状态能够复用 | `state-reuse` | **PASS** —— 独立进程读回状态并用于上下文 |
| 代码修改有效 | `code-change-effective` | **PASS** —— 修改前因 `UnknownFunctionError` 失败，修改后目标测试与全量回归全绿 |

**7/7 通过。**
