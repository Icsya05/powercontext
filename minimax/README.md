# 规有所依 —— 面向软件持续演进的 SDD 上下文管理系统

> MiniMax × OceanBase 赛题参赛作品。
> 用一个上下文模块把「规格 → 代码 → 测试 → 任务状态」串起来，
> 让 AI 开发助手在**可追溯的上下文**下完成一次真实的代码修改。

---

## 1. 作品要解决的问题

AI 开发助手改代码时需要三样东西：**当前要遵守哪些规格**、**应该改哪些代码**、
**怎么验证结果**。这三样东西通常散落在文档、代码和测试里，规格一改、任务一断，
助手就会用过期信息或漏掉约束。

本作品实现一个**上下文模块（`sddctx`）**：

1. 把规格条目、代码符号、测试用例**导入 seekdb** 并建全文索引；
2. 按任务描述**检索**出适用的规格 / 代码 / 测试，组装成开发上下文；
3. 把上下文交给 **MiniMax**，由它产出代码补丁；
4. **运行目标测试与回归测试**；
5. 把任务状态写入 **PowerContext**，模块重启后能读回并继续使用。

---

## 2. 三项技术的分工

| 技术 | 在本作品里承担的作用 | 接入方式 |
| --- | --- | --- |
| **MiniMax** | 参与本次任务的**代码生成与修改**：先按规格写出目标测试文件，再写出实现补丁 | OpenAI 兼容接口 `https://api.minimaxi.com/v1`，模型 `MiniMax-M3` |
| **seekdb** | 存储工程资料并建**中文全文索引**；上下文里的规格条目、代码符号、测试用例都是**查询结果** | MySQL 协议 `root@sys@127.0.0.1:2881`，库 `sdd_context`，索引 `WITH PARSER ik` |
| **PowerContext** | 保存**任务进展与验证结果**（Work Contract / Task Outcome / Atomic Memory），模块重启后读回使用 | HTTP API `http://127.0.0.1:8000`（PowerContext 1.4.1），MCP 亦可（`/mcp`） |

三者都不是「装上就算」：**seekdb 的查询结果直接决定送给模型的上下文**，
**MiniMax 的输出就是被应用的补丁**，**PowerContext 里的状态会在下次运行时进入上下文**。

---

## 3. 目录结构

```text
minimax/
├── README.md                      本文件：一页技术说明 + 交付索引
├── specs/                         SDD 规格（带稳定 ID，模块会解析导入）
│   └── jmespath-matches.md        SPEC-JP-FN-001
├── tasks/                         开发任务文档（目标 / 保持行为 / 验收命令）
│   └── T-2026-001.md
├── sddctx/                        上下文模块源码
│   ├── cli.py                     命令行入口
│   ├── config.py                  配置与路径
│   ├── documents.py               规格 / 任务文档解析
│   ├── code_index.py              Python 源码与测试的 AST 索引
│   ├── seekdb_store.py            seekdb 访问层（建表 / 写入 / 检索）
│   ├── context.py                 上下文组装
│   ├── minmax_client.py           MiniMax 调用
│   ├── powercontext_client.py     PowerContext 调用
│   ├── runner.py                  流水线
│   ├── evidence.py                证据记录
│   └── tests/                     模块自身的单元测试
├── sample_project/
│   ├── jmespath/                  被修改的业务工程（上游 jmespath.py，MIT）
│   └── before/                    修改前的代码快照
├── validation/
│   └── check_acceptance.py        六项必做项自动核验
├── deploy/
│   └── powercontext.env.example   PowerContext 服务配置模板
├── evidence/                      真实运行证据
│   ├── raw/                       每次运行的原始 JSONL 记录
│   ├── patches/                   MiniMax 产出的补丁
│   ├── test-before.txt            修改前的目标测试输出
│   └── acceptance.md              六项必做项核验报告
└── docs/
    ├── RUN.md                     运行说明
    ├── WALKTHROUGH.md             验证样例
    └── EVIDENCE.md                技术使用记录
```

---

## 4. 模块结构与上下文选择方式

