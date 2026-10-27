# 本机部署指南：Docker Desktop + Dify + MiniMax 模型

给「第一次装、不知道从哪下手」的人写的。照着做，每一步都有「怎么确认这步成功了」。

---

## 第 0 步：确认一下你现在在哪

按 `Win + X` → 弹出菜单里选 **终端(管理员)** 或 **Windows PowerShell(管理员)**。
标题栏必须带「管理员」三个字。如果弹出来的窗口没有管理员权限，右键菜单里的
「终端(管理员)」再点一次，UAC 弹窗点「是」。

下面所有命令都在这个窗口里执行。

---

## 第 1 步：开启 WSL2 和虚拟机平台

Docker Desktop 在 Windows 上需要一个 Linux 内核层（WSL2）。先把它装上。

**复制这一行，粘贴到管理员 PowerShell，回车：**

```powershell
wsl --install --no-distribution
```

它会自动下载并启用两个 Windows 功能：`Microsoft-Windows-Subsystem-Linux` 和
`VirtualMachinePlatform`。

**看到命令执行结束后，屏幕上会提示需要重启。直接重启电脑。**

```powershell
# 重启后可以再确认一次（可选）
wsl --status
```

> 如果这一步报错 `需要管理员权限` 或者 `0x80072ee7` 之类的，把完整报错发我。

### 第 1.5 步（只有报错时才需要）：补 WSL2 内核

如果第 1 步之后 Docker 启动时报 **"WSL 2 installation is incomplete"** 或
**"WSL2 requires a kernel update"**，执行：

```powershell
wsl --update
```

然后如果还不行，手动装内核更新包：

1. 打开 https://github.com/microsoft/WSL2-Linux-Kernel/releases
2. 下载 `wsl_update_x64.msi`
3. 双击安装 → 一路 Next
4. **重启电脑**

---

## 第 2 步：安装 Docker Desktop

**方式 A（推荐，一条命令）**：在管理员 PowerShell 里粘贴：

```powershell
winget install -e --id Docker.DockerDesktop
```

**方式 B（手动）**：浏览器打开
<https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe>
下载 `Docker Desktop Installer.exe`，双击运行。

安装过程中的选项：

| 界面选项 | 怎么选 |
| --- | --- |
| 安装位置 | 默认即可（别装 C 盘最好，但 D 盘也可以） |
| 勾选项 | 保持默认勾选即可 |
| UAC 弹窗 | 点「是」 |
| 安装完成 | 点「Close」 |

> ⚠️ 如果提示 **"requires Windows 11 Pro / Enterprise"**，说明它想用 Hyper-V 后端。
> 家庭版请在首次启动 Docker Desktop 时选择 **Use WSL 2 instead of Hyper-V**。

---

## 第 3 步：首次启动 Docker Desktop

1. 从「开始」菜单打开 **Docker Desktop**
2. 弹出协议 → 勾选同意 → **Accept**
3. 提示「Sign out」/「需要注销」→ 按提示注销或重启（某些版本会要求）
4. 等待 Docker Desktop 主界面加载完，左下角状态变成绿色的 **Engine running**

> 首次启动可能显示一个调查问卷，随便跳过即可。

---

## 第 4 步：验证成功（这一步通过就说明环境完全 OK）

在 PowerShell 里（**不需要管理员**）执行：

```powershell
docker version
```

期望输出里同时有 **Client** 和 **Server** 两段，且 Server 那段有版本号。

再执行一次：

```powershell
docker run --rm hello-world
```

期望看到 `Hello from Docker!`。

**这两条都通过 = 完成。** 之后把结果告诉我一声，或者直接回来说「好了」。

---

## 第 5 步：起 Dify（这一步交给我）

Docker 一到位，剩下的我来跑：

