# PowerContext 初赛核心代码交接

记录日期：2026-10-26，北京时间。代码已推送，另一台电脑可以从 GitHub 继续；运行环境按下面的步骤重新建立即可，不需要原电脑的 WSL 或数据库。

## 代码题填写信息

- 仓库 HTTPS URL：`https://github.com/Icsya05/powercontext`
- 工作分支：`competition/prelim-integration`
- 已测试代码 commit：`39a12dbf95da799c7160bb9a7528cbc944215a47`
- 该版本的 `src/` Git tree：`e2d88f781fdfc2642764dae0c9b99586f2f38128`
- 冻结基线：`9db1753434162c0aa7c9f1189a1722e617880a52`，已确认在历史中，官方 `check-baseline` 通过。

默认 `master` 没有这些比赛实现。代码题提交要填写上面的完整代码 commit，不能只填仓库后任由平台读取默认分支。仓库准备题仅填仓库 URL。后续只增加交接文档的 commit 不改变上述已测试代码。

## 已实现及整合验证

在逐文件 SHA-256 核对的 Linux 原生文件系统副本中，运行全部十项代码题公开目标，命令最终退出码 0，**95 个公开测试全部通过**：

| 题目 | 实现 | 公开测试 |
| --- | --- | ---: |
| `source-01-table-evidence` | CSV 行证据与可回查原文 | 17 |
| `source-02-pi-history` | Pi 会话图、原始记录、持久化连接器断点 | 15 |
| `source-03-pdf-retrieval` | PDF 逐页来源、精确引用 | 6 |
| `memory-01-source-lifecycle` | 持久化依赖图、停用恢复、重试与审计 | 4 |
| `memory-02-embedding-batches` | 跨 scope 并发 Embedding 合批与缓存 | 8 |
| `retrieval-01-reranking` | HTTP 重排、合法降级与分数精度 | 10 |
| `retrieval-02-hybrid-search` | seekdb 数据库内单语句双通道候选召回 | 1 |
| `processing-01-count-trigger` | Memory/Topic 数量阈值与时间/显式触发组合 | 17 |
| `context-01-evidence-selection` | 查询驱动原文片段、精确坐标与完整字节预算 | 3 |
| `context-02-incremental-pack` | 可还原的增量上下文包 | 14 |

同一整合副本的来源、连接器、Memory 服务、上下文、数量触发和各题自有测试：**251 passed, 13 skipped，29.26 秒**。跳过项按测试原有条件保留，不改测试让它通过。整合公开数量触发测试 237.35 秒；整合真实 seekdb 混合检索测试 39.86 秒；生命周期 23.19 秒。

官方 `competition/` 题面、测试、样例、依赖及评分资产与已获取的官方比赛分支 `dab240063bfcfa7917898dc44da4baadb3747bd0` 对比，无修改。

## 本轮重点与独立审查

来源生命周期已补充中断后重启的停用/恢复、成功事件重放不增修订、注册失败重试、严格字段和 scope 隔离测试。独立审查发现两项 Important 问题，均先复现失败再修复：

1. 旧正文引用虽仍可审计，但已不是当前正文时，注册原来会先持久化再失败，永久占用节点编号。现在在写入前拒绝这种绑定。正文版本仍相同的历史修订引用可正常绑定。
2. 生命周期 reason 没有题面长度上限，原生 Memory 审计 reason 上限为 512 字符。现在完整事件照常持久化并参与重放身份比较，传给原生写入的审计摘要先规范化再截至其上限。

修复后的生命周期相关独立套件 87 passed、13 skipped；整合后又通过上面的 95 项公开和 251 项相关回归。

证据选择先观察到缺少接口的失败，再实现 strict 默认关闭开关、不可变片段结果、基于查询和词项稀有程度的句段选择、相邻区间合并、长句中的原文窗口和逐次完整输出计费。原文、坐标、scope、引用及 origins 一致。独立审查没有 Critical/Important 问题；审查者另跑了 96 项相关测试、48 组 Unicode/预算/空输入和区间合并排列检查。

## 必须保留的限制

