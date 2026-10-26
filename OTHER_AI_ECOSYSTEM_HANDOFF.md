# 两位队友并行任务总说明

原来分给另一台电脑 AI 的生态任务，现拆成两份独立任务。将对应文件单独发给对应队友或他的 AI 即可，每份都有官方入口、开始命令、现状、步骤和完成标准。

| 人员 | 任务 | 独立交接文件 |
| --- | --- | --- |
| wyd | 高德 Skill、魔搭发布与链接提交 | [wyd 的完整说明](TEAMMATE_WYD_HANDOFF.md) |
| zyj | 独立 Dify 作品、seekdb 服务与真实验证 | [zyj 的完整说明](TEAMMATE_ZYJ_HANDOFF.md) |
| 主 AI | PowerContext 核心代码和整合 | 继续原核心分支；本次只更新交接文档 |

wyd 使用 `ecosystem/wyd-gaode-modelscope`，只改 `gaode/`、`modelscope/`；zyj 使用 `ecosystem/zyj-dify`，只改 `dify/`。两者都从 `competition/nearby-skill` 开始，各自推送，不直接推 master。最终合并由团队统一处理。

两人现在就能同时开工。zyj 使用自己部署的 seekdb，不等高德、魔搭或核心产品整合；两人均不依赖原电脑的 WSL 和数据库。账号与模型服务需在各自环境正常授权。本轮仅拆分交接，不表示任何作品已经提交或取得比赛成绩。

Dify 涉及部署、服务和集成，工作量通常比单文件 Skill 大；wyd 完成前两项后可先交付，由团队再决定是否协助 zyj。协助时仍只由 zyj 维护 Dify 主分支，避免同时改同一文件。
