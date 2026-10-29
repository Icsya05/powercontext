| 项目 | 说明 |
| --- | --- |
| 项目 | seekdb |
| 总分 | 10 分 |
| 任务 | 部署并启动一个 seekdb 实例，部署平台不限 |
| 提交产物 | 自己部署的 seekdb 实例的遥测 ID |

## 一、题目背景
本题通过一次部署实践，帮助参赛者熟悉 seekdb 的运行方式。参赛者需要部署并启动一个 seekdb 实例，获取该实例的遥测 ID，并将 ID 提交到大赛提测平台。

**部署平台不限。** 可以使用自己的服务器、云服务器或满足 seekdb 运行要求的本地开发环境。

如果你没有可用的服务器，可以参考[AMD Radeon使用和部署seekdb](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/lcuknwgl955v8ou7) ，尝试申请 AMD 平台的资源服务器，并按照文档完成部署。AMD 是可选的资源获取方式，不作为参赛或得分的必要条件；若平台暂时无法连接或资源紧张，可使用其他环境完成本题。

## 二、题目内容
### 2.1 部署并启动 seekdb
1. 准备满足 seekdb 运行要求的服务器或本地开发环境。
2. 按 seekdb 部署说明完成安装和配置，启动实例。
3. 确认实例正常运行，能够连接并执行 SQL 查询；建议保存部署成功截图，便于后续核对。

选择 AMD 平台的参赛者，可按照上述分享中的账号注册、资源申请、实验环境启动和 Notebook 操作步骤完成部署。本题仅要求成功部署 seekdb，不要求使用 GPU 加速或完成 hipVS 实验。

### 2.2 获取自己实例的遥测 ID
部署成功后，在 **seekdb 运行目录**下找到 `run/telemetry.json`。打开文件，读取其中 `content.id` 的值，该值即本次部署的遥测 ID（UUID）。

例如，文件结构如下：

```json
{
  "content": {
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

上面的字符串仅为格式示意。**请复制自己部署实例的 **`content.id`**，保留完整内容及其中的连字符。**

也可以在 seekdb 运行目录执行以下命令，直接输出遥测 ID：

```bash
python3 -c 'import json; print(json.load(open("run/telemetry.json"))["content"]["id"])'
```

如果找不到文件，先确认 seekdb 已成功启动，并检查当前所在路径是否为该实例的运行目录。

## 三、提交方式
1. 登录大赛提测平台，进入**赛题一**的提交入口。
2. 将获取到的**遥测 ID**填入对应字段并提交。
3. 核对提交内容与自己实例的 `content.id` 一致。

提交的是 **ID 字符串本身**，不是整个 `telemetry.json` 文件、文件路径、AMD 账号或算力券码。

完整流程为：**选择部署环境 → 部署并启动 seekdb → 获取自己的遥测 ID → 将 ID 提交到提测平台**。

## 四、提交前检查
| 检查项 | 要求 |
| --- | --- |
| 部署环境 | 使用满足 seekdb 运行要求的环境，平台不限 |
| 启动状态 | seekdb 已成功启动，能够连接并执行 SQL 查询 |
| 遥测 ID | 来自自己部署实例的 `run/telemetry.json` 中的 `content.id` |
| 平台提交 | 已将完整遥测 ID 提交至提测平台的赛题一入口 |

若使用 AMD 平台，完成实验并保存遥测 ID 和部署记录后，可按照 AMD 分享中的步骤，在 **Active Instance → Destroy** 释放实验环境，避免持续消耗算力额度。