- 公开测试通过不等于正式评分通过。**尚未正式提测、没有平台分数；评测平台读取私有仓库的权限也未确认。**
- 证据选择尚未测量隐藏 SciFact 的 48 请求质量门槛：平均 evidence token recall ≥0.65、完整证据覆盖请求 ≥40%。当前是离线词项算法，不声称已经达标，不读取评测标注或按题目 ID 写答案。
- PDF、重排、混合检索的完整隐藏质量/延迟门槛，以及官方完整增量序列，未取得平台验证。
- 固定比赛依赖不是全仓开发依赖。全仓 pytest 曾有 110 个可选依赖收集错误；本轮两个服务测试文件也因缺少 `platformdirs` 无法收集。不能声称全仓测试通过。不要为此擅改固定比赛依赖。
- 新增生命周期、证据选择源码的 Ruff/类型检查通过。对大文件整体检查时，原有 AsyncIterator 弃用诊断及既有 datetime.max 诊断须单独记录，不能掩盖成全仓质量检查通过。
- **预算探针问题已修复**：四档预算测试先失败后通过；证据 probe 复用实际输出路径。相关证据、普通上下文、召回与增量套件153项通过，修改经独立审查，随后完整95项公开及251项回归通过。详见 AWARD_REVIEW.md。
- **非阻塞接口缺口**：HTTP/client 生成的 PrepareContextRequest 尚无该开关，本题实现按 Python runtime/builder 接口交付。扩展 HTTP 时应改 OpenAPI 源契约再生成，不能手改生成代码。
- 生命周期 Topic 过滤发生在通道候选取回之后、融合之前。题面四个 Topic 规模已验证；不承诺大量停用 Topic 下的候选不饥饿。并发写者、绑定后外部改正文及同一原生引用的多节点别名语义未扩展。
- seekdb 内核赛题和其余需要特定平台/硬件的生态题，不能视为本文件中已完成。原电脑的数据库/遥测工作保留原侧，不是两位队友的前置依赖。

## 在另一台电脑复现

私有仓库需要当前使用者的 GitHub 账号有读权限。不要把密码、模型 Token 或仓库读取凭据写进代码、URL、交接文件或截图。

在 Linux x86_64 原生文件系统建立环境，使用 Python 3.12 和官方固定依赖。Windows 用户可使用自己的 Linux/WSL/云环境；不要在 `/mnt/c` 内运行原生 worker 计时测试。

```bash
git clone https://github.com/Icsya05/powercontext.git
cd powercontext
git checkout 39a12dbf95da799c7160bb9a7528cbc944215a47
make -C competition install
make -C competition check-baseline
make -C competition test-csv test-pi test-rerank test-embedding test-incremental test-pdf test-count-trigger test-hybrid test-evidence test-lifecycle
```

执行前阅读 `AGENTS.md`、`REVIEW.md` 和 `competition/README.md`。若要继续改代码，从上述 commit 或最新集成分支新建自己的分支，先读取最新交接；不要在 detached HEAD 直接长期工作。

## 后续优先顺序与三方分工

1. 有本人授权登录及合规权限的环境里，按官方提测指南确认私有仓库可读，提交完整代码 SHA，保存真实平台反馈。没有成功记录就标为未提交；不将准备好的材料当作成绩。
2. 根据真实反馈修复失败，优先验证证据选择隐藏质量及检索/PDF质量；单独开发 probe 对齐和 HTTP 契约扩展时补相应回归，不误改评分资产。
3. wyd 负责 `gaode/` 与 `modelscope/`，分支 `ecosystem/wyd-gaode-modelscope`；zyj 负责 `dify/` 与自己部署的 seekdb，分支 `ecosystem/zyj-dify`。两人互不等待，不改核心代码或对方目录。详见各自 TEAMMATE handoff。
4. 主 AI 维护核心集成。正式提交前核对最终 commit 与所需赛题，平台反馈和后续新代码单独留记录。

官方入口：

- [赛题总览](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/ocqe6xv6mlgapq24)
- [提测指南](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/ut82q2fcalep4y1r)
- [平台](https://open.oceanbase.com/train/detail/21)

初赛已知截止为北京时间 2026-11-18 24:00；接手时核对平台最新公告。本文件不含账号凭据。
