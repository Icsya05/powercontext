| 项目 | 说明 |
| --- | --- |
| 项目 | seekdb |
| 总分 | 20 分 |
| 任务 | 选择一个大赛 Bug 进行修复 |
| Issue 标签 | `2026-competition` |
| 提交产物 | 向 seekdb 提交 Pull Request，并将 PR number 提交到提测平台 |

## 一、题目背景
修复真实问题是参与开源数据库开发的重要方式。本题要求参赛者从 seekdb 的大赛 Issue 中选择一个 Bug，完成问题复现、原因分析、代码修复和测试验证，并通过 Pull Request 向社区提交修复。

通过本题，参赛者可以熟悉 seekdb 的代码结构、调试方法和开源协作流程，体验从发现问题到提交修复的完整过程。

## 二、题目内容
### 2.1 选择 Bug
在 [seekdb 大赛 Issue 列表](https://github.com/oceanbase/seekdb/issues?q=is%3Aissue%20label%3A2026-competition)中，选择一个带有 `2026-competition` 标签的 Issue 进行修复。

阅读 Issue 中的问题描述、复现步骤和预期行为，确认问题涉及的模块及修复目标。本题的选题范围为带有该标签的大赛 Issue。

### 2.2 完成修复
1. 根据 Issue 描述复现问题，分析产生问题的原因。
2. 在 seekdb 代码中完成修复，使相关行为符合 Issue 描述的预期。
3. 验证修复结果，并检查相关功能是否受到影响；根据问题类型补充或更新回归测试。

## 三、提交方式
### 3.1 提交 Pull Request
将修复代码以 Pull Request 的形式提交到 [seekdb 仓库](https://github.com/oceanbase/seekdb)，并在 PR 描述中关联所修复的 Issue。

PR 描述应说明：

+ 对应的 Issue 编号或链接。
+ 问题原因及修复方案。
+ 测试方法、执行结果，以及修复前后的行为变化。

### 3.2 提交到提测平台
创建 PR 后，将该 PR 的 **地址** 提交到大赛提测平台的赛题二入口。

本题的提交流程为：**选择带 **`2026-competition`** 标签的 Issue → Fork seekdb仓库 → 修复并验证 → 向 seekdb 提交 PR → 将 PR 地址提交到提测平台**。

## 三、评分标准
| 得分项 | 分值 |
| --- | ---: |
| Fork仓库 | 10 |
| 提交PR | 10 |
| **合计** | **20** |
