# 生态分工检查点（2026-10-27）

核心代码与生态分支独立。当前核心已验证代码为448f5d0e；下面分支已从GitHub读取，尚未合流或正式提测。后续接手者先读各分支最新README和validation记录，不仅看较早HANDOFF的“未执行”表格。

| 负责人 | 远端分支与完整SHA | 实际证据与剩余项 |
| --- | --- | --- |
| wyd | ecosystem/wyd-gaode-modelscope @ 46d2d9cc825c152e661606c50636a0fc31e87223 | 高德Skill与离线7场景材料已在仓库；仍无真实高德MCP/平台成绩。魔搭作品已公开，本轮重新匿名clone并确认仓库只有SKILL.md，与该分支内容按LF规范化后逐字一致。仍无大赛提测记录。 |
| zyj | ecosystem/zyj-dify @ 454a2b70fd2782c43596958872a7dd5f516c8a9f | 已读到真实seekdb服务10项通过、Dify DSL导入/导出/重新导入7项通过的日志；这些是队友提交的证据，本轮未重新运行其环境。尚未找到绑定真实模型后完整NPC工作流多轮运行的成功报告，不能把DSL往返当成LLM端到端验收。 |

魔搭作品：https://modelscope.cn/skills/BadFallen/nearby-walk-recommendations 。公开Git提交38f7a60bd7b435d059c49c01a03f61d4c2f86a1e，规范化内容SHA256：62d2022e533b1e9f259e7ff40aef9ac998c7a234b54ea00e80327be1ab2fdf05。

两个分支相对competition/nearby-skill的文件变化分别仅在gaode/modelscope和dify目录，符合分工。合流前仍需审查Dify运行配置、模型连通性、演示证据及官方生态交付要求。本轮保留两个分支的原提交和目录归属，没有直接修改队友文件或向其他聊天发送消息。

状态文档有陈旧段落：魔搭README开头仍写“尚未上传”，与其后已发布证据矛盾；Dify较早HANDOFF仍列数据库和DSL未执行，但后续validation已有成功记录。接手时应以具体时间、完整提交和验证原始记录核对，不把这些旧文字当成当前事实。

比赛平台读取私有仓库的权限、提交入口记录与正式成绩仍未验证；GitHub连接可读取仓库和公开作品可clone，均不等于平台已接收作品。
