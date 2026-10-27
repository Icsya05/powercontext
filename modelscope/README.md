# 魔搭社区（ModelScope）发布记录

对应赛题：**上传并分享自己的 Skill**（总分 20），提交产物为该 Skill 在魔搭的**网址或编号**——个人主页、账号 ID、Skill 名称都不算。

本目录保存发布材料与状态。**作品尚未上传**，原因见文末「卡点」。

## 作品信息

| 项目 | 内容 |
| --- | --- |
| 作品名称（Skill name） | `nearby-walk-recommendations` |
| 显示名 | 周边去哪儿 |
| 作品网址 | ✅ `https://modelscope.cn/skills/BadFallen/nearby-walk-recommendations`（⚠️ **不带 `@`**，带 `@` 会 404） |
| 作品编号 | ✅ `BadFallen/nearby-walk-recommendations` |
| 来源仓库 | `https://github.com/Icsya05/powercontext`（私有），分支 `ecosystem/wyd-gaode-modelscope`，路径 `gaode/SKILL.md` |
| 许可 | Apache-2.0 |
| 分类（category） | `other` |
| 公开文件范围 | **仅 `SKILL.md` 一个文件**。不含评测数据、不含仓库其他代码、不含任何凭据 |
| 状态 | ✅ 已准备 / ✅ 已上传（2026-10-27，公开接口核验通过）/ ⬜ 已提测 |

## 上传结果（2026-10-27 核验）

用魔搭公开读接口 `GET /openapi/v1/skills/BadFallen/nearby-walk-recommendations` 回查：

| 字段 | 返回值 |
| --- | --- |
| id | `BadFallen/nearby-walk-recommendations` |
| display_name | 周边去哪儿 |
| category / license | `other` / `Apache-2.0` |
| private | `false`（公开可见） |
| source_url | `https://github.com/Icsya05/powercontext` |
| tags | `custom_tag:gaode`、`amap`、`walking-distance`、`poi-search`、`travel` |
| 作品页 HTTP 状态 | 200（`modelscope.cn` 与 `www.modelscope.cn` 均可） |
| 安装命令（平台生成） | `npx skills add https://modelscope.cn/skills/BadFallen/nearby-walk-recommendations` |

## 二次核验（2026-10-27，补做）

首次核验用“HTTP 200”判断页面可访问，这个方法**不可靠**：魔搭是单页应用，不存在的路径同样返回 200（实测
`/skills/this-skill-does-not-exist-xyz` 也是 200）。改用下面三项才算确证：

| 检查 | 方法 | 结果 |
| --- | --- | --- |
| 内容真的进了仓库 | `git clone https://modelscope.cn/skills/BadFallen/nearby-walk-recommendations.git` | 有提交 `Init Skill`，仓库内**只有** `SKILL.md` |
| 页面真的渲染出来 | 抓 HTML 看 `<title>` 与正文关键词 | `<title>Skill 详情 - 其他 - nearby-walk-recommendations</title>`，含“周边去哪儿”，14.8 KB |
| URL 写法 | 对比带 `@` 与不带 `@` | **不带 `@` 正确**；带 `@` 只返回 5 KB 空壳（`<title>ModelScope 魔搭社区</title>`），表现为 404 |

仓库里的 `SKILL.md` 是 7713 字节，本地是 7648 字节：差值 65 正好等于行数减一，是平台把 LF 换成 CRLF 导致的，
内容一致，不是上传损坏。

**仍待人工确认**：页面正文里 `SKILL.md` 的各小节是否完整显示（接口与 HTML 只能确认标题与摘要级信息）。

## 与高德赛题是同一份文件

魔搭题允许复用自己已写的 Skill。这里直接使用 `gaode/SKILL.md`，**同一份文件、内容完全一致**，避免两处维护出现差异。

重新打包（每次改完 `gaode/SKILL.md` 都要重打）：

```bash
cd gaode && zip -j ../modelscope/nearby-walk-recommendations.zip SKILL.md
```

