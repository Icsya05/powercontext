# 2026 初赛交付与提测说明

截至北京时间 2026-10-26，本分支基于官方 `2026-competition`，产品基线为 `9db1753434162c0aa7c9f1189a1722e617880a52`。官方题面、测试、依赖、数据和评分资产均未修改。

## 本分支已实现

| 赛题 | 公开测试 | 验证范围 |
| --- | ---: | --- |
| CSV 行级采集与原始记录回查 | 17 通过 | 原始字符串、身份、错误原子性、真实入库、重启、精确引用 |
| HTTP 重排服务接入与跨批次排序 | 10 通过 | 严格响应、跨批覆盖、全局稳定排序、请求计数、原生 Memory 搜索 |
| Embedding 并发请求合并与向量缓存 | 8 通过 | 去重、LRU、失败/取消隔离、usage、6 scope / 24 文本恰好 4 次请求 |
| 上下文增量传输与完整重建 | 14 通过 | wire 编码/摘要/字节数、UTF-8、完整重建、原生 prepare 集成 |
| 财报 PDF 全文解析与证据页检索 | 6 通过 | 全部 503 物理页、空白/权限页、修订身份、原生持久化和引用回查 |

另有 172 项补充及相关原有回归测试通过。Ruff 检查、格式检查通过；改动源码的 ty 检查无错误，原有 `application.py` 有 6 条 AsyncIterator 弃用警告。

一次真实边界回归发现 HTTP 大整数分数转换为 float 会丢失排序精度，补充测试已先失败再通过；现保留 JSON 整数精度。

独立审查针对实现提交 `b331af489e0889261331aa4b3cf0f9f155d2f8f0` 未发现需要修复的问题；另行复核 50 项补充测试、172 项回归、500 次随机 Unicode 分块与序列化重建，以及全部等待者取消后 provider 失败的异常处理。

本地补充测量采用固定 QMSum ES2004a 原始会议文件（SHA-256 `911e56db0d8482f1e730bae0a8fcf0ab0095c94abb000ba0516e975fa6e48b31`），8 条真实 turn 起步，后续追加 3 条，每 5 轮切换一次查询：40 轮均非空，产生 8 种上下文。普通正文累计 59,070 bytes，首次完整包加后续 delta 累计 24,627 bytes，净节省 58.31%；完整 v1 pack 累计 85,440 bytes，独立 gzip 对照 31,125 bytes。这是明确控制的本地测量序列，不能替代平台完整序列。

503 页公开财报的五个问题分别返回 20、20、20、9、12 个真实页面 citation，均经过 Memory 精确读取核对；这些数量不代表标注证据页的召回率。

## 提测填写

- 产品仓库：`https://github.com/Icsya05/powercontext`
- 代码分支：`competition/csv-row-evidence`
- 代码版本：使用该分支实际最新的完整 40 位 commit SHA。
- 必须明确指定代码分支或完整 commit；仓库默认 `master` 不包含这些赛题实现。
- 仓库准备题只填仓库 HTTPS URL；私有仓库还需要按赛事要求授予读取权限。
- 不在公开链接、文档或代码中填写 GitHub Token、模型 Key 或密码。

公开测试通过不等于正式得分。尚未核验平台私有仓库读取权限，也未在提测平台提交或取得分数。

## 复现

在 Linux x86_64 / Python 3.12 环境使用官方固定依赖：

```bash
make -C competition install
make -C competition check-baseline
make -C competition test-csv test-rerank test-embedding test-incremental test-pdf
```

补充回归使用相同依赖，从仓库根目录执行：

```bash
PYTHONPATH=src:competition PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  -c competition/pytest.ini --confcutdir=competition \
  tests/test_sources.py tests/test_source_observations.py \
  tests/builtin/artifacts/memory/test_reranking.py \
  tests/builtin/runtime/test_prepared_context.py tests/builtin/inference \
  tests/test_csv_rows.py tests/test_http_reranker.py tests/test_embedding_coalescing.py \
  tests/test_context_pack.py tests/test_pdf_pages.py
```

本机 WSL 的网络受到 Windows 代理 NAT 连接限制，因此使用 Windows 下载的相同固定 Linux wheel 离线安装；未更改官方 requirements。测试环境位于 `/home/ocean/.venvs/powercontext-2026`。

## 质量验收边界

- PDF 完整评测的 5 份财报 / 1151 页 / 24 个问题、逐页词项质量和 Recall@20 尚未执行；公开测试仅证明其公开范围。
- HTTP 重排的完整 173 文档 / 20 query 质量门槛尚未执行。
- 增量协议的完整 8 turn / 40 轮、至少 45% 净 wire 节省尚未执行。
- 没有访问隐藏标签、答案或评分数据，没有硬编码文档、query 或测试顺序。

## 其他赛题与后续入口

已阅读官方 seekdb 基础、内核四组题面、PowerContext 全部题面和 AMD/MiniMax/Qoder/阶跃/Dify/高德/魔搭要求。当前没有实现或宣称完成以下任务：

- PowerContext：Pi 会话、数量触发、来源生命周期、原文证据选择、单 SQL 混合检索。
- seekdb：比赛标记 Issue 修复，AI 函数六子题、文件 SQL、异步 AI 列、全文索引调优；这些需要实际内核构建及专门验证。
- 生态项目：AMD 需要实际 GPU 构建；MiniMax、Qoder 需要各自真实开发记录；阶跃需要浏览器本地推理与 seekdb 混合检索；Dify 需要真实可运行流程。不能以文档或演示代码代替其实际参与证明。
- 高德独立交付在 `competition/nearby-skill` 分支的 `gaode/SKILL.md`，仅需上传该文件。格式和四个独立场景检查通过，尚未接受平台真实高德工具评测。
- 魔搭要求真实上传自己的 Skill 并取得作品页面 URL 或编号；尚未上传。

官方页面间部分题数、分值文字有差异，正式题目和成绩以最新提测平台为准。
