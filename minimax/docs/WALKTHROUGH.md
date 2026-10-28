# 验证样例

> 官方赛题「提交材料 → 验证样例」要求的交付物：
> 任务描述、有效规格、初始数据、操作步骤、预期结果及重置方法。

---

## 1. 任务描述

| 项 | 内容 |
| --- | --- |
| 任务编号 | `T-2026-001` |
| 标题 | 为 jmespath 增加 `matches()` 正则谓词函数 |
| 业务工程 | `minimax/sample_project/jmespath` —— 上游 jmespath.py v1.1.0（MIT），commit `2812594e69d43098ef60f81f4efc404c071b0418` |
| 要改什么 | 在 `jmespath/functions.py` 里新增内建谓词函数 `matches(subject, pattern)`，让 JSON 查询可以用正则做筛选条件，例如 `people[?matches(name, '^a')].name` |
| 哪些原有行为必须保持 | 既有 23 个内建函数的签名/返回值/异常行为不变；`lexer.py` / `parser.py` / `visitor.py` / `ast.py` 行为不变；合规测试集全部通过；回归基线（991 passed, 1 skipped）不得退化 |

---

## 2. 有效规格

规格全文：[`../specs/jmespath-matches.md`](../specs/jmespath-matches.md)（`SPEC-JP-FN-001`）。

上下文中**必须出现**的条目与来源位置（`sddctx context` 的实际输出）：

| 条目 | 种类 | 来源 |
| --- | --- | --- |
| `SPEC-JP-FN-001#R1` | requirement | `minimax/specs/jmespath-matches.md:40` |
| `SPEC-JP-FN-001#R2` | requirement | `minimax/specs/jmespath-matches.md:48` |
| `SPEC-JP-FN-001#R3` | requirement | `minimax/specs/jmespath-matches.md:53` |
| `SPEC-JP-FN-001#R4` | requirement | `minimax/specs/jmespath-matches.md:62` |
| `SPEC-JP-FN-001#R5` | requirement | `minimax/specs/jmespath-matches.md:69` |
| `SPEC-JP-FN-001#R6` | requirement | `minimax/specs/jmespath-matches.md:79` |
| `SPEC-JP-FN-001#B1` / `#B2` / `#B3` | invariant | `…:87` / `…:93` / `…:99` |
| `SPEC-JP-FN-001#A1` / `#A2` / `#A3` | acceptance | `…:106` / `…:111` / `…:117` |

上下文中**必须出现**的代码来源：

| 符号 | 来源 |
| --- | --- |
| `jmespath/functions.py :: <imports>` | `…/jmespath/functions.py:1` |
| `jmespath/functions.py :: Functions._func_matches` | `…/jmespath/functions.py`（实现所在行） |

上下文中**必须出现**的测试来源：

| 测试 | 来源 |
| --- | --- |
| `tests/test_matches.py::TestMatches.test_r1_requires_exactly_two_string_arguments` | `…/tests/test_matches.py` |
| `…::test_r2_returns_true_for_a_match_and_false_for_no_match` | 同上 |
| `…::test_r3_uses_python_re_search_semantics` | 同上 |
| `…::test_r4_invalid_regex_raises_jmespath_type_error` | 同上 |
| `…::test_r5_can_be_used_as_a_filter_predicate` | 同上 |
| `…::test_r6_type_error_message_includes_value_type_and_expected_types` | 同上 |

---

## 3. 初始数据

| 数据 | 位置 | 初始状态 |
| --- | --- | --- |
| 规格条目 | seekdb `sdd_context.sdd_spec` | 导入后 12 行（`SPEC-JP-FN-001` 的 R1–R6、B1–B3、A1–A3） |
| 代码符号 | seekdb `sdd_context.sdd_code` | 导入后 335 行 |
| 测试用例 | seekdb `sdd_context.sdd_test` | 导入后 87 行 |
| 任务状态 | PowerContext scope `sdd task T-2026-001` | **空**（没有 `sdd.task.state` 记忆） |
| 业务工程代码 | `minimax/sample_project/jmespath/jmespath/functions.py` | 与 `minimax/sample_project/before/` 快照逐字节一致（`matches()` 未实现） |
| 目标测试 | `minimax/sample_project/jmespath/tests/test_matches.py` | 由 MiniMax 按规格生成 |

> 「任务状态为空」是赛题明确要求的起点：从空状态开始保存任务记录，
> 重启模块后才能读回并使用。

---

## 4. 操作步骤

前置条件：`seekdb`、`PowerContext`、`MiniMax` 三者都可达
（`python -m sddctx doctor` 输出三段 `status: ok/ready`）。

