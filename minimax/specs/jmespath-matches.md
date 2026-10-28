---
spec_id: SPEC-JP-FN-001
title: matches(subject, pattern) 正则谓词函数
target_project: sample_project/jmespath
applies_to:
  - jmespath/functions.py
  - tests/test_matches.py
status: approved
---

# SPEC-JP-FN-001 — 为 jmespath 增加 `matches()` 正则谓词函数

## 背景

`jmespath.py` 已经完整实现了 JMESPath 1.0 规范的全部 23 个内建函数
（`abs` `avg` `ceil` `contains` `ends_with` `floor` `length` `map` `max`
`max_by` `merge` `min` `min_by` `not_null` `reverse` `sort` `sort_by`
`starts_with` `sum` `to_array` `to_number` `to_string` `type` `values`），
但没有任何正则匹配能力。

在 JSON 查询里，"筛出名字里含某个模式的记录"是非常常见的需求，现有的
`starts_with` / `ends_with` / `contains` 只能覆盖前缀、后缀和子串三种情况。
本规格定义一个新的内建谓词函数 `matches()`，用 Python 正则语义补上这个缺口。

## 适用范围

本规格只描述对 `sample_project/jmespath`（上游 `jmespath.py` v1.1.0，
MIT 许可）的一次局部修改：新增一个内建函数及其验收测试。

## 术语

| 术语 | 含义 |
| --- | --- |
| subject | 被匹配的第一个参数，必须是字符串 |
| pattern | 正则表达式，第二个参数，必须是字符串 |
| 谓词 | 返回 `true` / `false` 的函数，可在 `filter` 投影里当条件用 |

## 需求

## R1 | matches 必须是恰好两个字符串参数

`matches` 注册为内建函数，签名为两个 `string` 类型的参数
（`@signature({'types': ['string']}, {'types': ['string']})`）。
参数个数不是 2、或任一参数类型不是字符串时，抛
`jmespath.exceptions.JMESPathTypeError` / `ArityError`，
错误信息格式与库内其它函数完全一致。

## R2 | 命中返回 true，未命中返回 false

`matches(subject, pattern)` 当且仅当 `subject` 中存在 `pattern` 的正则匹配时
返回 `true`，否则返回 `false`。返回值必须是真正的布尔值，不是真值字符串。

## R3 | 正则语义为 Python re.search

匹配语义采用 Python `re.search`：在 `subject` 的**任意位置**寻找匹配，
不要求整串匹配。`pattern` 按 Python `re` 的语法解释，
因此 `^` `$` `.*` `[0-9]` `\+` 等写法都按 `re` 的规则生效。

例：`matches('abc', 'b')` → `true`；`matches('abc', '^a')` → `true`；
`matches('abc', '^b')` → `false`。

## R4 | 非法正则必须报 JMESPathTypeError

`pattern` 不是合法正则时（例如 `'['`），抛
`jmespath.exceptions.JMESPathTypeError`，错误信息里必须包含函数名
`matches()` 和出错的那个 pattern 值，不得抛别的异常类型，
不得把非法正则当成"不匹配"静默返回 `false`。

## R5 | 可以在 filter 投影中当谓词用

`matches()` 必须在 `filter` 投影中可用，例如：

```
people[?matches(name, '^a')].name
```

对 `{"people": [{"name": "alice"}, {"name": "bob"}]}` 必须返回 `["alice"]`。

## R6 | 参数类型错误的信息要指明期望类型

当 `subject` 不是字符串时，错误信息里必须出现函数名 `matches()`、
实际收到的值与类型、以及期望的类型列表 `['string']`，
与库内既有函数（如 `length()`）的错误信息风格保持一致。

## 不变行为（回归要求）

## B1 | 既有内建函数行为不变

修改不得改变任何既有内建函数的签名、返回值或异常行为。
`sample_project/before/jmespath/` 里保存了修改前的模块快照，
`git diff` 必须显示既有函数体没有任何语义改动。

## B2 | 解析器、词法器、访问器不变

不得修改 `lexer.py`、`parser.py`、`visitor.py`、`ast.py` 的行为。
新增能力只通过新增一个带 `@signature` 装饰器的 `_func_*` 方法实现，
由既有的 `FunctionRegistry` 自动注册。

## B3 | 合规测试集仍然全部通过

`tests/compliance/` 下的 JMESPath 合规用例必须全部通过，
`pytest tests/` 必须全绿（修改前的基线是 991 passed, 1 skipped）。

## 验收标准

## A1 | 新增验收测试文件

新增 `tests/test_matches.py`，逐条覆盖 R1–R6（参数类型、命中与未命中、
正则语义、非法正则、filter 投影使用、错误信息内容）。

## A2 | 修改前目标测试必须失败

在实现之前运行 `pytest tests/test_matches.py`，必须因为 R1 未实现而失败
（错误信息包含 `Unknown function: matches()`），
**不允许**用缺少依赖、无法启动之类的环境错误冒充功能未实现。

## A3 | 修改后目标测试与回归测试必须全绿

实现之后，`pytest tests/test_matches.py` 全绿，
并且 `pytest tests/`（包含全部既有测试与合规用例）全绿。
测试集在修改前后保持一致，不得通过删除断言、跳过测试或修改预期结果让其通过。