```powershell
# 起 seekdb + 记忆服务
docker compose -f dify/deploy/docker-compose.yml --env-file dify/.env up -d

# 建表 + 建中文全文索引
python dify/deploy/init_db.py --env dify/.env

# 起 Dify 1.17.1（会自动写好 SSRF 放行和 SECRET_KEY）
python dify/deploy/start_dify.py --dify-src D:\ZhuYijing\Documents\minimax工作文件夹\dify-src
```

---

## 第 6 步：在 Dify 里配 MiniMax 模型（需要你点几下）

Docker 起来、我在跑上面命令的时候，你可以在浏览器里做这个。

### 6.1 建管理员账号

浏览器打开 <http://localhost/install>

- 设置邮箱、密码 → 创建 → 会自动登录进控制台

### 6.2 安装 OpenAI-API-Compatible 插件

1. 左边菜单点 **设置**（Settings）
2. 顶部找到 **模型供应商**（Model Provider）
3. 搜索框输入 `OpenAI-API-compatible`
4. 点它右边的 **安装**（Install）

> 如果搜不到，就搜 `openai`，找到官方 OpenAI 插件也行——MiniMax 有 OpenAI 兼容接口。

### 6.3 填 MiniMax 的接口信息

在同一个 **模型供应商** 页面，找到刚装好的 **OpenAI-API-compatible**，点它右边的
**设置**（齿轮 / Configure），填三项：

| 字段 | 填什么 |
| --- | --- |
| **API Key** | 你的 MiniMax 接口密钥 |
| **API Endpoint URL** | 你的 MiniMax 账号对应的 OpenAI 兼容地址 |
| **Model Name** | 你账号里可用的模型名 |

> **API 地址和模型名去哪看**：登录 MiniMax 开放平台 → 右上角「账户管理 / 接口密钥」，
> 页面里会直接显示你的 **API 地址** 和可用**模型列表**。常见的两个：
> - 国内站：`https://api.minimaxi.com/v1`
> - 国际站：`https://api.minimax.io/v1`
>
> 以你自己控制台里显示的为准，**不要照抄我这里的猜测值**。

填完点 **保存**。

### 6.4 顺手验证一下模型能不能用

在「模型供应商」页面，把鼠标移到刚配好的模型上，右边会出现 **试运行 / Test** 之类的
按钮（有的版本是「调参数」旁的闪电图标）。点一下，发一句话，能返回内容就说明配好了。

---

## 第 7 步：交给我

上面 6.3 配完、6.4 验证通过后，告诉我一句「模型配好了」，我接着做：

1. 导入 `dify/workflow.yml` 到 Dify，把「阿澈回应」节点的模型换成你配好的那个
2. 跑 7 个验证样例（首次到店 / 跨会话恢复 / 全文检索召回 / 玩家隔离 / 重置 / 数据库故障 / 非法卡号）
3. 从 Dify 导出 DSL → 在一个干净的新应用里重新导入 → 再跑一遍
4. 把真实运行记录、数据库行、截图写进 `dify/validation/`
5. 用真导出的 DSL 替换交付用的 `dify/workflow.yml`，提交并推送

---

## 出问题怎么办

| 现象 | 处理 |
| --- | --- |
| `wsl --install` 报 0x800f0954 之类的 | 系统的虚拟化没开。重启进 BIOS 打开 `Intel VT-x` / `AMD SVM`，或看第 1.5 步 |
| Docker Desktop 提示需要 WSL2 | 回第 1 步，确认重启过 |
| Docker Desktop 提示要注销 | 注销一次登录即可 |
| `docker version` 只有 Client 没有 Server | Docker Desktop 引擎没起来，看主界面左下角是不是绿色 |
| `docker run` 卡在拉镜像 | 网络问题。Docker Desktop 里 **Settings → Resources → Proxies** 里确认代理；必要时在 Settings → Docker Engine 里加 registry mirror |
| Dify 页面打不开 | `docker compose ps` 看容器状态，`docker compose logs api` 看报错 |
| HTTP 节点报 `blocked by SSRF protection` | Dify 的 `docker/.env` 里要有 `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=host.docker.internal`，我会在起 Dify 前写好 |
