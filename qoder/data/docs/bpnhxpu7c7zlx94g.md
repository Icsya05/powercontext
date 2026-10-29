## 背景与目标
大模型让应用具备了理解、生成和推理能力，但要让 AI Agent 真正进入生产系统，仅有模型本身还不够。真实系统需要记住长期上下文，理解业务数据，把模型能力纳入数据处理流程，并且在数据规模增长时依然保持稳定、高效、可治理。这背后对应的是一整条从应用框架到数据库内核的工程链路。

本次实训围绕 PowerMem 与 seekdb 设计，选取了四个具有代表性的切入点：通过 PowerMem 适配 LangChain，让 Agent 在多轮任务中持续利用长期记忆；通过 Document AI Function，让数据库能够在 SQL 流程中调用模型完成文档理解、摘要和抽取；通过自定义分词词典，让全文检索能够更准确地理解领域词和业务术语；通过全文索引构建性能优化，让检索能力在更大数据量和更真实的工程压力下依然跑得动。

这些题目不是彼此孤立的功能点，而是一条完整的 AI 数据系统落地路径：从“记得住”到“会用模型”，从“搜得准”到“跑得动”。希望同学们在完成实训的过程中，不只是熟悉某个模块的代码修改，更能理解 AI 能力进入数据库系统时必须面对的核心问题：状态如何沉淀，语义如何进入查询，领域知识如何影响检索质量，以及系统性能如何支撑真实应用。

## 实训营相关
| PowerMem 的 LangChain 中间件集成 | [https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/smpp9wl8trfkeev1](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/smpp9wl8trfkeev1) |
| --- | --- |
| Document AI | [https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/gp6voyg9r0qqbt95](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/gp6voyg9r0qqbt95) |
| IK 分词器支持用户自定义词典 | [https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/iq4su2iqyuzen05i](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/iq4su2iqyuzen05i) |
| 全文索引优化 | [https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qpbdgg2geoh5zoyx](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qpbdgg2geoh5zoyx) |
| 测试跑分 | [https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/yt95uatolcbtfgow](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/yt95uatolcbtfgow) |