```bash
cd minimax

# 步骤 1 —— 导入任务涉及的规格、代码和测试资料
python -m sddctx import
#   期望：{"specs": 12, "code": 335, "tests": 87, "stored": {...}}

# 步骤 2 —— 根据任务选择相关资料，形成开发上下文
python -m sddctx context --task T-2026-001
#   期望：打印出上面第 2 节列出的规格条目、代码符号、测试用例，
#         每一项都带文件路径 + 行号

# 步骤 3 —— 把上下文交给 MiniMax，完成代码修改
#   3a 先让 MiniMax 按规格写出目标测试
python -m sddctx testgen --task T-2026-001
#   3b 再让 MiniMax 依据上下文产出实现补丁并应用
python -m sddctx patch --task T-2026-001
#   期望：{"exit_code": 0, "patch_path": "minimax/evidence/patches/<...>.patch"}

# 步骤 4 —— 运行功能与回归测试
cd sample_project/jmespath
python -m pytest tests/test_matches.py -q     # 目标功能测试
python -m pytest tests/ -q                    # 相关回归测试

# 步骤 5 —— 保存任务状态，并验证重启后能读回
cd ../..
python -m sddctx state --task T-2026-001
#   期望：打印 scope_id 和 state（finished / todo / verification）
```

一条命令重建整条证据链（推荐给评审）：

```bash
cd minimax
python -m validation.reproduce_evidence
python -m validation.check_acceptance
```

---

## 5. 预期结果

### 5.1 修改前（目标行为未实现）

```bash
cd minimax/sample_project/jmespath
python -m pytest tests/test_matches.py -q
```

**期望：6 个测试全部失败，失败原因是功能未实现，而不是环境错误。**

```text
E   jmespath.exceptions.UnknownFunctionError: Unknown function: matches()
...
FAILED tests/test_matches.py::TestMatches::test_r1_requires_exactly_two_string_arguments
FAILED tests/test_matches.py::TestMatches::test_r2_returns_true_for_a_match_and_false_for_no_match
FAILED tests/test_matches.py::TestMatches::test_r3_uses_python_re_search_semantics
FAILED tests/test_matches.py::TestMatches::test_r4_invalid_regex_raises_jmespath_type_error
FAILED tests/test_matches.py::TestMatches::test_r5_can_be_used_as_a_filter_predicate
FAILED tests/test_matches.py::TestMatches::test_r6_type_error_message_includes_value_type_and_expected_types
6 failed
```

完整输出：[`../evidence/test-before-tests-test_matches.py_-q.txt`](../evidence/test-before-tests-test_matches.py_-q.txt)。

### 5.2 修改后

```bash
cd minimax/sample_project/jmespath
python -m pytest tests/test_matches.py -q   # 6 passed
python -m pytest tests/ -q                  # 996 passed, 1 skipped
```

**期望：目标测试全绿，回归测试全绿。**
回归基线是 991 passed + 1 skipped，新增 6 个目标测试 → 997 个用例中 996 通过、1 跳过。

完整输出：[`../evidence/test-after-tests-test_matches.py_-q.txt`](../evidence/test-after-tests-test_matches.py_-q.txt)、
[`../evidence/test-after-tests-_-q.txt`](../evidence/test-after-tests-_-q.txt)。

### 5.3 状态复用

```bash
cd minimax
python -m sddctx state --task T-2026-001
```

**期望**：读回的 state 里包含

```json
{
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
  ]
}
```

并且这些内容会出现在下一次 `sddctx context` 的「progress recorded by earlier runs」段落里。

### 5.4 规格更新后重新导入

```bash
cd minimax
# 改一下 specs/jmespath-matches.md 里 R2 的标题
python -m sddctx import
python -m sddctx context --task T-2026-001
```

**期望**：上下文里的 R2 标题变成新写的那个，而不是固定答案。
`validation/check_acceptance.py` 里的 `context-follows-spec-edit` 就是在自动做这件事
（改规格 → 重新导入 → 校验上下文用了新内容 → 还原规格 → 再导入）。

---

## 6. 重置方法

把一切恢复到「任务开始前」的状态：

| 要重置的东西 | 命令 |
| --- | --- |
| 业务工程代码 | `cd minimax && python -m sddctx patch --task T-2026-001 --revert`（从 `sample_project/before/` 快照还原） |
| 目标测试文件 | 删除 `minimax/sample_project/jmespath/tests/test_matches.py`，再 `python -m sddctx import` 清掉 seekdb 里对应的行 |
| seekdb 里的资料 | `python -m sddctx import` 是幂等的，重新导入即刷新；要把三张表清空则直接 `DELETE FROM sdd_spec / sdd_code / sdd_test` |
| PowerContext 里的任务状态 | `curl -X POST http://127.0.0.1:8000/v1/memory/remember` 不可用时，直接删掉 scope `sdd task T-2026-001`（`DELETE /v1/scopes/{scope_id}`），或新建一个幂等键换一个 scope |
| 完整重来一遍 | `python -m validation.reproduce_evidence` —— 回滚 → 跑失败 → 应用补丁 → 跑通过 → 重新导入 → 存状态 |

> 「从空状态开始保存任务记录，重启模块后能够读取，并用于后续上下文或任务处理」
> 这一条验收项，由 `validation/check_acceptance.py` 的 `state-reuse` 检查自动完成：
> 它用一个**独立的进程**去 PowerContext 读回状态，再把读到的状态喂给上下文组装，
> 并检查上下文里确实出现了已完成 / 待办 / 已验证三类内容。
