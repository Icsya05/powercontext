fork相关仓库，切换到对应分支(vldb_2026)，提交代码给官方仓库，通过github action跑分。

| 项目 | 代码仓库 | 分支 |
| --- | --- | --- |
| powermem | [https://github.com/oceanbase/powermem](https://github.com/oceanbase/powermem) | vldb_2026 |
| seekdb | [https://github.com/oceanbase/seekdb](https://github.com/oceanbase/seekdb) | vldb_2026 |

**注意fork指定分支！**

PR 创建好后，可以在统计文档中进行更新，我会用脚本统计大家的成绩

[https://oceanbase.yuque.com/g/org-wiki-obtech-vh7w9r/hc3pio/snoeve4gf18ksg85/collaborator/join?token=5S8Mmaa7BtSwfRBA&source=doc_collaborator#](https://oceanbase.yuque.com/g/org-wiki-obtech-vh7w9r/hc3pio/snoeve4gf18ksg85/collaborator/join?token=5S8Mmaa7BtSwfRBA&source=doc_collaborator#) 邀请你共同编辑表格《队伍与PR统计》

## 算分原则
### 技术测评部分
总分100分，每个题目25分。

每个小题的满分也按照100分算，会按照0.25系数折算到总分中。

| 题目 | 规则 |
| --- | --- |
| PowerMem 的 LangChain 中间件集成 | Public import contract: PASS (gate)<br/>Retrieve memory before model call: PASS (35/35)<br/>Persist interaction after agent run: PASS (25/25)<br/>Disable interaction persistence: PASS (10/10)<br/>Fail-open on search error: PASS (15/15)<br/>Async memory injection: PASS (15/15) |
| Document AI | load file: PASS (50/50)<br/>split document: PASS (50/50) |
| IK 分词器支持用户自定义词典 | load and use custom IK dictionary: PASS (100/100) |
| 全文索引优化 | large fts benchmark 跑分，benchmark脚本详看全文索引优化文档<br/>1. 加权综合后从基线提升50%即为满分<br/>2. 提升0%以下都为0分<br/>3. 会有一定的不稳定，误差在2分左右 |

### 答辩评审
每个人10分，暂时是五位评委，最后所有评委加权总分到100分

具体评委的细分考量点可以参考技术部分的规则设计

### 最终得分
技术测评部分*60% + 答辩评审部分*40%

最终结果会放到英雄榜中：[https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/zf62cru5n8k2qkg1](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/zf62cru5n8k2qkg1)

## 注意事项
1. seekdb编译资源稍重，大量并发任务会排队，请耐心等待
2. 只选取最后一次的提交结果
3. 一个队伍只有一个PR进行统计
4. 周六下午4点截止提交代码
5. 不允许修改测试文件。如果测试文件有问题请反馈
6. checkout有时候会因为代理不是很稳定，重试一次就好了

## 英雄榜
因为语雀开启token让代码自动上传还需要开会员，所以我们每天更新一次

队伍与PR统计：[https://oceanbase.yuque.com/g/org-wiki-obtech-vh7w9r/hc3pio/snoeve4gf18ksg85/collaborator/join?token=5S8Mmaa7BtSwfRBA&source=doc_collaborator#](https://oceanbase.yuque.com/g/org-wiki-obtech-vh7w9r/hc3pio/snoeve4gf18ksg85/collaborator/join?token=5S8Mmaa7BtSwfRBA&source=doc_collaborator#) 邀请你共同编辑表格《队伍与PR统计》

榜单：[https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/zf62cru5n8k2qkg1](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/zf62cru5n8k2qkg1)
