# HANDOFF：wyd 的高德 Skill 与魔搭发布

更新于 2026-10-26。本文件只记录**已实际完成**的事，不含预测性描述。

## 1. 位置

| 项目 | 值 |
| --- | --- |
| 仓库 | `Icsya05/powercontext`（私有） |
| 分支 | `ecosystem/wyd-gaode-modelscope` |
| 起点提交 | `9ce99250bd92e4dd0aa2d124c0fb649619b4a408`（`competition/nearby-skill`） |
| 本轮内容提交 | `9c82abd4369bc25a006dc6fa5b7810545c7bf250`（14 个文件） |
| 本文件所在提交 | 上述提交的后续提交，见分支 HEAD |
| 文件归属 | 只动 `gaode/`、`modelscope/`，未改 `src/powercontext/`、CI、根文件 |

## 2. 交付物

- `gaode/SKILL.md` —— 高德赛题的唯一提交产物，当前 7648 字节、66 行。
- `gaode/VALIDATION.md` —— 验证记录，含本轮 7 场景离线回归与修正过程。
- `gaode/dev/fixtures.json`、`gaode/dev/score_answer.py`、`gaode/dev/answers/*.md` —— 可复现的回归材料。
- `modelscope/README.md` —— 魔搭发布记录（作品页字段、上传步骤、许可、状态、卡点）。
- `modelscope/publish_skill.py` —— 一条命令完成打包与上传（两步 OpenAPI）。

## 3. 本轮实际做了什么

按官方题面和高德 MCP 的真实工具集核对后，改了 5 处，没有重写原有正确内容：

1. 加工具名对应表（周边检索 / 关键词检索 / 详情 / 地理编码 / 步行路线），步行优先坐标版。
2. 显式禁止用 `maps_distance`（距离测量）和驾车、骑行、公交代替步行路线——它同样返回 `distance`/`duration`，`type` 还能写“步行”，是最容易被误用的工具。
3. 起点只有地标名时先地理编码再继续；坐标与用户所说城市不符时以坐标为准并说明；单轮任务不以反问结束。
4. 候选按搜索远近顺序核实，约 8 个为上限，避免对全部候选无节制查路线。
5. 推荐理由必须含该地点实测数字；距离短不得推断安静、座位或久坐。

## 4. 验证：哪些真实，哪些是模拟

| 项目 | 性质 | 结果 |
| --- | --- | --- |
| skill-creator `quick_validate.py gaode` | 格式检查（真实执行） | `Skill is valid!`，退出码 0 |
| 官方 `2026-competition-ecosystem` 分支核对 | 真实（下载并读取） | `gaode/` 下只有 `.gitkeep`，无模板，格式以题面为准 |
| 高德 MCP 能力与字段核对 | 真实（读取官方 MCP 文档） | 步行路线为经纬度入、`distance` 米 / `duration` 秒；距离测量是独立工具 |
| 7 场景离线回归 | **模拟**：合成工具返回 + 独立上下文 Agent | 首轮 6/7，修正 J 缺陷后 7/7 |
| 真实高德 POI / 步行路线请求 | **未执行** | 本机无高德 Key、未配置 MCP |
| 平台加载 Skill 实际评测 | **未执行** | 未提测 |

本轮发现的真实缺陷：J 场景首轮回答把“步行最短”写成“更适合久坐一下午”，而同一份回答的说明段又写安静与久坐“未核实”，前后矛盾。已在输出节补规则，修正后复测通过。

复现方式（需要 Python 3.10+）：

```bash
cd gaode
python dev/score_answer.py dev/answers/
# 期望：合计 7/7 通过
```

## 5. 上传与提测状态

- 高德题：**未提交**。文件已就绪，未在平台上传。
- 魔搭题：**已上传，未提测**。作品已发布并核验：编号 `BadFallen/nearby-walk-recommendations`，
  网址 <https://modelscope.cn/skills/@BadFallen/nearby-walk-recommendations>（公开可见，页面 200）。
  尚未把该网址提交到大赛的魔搭题入口。
- 无任何平台成绩，不宣称得分。

## 6. 卡点与本人最少操作

| 卡点 | 最少操作 |
| --- | --- |
| 高德题需要登录评测平台上传 `gaode/SKILL.md` | 登录 <https://open.oceanbase.com/train/detail/21>，进入高德题目录，上传该文件并确认提交记录 |
| 魔搭需要本人账号上传 | 二选一：① 网页上传 `modelscope/nearby-walk-recommendations.zip`；② 在魔搭创建 API Key 后执行 `export MODELSCOPE_API_KEY=... ; python modelscope/publish_skill.py --owner <用户名>` |
| 魔搭上传后要把作品网址填进大赛 | 打开作品页确认能看到 SKILL.md，复制完整网址，提交到魔搭题入口，再回填 `modelscope/README.md` 的表格 |
| 首次上传可能触发实名或条款 | 由本人在页面确认 |

凭据未写入任何提交文件。后续更新 Skill 内容时，改用 PATCH `/openapi/v1/skills/{owner}/{skill_name}/settings` 换 `skill_file`（`publish_skill.py` 目前只走创建流程，作品已存在时创建会失败，需按 `modelscope/README.md` 的 PATCH 示例操作）。`skill_name` 与 `owner` 创建后不可改。
