**📣****欢迎选择 OceanBase 数据库大赛 AMD 赛题！你需要的免费 GPU 算力资源来了！**

## 一、注册并申领算力
AMD 提供免费 Radeon Cloud GPU 算力，支持大家完成模型推理、项目开发与作品验证。请按以下步骤即可申请。

### **如何领取**
1️⃣ 注册 AMD 开发者计划（ADP）；
2️⃣ 登录 Radeon Cloud，完成平台验证；
3️⃣ 根据下方时段规则使用算力：热门时段等待批次分配通知，非热门时段直接使用空闲 GPU；
4️⃣ 收到分配通知后，在指定窗口登录 Radeon Cloud，查看算力额度（Credits）并使用 GPU。

📌 按个人账户领取，每位队员都需独立注册、验证和登记，全员注册完成后，额度发放至个人账户。

### **算力如何分配**
☀️ **热门时段：07:00–23:00**

• 每48小时开启一轮分配，每轮最多500人，人数根据实际 GPU 利用率动态调整。
• GPU 释放后，按等候名单顺序分配；进入本轮名单不代表立即获得 GPU。
• 同队成员安排在同一使用窗口，资源仍按个人账户分配。
• **每人同时最多使用1张 GPU，单次实例最长运行4小时，超时自动回收。**

本轮使用结束或错过窗口后，如仍需算力，请按通知参加下一轮排队。

🌙 **非热门时段：23:00–次日07:00**

完成 ADP 注册及 Radeon Cloud 验证后，**无需排队，空闲 GPU 先到先得**。可用资源以平台实际情况为准，欢迎利用夜间时段减少等待。

### **通知与使用提醒**
🔔 轮次、批次名单及预计开放、结束时间将通过群公告和 @所有人通知同步；获得资源后会另行通知。

⚠️ 48小时是本轮分配与使用窗口，不是连续占用时长。请提前准备代码、数据和运行步骤，在实例回收前保存成果；任务完成后及时释放资源。

📝 赛题计分与算力领取分别管理。请按赛事要求完成 AMD 赛题及提交，算力领取次数不等于赛题计分次数。

### **资料入口**
▪ AMD 开发者计划注册
[https://developer.amd.com.cn/login?source=0u9Eqno7R](https://developer.amd.com.cn/login?source=0u9Eqno7R)

▪ Radeon Cloud 平台及验证指引
[What is AMD Radeon Cloud | Radeon Cloud Docs](https://amd-aim.github.io/radeon-cloud-docs/introduction/)

▪ OceanBase 大赛 AMD 赛题及实践指南
[https://open.oceanbase.com/competition](https://open.oceanbase.com/competition)

### **遇到问题**
请扫描下方二维码进入AMD赛道专属答疑群，在群内提供：**队伍名称＋问题环节＋报错信息或截图**，若遇到入群失败等问题可在此艾特“AMD开发者小助手”，我们会协助跟进。

请勿发送密码、API Key、SSH 私钥等敏感信息。报名、组队、计分及作品提交问题，请按 OceanBase 赛事平台指引处理。

先领取免费算力，一起跑通 AMD 赛题，让你的创意和思考起飞！🚀

## 二、注册并兑换算力
### 1. 注册 AMD 开发者账号
打开 [AMD 开发者平台](https://developer.amd.com.cn/login?source=0u9Eqno7R)，首次使用先注册，再登录。验证码有效时间较短，建议先填好其他信息，再发送验证码；密码按页面要求设置。

![AMD 开发者平台注册与登录入口](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983212063-582107f7-c310-43a6-9785-35a2259f722c.png)

### 2. 兑换算力券
登录后，在首页点击“积分免费兑换”，进入权益页面领取算力额度。

![首页的积分免费兑换入口](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983211850-6a5e57eb-c9dc-4014-88d0-13a51b0dd01b.png)

选择兑换小时数，点击“立即兑换”。原手册说明每账号每日最多兑换 20 小时，具体可兑换额度以页面显示为准。

![选择算力券兑换小时数](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983211433-771a635f-39e0-4853-9491-48531751fab8.png)

兑换完成后，在兑换记录中点击“查看云算力券”，再点击“复制链接”，供下一步兑换使用。

![兑换记录中的查看云算力券入口](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983211543-607f5252-bb0f-43fa-917c-c57b87d93525.png)

### 3. 将算力券兑换到 Radeon Cloud
返回首页，点击“AMD 开发者云”，按提示使用 GitHub 或魔搭账号登录。

![进入 AMD 开发者云](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983211820-33d69ce9-4ad3-4367-b487-e1dff8988b77.png)

打开右上角用户名下的 **Profile**，点击 **Redeem Credits**；在弹出的 **Coupon Code** 输入框中粘贴刚复制的内容，再点击 **Redeem**。看到兑换成功提示后，确认可用额度已增加。

![Profile 页面中的 Redeem Credits 入口](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983213348-42a61c5e-c876-4ed0-b02d-6bdfd69e4b1d.png)

## 三、启动 seekdb 并完成实验
### 1. 创建实验环境
进入 **Gallery**，搜索 `seekdb`，找到 **seekdb-hipvs**，点击 **Launch**。该模板包含 seekdb、hipVS 预编译库和测试样例。

![搜索 seekdb 并启动 seekdb-hipvs 模板](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983213513-eb718ddd-79c2-44a8-a52a-6a550589ce41.png)

等待工作空间初始化。显示 **Your workspace is ready** 后，点击 **Open Notebook** 进入实验。

![工作空间准备完成后打开 Notebook](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983213888-aa4b10aa-b7f7-40d0-af53-6693349fd74b.png)

### 2. 按顺序执行 Notebook
阅读每段说明，依次选中代码单元并点击执行按钮，在单元下方查看结果。按 Notebook 顺序完成环境检查、启动数据库和后续数据实验。

![依次选择并执行 Notebook 代码单元](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983213825-e5f794c7-d13d-4bf9-b26b-604f42266845.png)

先运行环境与硬件自检，检查 AMD GPU、ROCm、seekdb 二进制及相关库是否正常。

![环境与硬件自检结果](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983214212-1d9825d7-5def-4e02-bb74-5e61585190bd.png)

继续执行启动 seekdb 的单元，确认输出 `observer ready` 和 seekdb 版本信息。**保存部署成功的结果截图**，后续登记会用到。

![seekdb 启动成功与版本信息](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983215142-18ea319b-69f3-49a2-b878-af26669cc27a.png)

## 四、保存部署 UUID 并释放实例
### 1. 保存部署信息
在 **seekdb 运行目录**下找到 `run/telemetry.json`，打开文件，复制 `content.id` 的值，即本次部署的 UUID，同时保存截图。

例如，文件中出现 `"content": {"id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", ...}`，应登记 `id` 对应的完整字符串。请填写自己实例的值。

领取考券前，准备好：

+ seekdb 部署成功截图。
+ 部署 UUID 及对应截图。
+ OBCA 课程学习完成截图。

### 2. 释放实验环境
**先保存好截图和 UUID，再到 Profile 的 Active Instance 中点击 Destroy，释放实例，避免持续消耗算力额度。**

下图是释放完成后的状态，显示 **No Active Instance**。

![释放实例后的 No Active Instance 状态](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792983215205-570efa6c-9e56-44db-b54f-069def35a893.png)