```text
        specs/*.md ──┐
        tasks/*.md ──┼──> import ──> seekdb (sdd_spec / sdd_code / sdd_test)
   sample_project/ ──┘                    │
                                          │  MATCH(content) AGAINST (关键词)
                                          ▼
                                     context 组装
                                          │
            ┌─────────────────────────────┼──────────────────────────────┐
            ▼                             ▼                              ▼
      适用规格条目(R/B/A)          要改的代码符号                 验证用的测试
            └─────────────────────────────┼──────────────────────────────┘
                                          ▼
                       MiniMax（生成补丁 / 生成目标测试）
                                          ▼
                        git apply ──> pytest ──> 状态写入 PowerContext
```

### 4.1 上下文是怎么选出来的

1. **关键词**来自任务文档显式声明的 `keywords`（没有则从标题与目标抽取）。
2. **规格条目**：`MATCH(content) AGAINST (关键词)` 命中 `sdd_spec`，
   再把任务声明的 `spec_ids` 的**全部小节**补齐 —— 保证模型看到完整的需求集。
3. **代码符号**：优先取任务 `applies_to` 声明的文件里**全部**符号
   （这就是要改的文件），再补上全文检索命中的若干符号。
4. **测试用例**：优先取任务 `target_tests` 声明的测试文件里的用例，
   再补上全文检索命中的若干用例。
5. **任务状态**：从 PowerContext 读回的「已完成 / 待办 / 已验证」也进上下文。

每一条都带**文件路径 + 行号**，模型看到的每段代码、每条规格都能回到真实位置。

### 4.2 上下文输出能定位什么

官方题面 §2.3 要求上下文能定位四类信息，模块逐条对应：

| 题面要求 | 模块输出 |
| --- | --- |
| 本次任务适用的规格条目 | `SPEC-JP-FN-001#R1` … `#R6`（含来源行号） |
| 需要修改的代码文件或符号 | `jmespath/functions.py :: Functions._func_matches`（含来源行号） |
| 用于验证功能及兼容性的测试 | `tests/test_matches.py::TestMatches.test_r2_…`（含来源行号） |
| 已完成事项、待办事项和已有验证结果 | 来自 PowerContext 的任务状态 |

---

## 5. 任务与规格

| 项 | 值 |
| --- | --- |
| 业务工程 | `jmespath.py` v1.1.0（MIT），上游 commit `2812594e69d43098ef60f81f4efc404c071b0418` |
| 任务 | `T-2026-001` —— 为 jmespath 增加 `matches()` 正则谓词函数 |
| 规格 | `SPEC-JP-FN-001` —— 6 条需求（R1–R6）、3 条不变行为（B1–B3）、3 条验收（A1–A3） |
| 目标测试 | `tests/test_matches.py`（由 MiniMax 按规格生成） |
| 回归测试 | 项目原有的 `pytest tests/`（基线 991 passed, 1 skipped） |

规格全文见 [`specs/jmespath-matches.md`](specs/jmespath-matches.md)，
任务全文见 [`tasks/T-2026-001.md`](tasks/T-2026-001.md)。

---

## 6. 交付索引

| 官方要求 | 交付物 |
| --- | --- |
| 完整源码 | `sddctx/`（模块）、`sample_project/`（业务工程）、`validation/`（核验脚本） |
| 运行说明 | [`docs/RUN.md`](docs/RUN.md) |
| 验证样例 | [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) |
| 代码与测试 | `sample_project/before/`（修改前快照）、`evidence/patches/`（补丁）、`evidence/test-before.txt`、`evidence/acceptance.md` |
| 技术使用记录 | [`docs/EVIDENCE.md`](docs/EVIDENCE.md) + `evidence/raw/*.jsonl`（模块自动记录） |
| 一页技术说明 | 本文件 |

---

## 7. 快速开始

```bash
cd minimax
python -m sddctx doctor          # 检查 seekdb / PowerContext / MiniMax
python -m sddctx import          # 把规格、代码、测试导入 seekdb
python -m sddctx context --task T-2026-001    # 看上下文
python -m validation.check_acceptance         # 核验六项必做项
```

完整步骤（依赖安装、PowerContext 启动、配置）见 [`docs/RUN.md`](docs/RUN.md)。