⚠️ 魔搭要求：**zip 根目录必须只有 1 个 `SKILL.md`，不能带其他文件**（`docs`/`README`/子目录都不行）。所以这里用 `-j` 只装文件本身，不带 `gaode/` 目录层。整个包需 ≤ 5 MB（本包约 8 KB）。

## 上传方式

### 方式一：网页（最直观）

1. 登录 <https://www.modelscope.cn>。
2. 进入 Skills 页面，选择创建 / 上传 Skill。
3. 上传上面那个 zip，填写显示名、描述、分类、许可、来源 URL。
4. 上传后**重新打开作品页**，确认能看到 SKILL.md 内容，再复制完整网址。

### 方式二：OpenAPI（不需要浏览器，本机已验证 `modelscope.cn` 可达）

两步：先传 zip 拿到文件 id，再用它创建 Skill。

```bash
export MODELSCOPE_API_KEY=<你自己的 API Key>   # 在 魔搭 → 我的 → API-KEY 创建
python modelscope/publish_skill.py --owner <你的用户名>
```

脚本会依次完成：打包 → 上传 → 创建 → 回查确认 → 打印作品网址。加 `--dry-run` 只打包不上传。

也可以手写 HTTP：

```bash
# 第 1 步：上传 zip，取返回的 data.id（注意键名是 id，不是 file_id）
curl -X POST "https://modelscope.cn/openapi/v1/files/upload" \
  -H "Authorization: Bearer $MODELSCOPE_API_KEY" \
  -F "file=@nearby-walk-recommendations.zip" -F "type=skill"

# 第 2 步：创建 Skill
curl -X POST "https://modelscope.cn/openapi/v1/skills" \
  -H "Authorization: Bearer $MODELSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"owner":"<用户名>","skill_name":"nearby-walk-recommendations",
       "display_name":"周边去哪儿","description":"...","skill_file":"<第1步的id>",
       "category":"other","license":"Apache-2.0"}'
```

`skill_name` 只能用小写字母、数字和连字符，创建后不可改；`owner` 同样不可改。需要改名或换包时用 PATCH `/openapi/v1/skills/{owner}/{skill_name}/settings`，可改 `display_name`、`description`、`skill_file`、`tags`、`source_url`、`category`、`license`。

## 建议填写的描述与标签

描述（1–2 句，说清做什么、什么时候用）：

> 根据用户给出的城市、起点坐标和自然语言需求，调用高德 MCP 的地点搜索与步行路线规划，推荐最多 3 个从同一起点出发的备选地点，给出实测步行距离、耗时和逐条理由；步行时间只用路线规划结果，超时、无结果、路线失败分别如实说明。

标签：`gaode`、`amap`、`walking-distance`、`poi-search`、`travel`、`skill`

使用示例（填在作品说明里）：

> 我在杭州，起点 120.150000,30.270000，想找家咖啡馆，步行不超过 15 分钟，最多 2 家，优先近一点的。

## 提交到大赛平台

上传成功、拿到网址后：

1. 登录 <https://open.oceanbase.com/train/detail/21>，进入魔搭社区赛题入口。
2. 把**作品完整网址**（或编号）填进对应字段并保存。
3. 回读一次已提交内容，确认它指向的是自己的作品，不是个人主页或 Skill 名称。
4. 把网址和提交时间回填到本文件上表。

## 卡点（需要账号本人操作）

| 卡点 | 说明 | 最少操作 |
| --- | --- | --- |
| ~~魔搭账号登录~~ | ✅ 已完成：用账号 `BadFallen` 的写权限令牌，通过 `publish_skill.py` 发布 | 无需操作 |
| ~~可能触发实名/条款~~ | ✅ 未触发 | 无需操作 |
| 大赛平台提交 | 需要登录 open.oceanbase.com 并进入魔搭赛题目录 | 本人提交，作品网址见上表 |
| 页面正文人工确认 | 接口只能确认元数据，`SKILL.md` 正文是否完整显示要人眼看 | 打开作品页看一眼 |

上述凭据**没有**出现在本仓库任何文件中；本文件也不记录 Token 值。
