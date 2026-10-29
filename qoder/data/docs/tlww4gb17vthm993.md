## 1. 最小架构图
seekdb 不是由许多独立微服务拼成的数据库。当前源码最终把协议入口、SQL 引擎、事务存储、日志、全文和向量检索等模块链接进同一个 `seekdb` 可执行文件。模块边界很重要，但它们主要是进程内边界。

可以先记住这张最小架构图：

```latex
MySQL 客户端
    │  MySQL Protocol / COM_QUERY
    ▼
observer：进程装配、网络、会话与协议入口
    │
    ├── sql：Parser → Resolver → Rewrite → Optimizer → Codegen → Executor/DAS
    │                                                      │
    ├── rootserver：Schema、DDL、索引构建、Fork 等本地控制面 │
    │                                                      ▼
    ├── pl：PL 与系统包                              storage：事务、LS、Tablet、
    │                                                Memtable、SSTable、Compaction
    └──────────────────────────────┬───────────────────────┘
                                   ▼
                         logservice：PALF、Apply、Replay

                 share / oblib：所有上层共同依赖的基础设施
```

这张图表达的是职责和主要调用方向，不代表任意两个模块之间都没有历史依赖。仓库为依赖关系设置了自动检查，但当前检查范围还不是全部源码。

### 1.1 最终产物
`src/observer/CMakeLists.txt` 中的主目标是：

```cmake
add_executable(seekdb)
```

`seekdb` 会链接 `ob_sql_static`、`ob_storage_static`、`ob_share_static` 等库。兼容目标 `observer` 在 Linux/macOS 上是指向 `seekdb` 的符号链接，在 Windows 上是 `seekdb.exe` 的副本。因此阅读、运行和发布时，应把 `seekdb` 当作主二进制。

这也解释了为什么只看某个目录的接口还不够。一个请求会在同一进程中跨过协议、优化器、执行器、事务存储和日志模块；定位问题时，要沿调用链判断错误发生在哪一层。

---

## 2. 仓库地图
### 2.1 顶层目录
| 目录或文件 | 主要职责 | 新人是否常用 |
| --- | --- | --- |
| `README.md` / `README_CN.md` | 产品能力、快速开始、当前主构建入口 | 必读 |
| `CONTRIBUTING.md` | 当前对外贡献流程 | 必读 |
| `build.sh` / `build.ps1` | Unix 与 Windows 的构建入口 | 必读 |
| `cmake/` | 编译选项、平台适配、打包、模块层次检查 | 构建问题必看 |
| `deps/` | `oblib` 和第三方依赖描述、下载脚本 | 基础设施与依赖问题 |
| `src/` | 数据库核心源码 | 核心 |
| `unittest/` | 按模块组织的 C++ 单元测试 | 修改核心代码必看 |
| `tools/deploy/mysql_test/` | `.test` 输入与 `.result` 预期结果 | SQL 行为修改必看 |
| `tools/deploy/obd.sh` | 本地部署与 mysqltest 封装 | Linux 回归常用 |
| `.github/` | Issue/PR 模板与工作流 | 提 PR 前必看 |
| `docs/developer-guide/` | 构建、调试、规范、测试说明 | 参考，但要与脚本交叉核对 |

一个重要经验是：**脚本和 CMake 比文字文档更接近可执行事实**。仓库部分开发文档从旧版演化而来，后文会明确列出已发现的路径和分支漂移。

### 2.2 `src/` 的核心模块
| 模块 | 主要职责 | 典型子目录或入口 |
| --- | --- | --- |
| `observer` | `main`、`ObServer` 装配、MySQL 协议、会话、网络、运行时生命周期 | `main.cpp`、`ob_server.cpp`、`mysql/`、`omt/` |
| `sql` | 解析、语义解析、改写、优化、代码生成、执行、DAS | `parser/`、`resolver/`、`rewrite/`、`optimizer/`、`engine/`、`das/` |
| `storage` | 事务访问、LS、Tablet、Memtable、SSTable、合并、DDL、LOB、检索存储 | `tx_storage/`、`ls/`、`tablet/`、`memtable/`、`blocksstable/` |
| `logservice` | PALF 日志、Apply、Replay | `palf/`、`applyservice/`、`replayservice/` |
| `rootserver` | DDL 调度、索引构建、Freeze、Fork Database 等本地控制面 | `ddl_task/`、`fork_table/` |
| `share` | Schema、配置、SCN、内部表、通用数据结构和跨模块接口 | `schema/`、`rc/`、`vector/`、`text_analysis/` |
| `pl` | PL 解析执行及数据库系统包 | `parser/`、`sys_package/` |
| `objit` | 少量基础类型与兼容接口 | 不应把它误读成一个完整 JIT 子系统 |

### 2.3 代码层次
`cmake/module_check/module_layers.conf` 记录了当前架构期望。数字越小，越接近基础层：

```latex
L5  observer / rootserver
L4  pl
L3  sql / storage / logservice
L2  share
L1  oblib common / rpc / grpc
L0  oblib lib
```

规则是：低层不能反向包含高层头文件。同层可以互相依赖。编译 `seekdb` 时，`module_layer_check` 会作为依赖自动运行，也可以单独执行：

```bash
python3 cmake/module_check/module_layer_check.py .
```

需要准确说明它的边界：当前 `[scanned]` 只遍历 `oblib` 和 `share`，其余模块主要作为目标层次注册。因此它表达了全局架构意图，但还没有完整检查每个上层模块。

---

## 3. 第一条主线：进程怎样启动
先从 `src/observer/main.cpp` 的 `main` 和 `inner_main` 开始，不要一上来钻进某个算法目录。

```latex
main
  → inner_main
      → 解析命令行参数
      → 切换到 base-dir
      → 创建 run/、log/、etc/
      → 初始化日志与 PID/daemon
      → ObServer::get_instance()
      → ObServer::init()
      → ObServer::start()
      → ObServer::wait()
      → 进程退出
```

### 3.1 `ObServer::init()` 做什么
`src/observer/ob_server.cpp` 中的 `ObServer::init()` 负责把进程需要的模块准备起来，主线包括：

1. 配置与全局上下文；
2. SQL 工厂、系统变量与内部 SQL 连接；
3. IO、缓存、Schema；
4. 网络框架和全文分词环境；
5. SQL、PL、存储、事务缓存；
6. Server Runtime 和各类后台任务。

### 3.2 `ObServer::start()` 做什么
`start()` 才开始启动 IO、存储对象、日志块、本地管理服务和网络，并等待 Runtime、Schema、时区等状态就绪，最后把服务状态切换为 `SERVING`。

`init` 与 `start` 的区别是阅读大型 C++ 服务的关键：前者主要建立对象和依赖，后者让线程、网络和后台任务真正运行。遇到启动失败时，先看失败发生在 `init` 还是 `start`，搜索范围会立刻缩小。

更细一层，`ObServerRuntimeController` 会按固定顺序 construct、init、start LS、日志、AccessService、向量和 Change Stream 等运行模块。`ObServer` 同时充当模块提供者，并通过 `share::g_mp` 发布当前进程内的服务；例如 DAS 通过该接口取得 `access_service()`。这是一条理解“设计分层”与“当前真实模块获取方式”的重要边界。

当前 `ObServer::wait()` 在停止完成后直接调用 `_Exit(0)`，不会像普通函数一样返回。因此，虽然 `main.cpp` 字面上在 `wait()` 后还有 `observer.destroy()`，正常停止路径并不会执行到那里；失败初始化等路径有自己的清理逻辑。分析退出资源释放时要以这个实际语义为准。

### 3.3 启动后产生哪些文件
`--base-dir` 是运行实例的根目录。程序切换到该目录后，会至少创建：

```latex
<base-dir>/
├── etc/
├── log/
│   └── seekdb.log
├── run/
│   └── seekdb.pid
└── store/ ...
```

所以源码目录和运行数据目录应该分开。开发冒烟时始终使用新的空目录，既容易清理，也能避免旧数据、旧配置和启动用户不一致造成的干扰。

---

## 4. 第二条主线：一条 SQL 怎样穿过内核
以 MySQL 协议的 `COM_QUERY` 为例：

```latex
MySQL packet
  → observer/ob_srv_xlator.cpp：把命令映射为 ObMPQuery
  → observer/mysql/obmp_query.cpp：会话、事务控制与单语句处理
  → sql/ob_sql.cpp：ObSql::stmt_query
      → parser
      → resolver
      → rewrite / transform
      → optimizer
      → code generator / plan cache
  → sql/executor + sql/engine
  → sql/das
  → storage/tx_storage/ObAccessService
  → LS / TabletService
  → Memtable / SSTable
  → 写事务：事务/LS 日志处理器追加 redo 到 PALF 并完成提交
  → ResultSet 返回 MySQL 客户端
```

普通读请求不会走日志持久化。写事务提交 redo 与 Apply/Replay 也不是一条 SQL 同步执行的三个连续步骤：Apply、Replay 属于独立的后台应用或恢复链路。排查写入持久性时，应把“前台提交是否成功”和“后台日志应用/重放状态”分开观察。

推荐按以下断点阅读：

| 阶段 | 文件 | 关键符号 |
| --- | --- | --- |
| 协议命令映射 | `src/observer/ob_srv_xlator.cpp` | 创建 `ObMPQuery` |
| Query 处理 | `src/observer/mysql/obmp_query.cpp` | `ObMPQuery::process()`、`do_process()` |
| SQL 总入口 | `src/sql/ob_sql.cpp` | `ObSql::stmt_query()`、`handle_text_query()` |
| 语义与计划 | `src/sql/ob_sql.cpp` | `generate_stmt()`、`generate_plan()`、`code_generate()` |
| 执行器 | `src/sql/executor/ob_executor.cpp` | Executor 入口 |
| SQL 到存储 | `src/sql/das/` | DAS scan/modify iterator |
| 事务存储门面 | `src/storage/tx_storage/ob_access_service.cpp` | `ObAccessService` |
| Tablet 访问 | `src/storage/ls/ob_ls_tablet_service.cpp` | 扫描、写入、可见性 |

可以用四条命令快速定位主入口：

```bash
rg -n "int inner_main" src/observer/main.cpp
rg -n "int ObServer::(init|start)" src/observer/ob_server.cpp
rg -n "int ObMPQuery::process" src/observer/mysql/obmp_query.cpp
rg -n "int ObSql::stmt_query" src/sql/ob_sql.cpp
```

不要试图第一次就读懂所有分支。先跟一条普通 `SELECT`，明确每层的输入输出，再分别研究 DDL、事务和检索算子。

---

## 5. AI 能力在代码中怎样落地
这一节可以作为进阶内容。它的重点不是罗列目录，而是说明：向量、全文和混合检索并没有绕开 SQL、DDL、事务和存储层。

### 5.1 向量索引
向量能力横跨多层，但建索引、查询和异步维护是三条不同路径：

```latex
建索引：CREATE VECTOR INDEX
  → SQL Resolver 解析定义并生成辅助表
  → Rootserver DDL Task 构建 HNSW/IVF 等索引

查询：向量表达式 / APPROXIMATE 查询
  → Optimizer 选择向量访问路径
  → HNSW/IVF DAS Iterator 做前后过滤与候选合并
  → Vector Index Adapter 查询索引

异步维护：事务 redo
  → Change Stream Fetcher / Dispatcher / Worker
  → Async Plugin 更新内存索引
  → 推进 refresh SCN
```

推荐入口：

+ `src/sql/resolver/ddl/ob_vec_index_builder_util.cpp`
+ `src/sql/das/iter/ob_das_hnsw_scan_iter.cpp`
+ `src/observer/vector_index/ob_plugin_vector_index_service.h`
+ `src/observer/change_stream/ob_cs_plugin_async_index.cpp`
+ `src/storage/vector_index/` 与 `src/storage/vector_type/`

只有配置为异步维护的索引才走 Change Stream 路径。当前 async plugin 代码还明确限制在 heap table 上的非语义 async HNSW 场景；其他索引类型和同步模式有自己的维护路径，不能把同一个刷新语义套到所有向量索引上。对这类异步 HNSW，“事务写入成功”和“ANN 索引的 `refresh_scn` 已追平”是两个需要分别观察的状态。

### 5.2 全文检索
```latex
建索引：FULLTEXT DDL
  → 构建倒排辅助表、Doc ID、分词生成列

查询：MATCH / Domain Scan
  → Optimizer 识别 MATCH / Domain Scan
  → Text Retrieval Merge Iterator
  → 按场景选择 DaaT、TaaT 或 BMW 等检索策略
  → 倒排表扫描，并使用 BM25 等方式计算相关性
```

推荐入口：

+ `src/sql/resolver/ddl/ob_fts_index_builder_util.cpp`
+ `src/sql/das/iter/ob_das_text_retrieval_merge_iter.cpp`
+ `src/sql/das/iter/sparse_retrieval/ob_das_tr_merge_iter.cpp`
+ `src/storage/retrieval/`
+ `src/storage/fts/`
+ `src/share/text_analysis/`

DaaT、TaaT、BMW 是按模式选择的策略，不是每次查询依次执行的流水线；BM25 主要承担相关性计算，也不应被描述成与前三者同一层次的顺序步骤。

### 5.3 混合检索
混合检索不是完全独立的第二套执行引擎，但当前有两种入口：

+ `HYBRID_SEARCH` 表达式在 Resolver 中生成原生 SQL，并重新解析生成的 SQL；
+ `DBMS_HYBRID_VECTOR_MYSQL.SEARCH` 由 `ObHybridSearchExecutor` / `ObQueryTranslator` 生成 SQL，再通过调用者会话的 Inner SQL 连接执行。

两条路径最终都会复用 Optimizer、DAS 以及向量和全文算子，但“重新进入 SQL 引擎”的具体机制不同。

推荐入口：`src/sql/hybrid_search/`。

### 5.4 Fork Database
```latex
FORK DATABASE
  → Resolver / Executor
  → LocalManagementService
  → Rootserver ObForkDatabaseService
  → 若存在 async 向量索引：锁源表并等待 Change Stream 追平
  → 为所有表确定一致快照
  → 创建目标 Schema、映射与 DDL Task
  → Storage ObTabletForkTask
  → 复用 SSTable 物理块，或按快照重写宏块
```

推荐入口：

+ `src/rootserver/fork_table/ob_fork_database_service.cpp`
+ `src/storage/ddl/ob_tablet_fork_task.cpp`

Fork 不能简单描述为“任何时候都零拷贝”。完全位于 Fork 快照之前的 SSTable 可以复用物理块；跨越快照边界的数据需要按快照扫描并重写。数据库级命令提交后，还会继续异步调度各表的 DDL Task。

当前实现还要求目标数据库不存在；源库如果包含 Routine、Package、Trigger 或 Outline，则不支持 Fork。这些属于当前代码约束，产品版本演进后应重新核对。

---

## 6. 三个平台的构建共同点
### 6.1 支持边界
| 平台 | 当前明确支持范围 | 构建入口 | 完整开发测试成熟度 |
| --- | --- | --- | --- |
| Linux | 多个主流发行版，x86_64/aarch64；以仓库 toolchain 与 manifest 为准 | `build.sh` | 最完整 |
| macOS | macOS 13+，仅 Apple Silicon M 系列 | `build.sh` | 内核编译、启动和部分单测可用；无 macOS CI |
| Windows | Windows 11 x64 | `build.ps1` | 原生核心二进制和打包路径已建立；全量测试仍有缺口 |

macOS Intel、Windows ARM64 当前都不在明确支持范围内。

### 6.2 `--init`、配置和编译不是一回事
根 CMake 当前要求 CMake 3.20 及以上，并以 C++20 构建。Linux/Windows 的 `--init` 会准备仓库约定的主要工具链；macOS 使用 Homebrew CMake，并由当前平台与依赖初始化结果提供受支持的 Clang 工具链。因此不要跳过对应平台的前置依赖。

Unix 脚本的基本语义是：

```bash
bash build.sh <debug|release> [--init] [--make [make 参数]]
```

+ `--init`：按当前平台的 manifest 初始化 `deps/3rd`；首次构建或依赖描述变化时使用。
+ `debug` / `release`：运行 CMake，生成或刷新构建目录。
+ `--make`：配置后继续编译；不写它通常只完成配置。
+ `release`：当前映射到 `RelWithDebInfo`，不是一个完全去掉调试信息的纯 `Release`。

Windows 的对应语义是：

```powershell
.\build.ps1 <debug|release> [--init] [--ninja] [-j N]
```

+ `--ninja` 才会在配置后继续编译。
+ Windows `release` 也映射到 `RelWithDebInfo`。

### 6.3 实际产物路径
| 平台与模式 | 主二进制 |
| --- | --- |
| Linux/macOS Debug | `build_debug/src/observer/seekdb` |
| Linux/macOS Release | `build_release/src/observer/seekdb` |
| Windows Debug | `build_debug\src\observer\seekdb.exe` |
| Windows Release | `build_relwithdebinfo\src\observer\seekdb.exe` |

仓库旧版开发文档中的 `build_debug/bin/observer/seekdb`、`build_release/bin/observer/seekdb` 已与当前 CMake 不一致，不要照抄。

### 6.4 并发度与资源
seekdb 是大型 C++ 工程，Unity Build 和链接都可能占用大量内存。Linux/macOS 默认按 CPU 核数并行，在笔记本或共享机器上容易因内存不足失败。第一次演示建议显式使用 `-j16`；内存较小可降到 `-j4`。Windows 脚本会按约 3 GB/任务自动估算并发，也可以手动指定 `-j 4`。

`--init` 会下载较多依赖。应提前确认网络、代理、磁盘空间，并把第一次依赖下载和完整链接放在演讲前完成。

---

## 7. Linux 编译与启动
Linux 是当前最适合做完整开发和回归的平台。若没有特殊发行版要求，建议先在 Ubuntu 22.04 x86_64 上完成第一次构建。

### 7.1 安装系统依赖
Ubuntu/Debian：

```bash
sudo apt-get update
sudo apt-get install -y \
  git wget rpm rpm2cpio cpio make build-essential \
  binutils m4 file python3 libtool-bin
```

Ubuntu 24.04+ 或 Debian 13+ 还需要：

```bash
sudo apt-get install -y libaio1t64
```

CentOS/Rocky/OpenAnolis 等 Yum 系发行版：

```bash
sudo yum install -y \
  git wget 'rpm*' cpio make glibc-devel glibc-headers \
  binutils m4 libtool libaio python3
```

SUSE/openSUSE：

```bash
sudo zypper install \
  git wget rpm cpio make glibc-devel binutils m4 python3
```

发行版支持表比依赖脚本的实际分支更宽，尤其部分 aarch64 组合未必有对应 manifest。最终应以 `deps/init/dep_create.sh` 能否识别当前系统为准；遇到未知发行版不要直接假设二进制兼容。

虽然前置包中有 GCC 和 `build-essential`，当前 Linux 主构建实际由仓库初始化的 Clang 17、LLD 和约定的 GCC sysroot 驱动；`cmake/Env.cmake` 中的纯 GCC 路径并未标记为可用。不要为了处理单个编译错误，擅自把 `CC/CXX` 切到系统 GCC 并混用两套 ABI。

还要注意公共网络可复现性：当前快照的部分 Linux manifest 仍引用 `yum-test.obvos.alibaba-inc.com`、`ob-yum.oceanbase-dev.com` 等开发或内网镜像。外部网络不能保证 `--init` 一键完成。如果首个失败 URL 属于这些域名，这不一定是个人代理配置错误；应在 GitHub Issue 中确认可公开访问的依赖源或向维护者获取当前替代方案，不要从不明来源手工拼接工具链。

### 7.2 克隆和构建 Debug 版本
```bash
git clone https://github.com/oceanbase/seekdb.git
cd seekdb

bash build.sh debug --init --make -j16
```

成功后检查：

```bash
./build_debug/src/observer/seekdb -V
```

注意版本信息必须来自本次编译的二进制。不要把工作区里以前留下的旧 `build_release` 产物当作当前源码已经编译成功的证据。

### 7.3 构建 Release 版本
依赖已经初始化后，不必每次重复 `--init`：

```bash
bash build.sh release --make -j4
./build_release/src/observer/seekdb -V
```

### 7.4 增量编译
只修改 `.cpp` 或头文件时，可以直接构建主目标：

```bash
cmake --build build_debug --target seekdb -- -j4
```

新增源文件、修改 CMake 或切换重要编译选项后，先重新运行配置：

```bash
bash build.sh debug
cmake --build build_debug --target seekdb -- -j4
```

### 7.5 使用独立目录前台启动
```bash
mkdir -p "$HOME/seekdb-dev-run"

./build_debug/src/observer/seekdb \
  --base-dir="$HOME/seekdb-dev-run" \
  --nodaemon
```

这条命令会占住当前终端。另开一个终端连接：

```bash
./deps/3rd/u01/obclient/bin/obclient \
  -h127.0.0.1 -P2881 -uroot -Doceanbase -A
```

也可以自行安装兼容 MySQL 协议的客户端，并使用相同的地址、端口、用户和数据库参数。

执行最小冒烟 SQL：

```sql
SELECT VERSION();
SHOW DATABASES;
CREATE DATABASE source_walkthrough;
USE source_walkthrough;
CREATE TABLE t1(id BIGINT PRIMARY KEY, value VARCHAR(64));
INSERT INTO t1 VALUES (1, 'hello seekdb');
SELECT * FROM t1;
```

返回启动终端按 `Ctrl+C` 结束。日志位于：

```latex
$HOME/seekdb-dev-run/log/seekdb.log
```

若 2881 被占用，可以给一个新的空 `base-dir` 并加 `--port=2882`，连接端口也同步改成 2882。

---

## 8. macOS 编译与启动
### 8.1 先确认平台
```bash
sw_vers -productVersion
uname -m
```

要求是 macOS 13 或更高版本，且 `uname -m` 为 `arm64`。Intel Mac 当前不受支持。

如果尚未安装命令行开发工具：

```bash
xcode-select --install
```

### 8.2 安装 Homebrew 依赖
```bash
brew install git cmake pkg-config openssl@3 ncurses googletest
brew install zstd lz4 utf8proc thrift re2 brotli
```

### 8.3 编译
```bash
git clone https://github.com/oceanbase/seekdb.git
cd seekdb

bash build.sh debug --init --make -j16
./build_debug/src/observer/seekdb -V
```

Release：

```bash
bash build.sh release --make -j16
./build_release/src/observer/seekdb -V
```

个人 Mac 的内存通常比编译服务器小，不建议直接照搬 `-j32`。先用 `-j16`，确认内存余量后再提高。

### 8.4 启动和连接
```bash
mkdir -p "$HOME/seekdb-dev-run"

./build_debug/src/observer/seekdb \
  --base-dir="$HOME/seekdb-dev-run" \
  --nodaemon
```

另一个终端安装并调用 MySQL 客户端：

```bash
brew install mysql-client
"$(brew --prefix mysql-client)/bin/mysql" \
  -h127.0.0.1 -P2881 -uroot -Doceanbase -A
```

macOS 原生内核编译与启动有明确支持，但仓库当前没有 macOS CI；`tools/deploy/obd.sh` 和部分测试脚本还使用 GNU `readlink -f` 等 Linux 假设。因此不要把“Mac 上能编译运行”扩展成“完整 OBD/mysqltest 回归已原生打通”。Mac 上单测优先直接使用 Homebrew/CMake 提供的 `ctest`，完整 mysqltest 建议放到 Linux 环境。

---

## 9. Windows 编译与启动
### 9.1 这是一条真正的 Windows 原生构建链
当前 Windows 路径生成的是 PE 可执行文件，不需要 WSL、Docker 或 MinGW。更准确地说，它使用：

```latex
LLVM 18 clang-cl + lld-link + llvm-lib
                    │
                    └── Visual Studio 2022 Build Tools / Windows SDK / MSVC ABI / 动态 CRT
```

所以它也不能简单称为“由 `cl.exe` 主导的 MSVC 构建”。VS Build Tools 主要提供 Windows SDK、系统库、MSVC 运行时和 ABI 环境。

### 9.2 前置软件
要求 Windows 11 x64，并安装：

1. Git；
2. Python 3.x，安装时加入 `PATH`；
3. Visual Studio 2022 Build Tools，勾选“使用 C++ 的桌面开发”，同时安装 Windows 11 SDK。

若要执行连接冒烟，还需另行安装一个兼容 MySQL 协议的命令行客户端；它不是编译 `seekdb.exe` 的必备依赖。

当前 `cmake/Env.cmake` 还把 Windows SDK include 版本精确写为 `10.0.26100.0`，而 `build.ps1 init` 不会安装 Windows SDK。先检查：

```powershell
Test-Path "${env:ProgramFiles(x86)}\Windows Kits\10\Include\10.0.26100.0\um"
```

结果必须为 `True`。若 VS Installer 只安装了其他版本，请在“单个组件”中补装 Windows 11 SDK `10.0.26100.0`；在源码改为动态发现 SDK 版本之前，仅有一个泛化的“Windows 11 SDK”并不足以保证当前命令可执行。

CMake、Ninja、LLVM 18、win_flex_bison、OpenSSL 和 vcpkg 第三方库由 `build.ps1 init` 下载到 `deps\3rd`。

建议使用较短的源码路径，例如 `C:\src\seekdb`，并在 PowerShell 中操作：

```powershell
New-Item -ItemType Directory -Force C:\src | Out-Null
Set-Location C:\src
git clone https://github.com/oceanbase/seekdb.git
cd seekdb

python --version
git --version
```

### 9.3 Debug 构建
仅对当前 PowerShell 进程放开脚本执行，然后初始化并编译：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1 debug --ninja --init -j 4
```

也可以拆开：

```powershell
.\build.ps1 init
.\build.ps1 debug --ninja -j 4
```

检查产物：

```powershell
.\build_debug\src\observer\seekdb.exe -V
Get-ChildItem .\build_debug\src\observer\
```

CMake 的 post-build 步骤会尝试把运行 DLL 放到 `seekdb.exe` 同目录。必须在一台没有额外开发环境 `PATH` 帮助的干净 Windows 机器上再做一次 `-V` 和真启动冒烟，才能确认 DLL 集合完整。

### 9.4 Release 构建
```powershell
.\build.ps1 release --ninja -j 4
.\build_relwithdebinfo\src\observer\seekdb.exe -V
```

常见误区是去找 `build_release`。Windows 的 `release` 实际使用 `RelWithDebInfo`，目录名因此是 `build_relwithdebinfo`。

### 9.5 前台启动
```powershell
New-Item -ItemType Directory -Force C:\seekdb-dev-run | Out-Null

.\build_debug\src\observer\seekdb.exe `
  --base-dir=C:\seekdb-dev-run `
  --nodaemon
```

另开 PowerShell，使用已安装的 MySQL 客户端连接：

```powershell
mysql -h 127.0.0.1 -P 2881 -u root -D oceanbase
```

开发阶段优先使用前台模式观察日志。当前 `tools/windows/seekdb_manage.ps1` 的首次初始化与自定义服务名仍有需要实机验证的行为，不把它列为本期的开箱即用主路径。

### 9.6 可选：打包
```powershell
.\build.ps1 package --init
```

+ 安装 .NET 8 SDK 后可以构建 WPF Configurator；缺少时跳过该向导。
+ 安装 WiX v4 后尝试生成 MSI；缺少时回退为 ZIP。
+ 输出在 `build_relwithdebinfo` 下，文件名通常匹配 `seekdb-*.msi` 或 `seekdb-*.zip`。

### 9.7 Windows 当前不能过度承诺的部分
核心二进制构建链已经存在，但以下环节仍应放到 Linux 做完整验证：

+ `unittest` 的部分链接参数仍带 GNU 风格，仓库没有可靠的 Windows 全量测试 runner；
+ OBD/mysqltest 仍以 Bash/Linux 工具链为主；
+ PL 的 `_Unwind_*` 在 Windows 当前是兼容 stub；
+ 当前仓库没有 Windows CI 证明每个提交都已实编实跑。

因此，仓库已经提供 Windows 原生修改和构建路径，但当前 HEAD 没有 Windows CI 或本机实编证据，仍需在符合上述 SDK 条件的 Windows 11 x64 机器上完成 `-V`、真启动和 SQL 冒烟。涉及核心逻辑的 PR 还应补充 Linux 单测和 mysqltest 结果。

---

## 10. 配置代码阅读环境
### 10.1 先生成 `compile_commands.json`
Linux/macOS 使用 ccls：

```bash
bash build.sh ccls --init
```

使用 clangd：

```bash
bash build.sh clangd --init
```

`clangd` profile 会关闭 Unity Build，并在仓库根目录建立 `compile_commands.json` 链接。Windows 的 `build.ps1` 在配置成功后会把 `compile_commands.json` 复制到仓库根目录。

### 10.2 推荐的阅读顺序
1. `README_CN.md`：先理解产品能力；
2. `cmake/module_check/module_layers.conf`：理解依赖方向；
3. `src/observer/main.cpp`：进程入口；
4. `src/observer/ob_server.cpp`：模块怎样装配和启动；
5. `src/observer/omt/ob_server_runtime_controller.cpp`：运行时模块生命周期；
6. `src/observer/mysql/obmp_query.cpp`：SQL 怎样进入内核；
7. `src/sql/ob_sql.cpp`：完整编译主线；
8. `src/storage/tx_storage/ob_access_service.cpp`：SQL 与事务存储的边界；
9. 再根据任务进入向量、全文、Fork 或某个具体算子。

### 10.3 三种搜索方式
```bash
# 找定义
rg -n "class ObAccessService|ObAccessService::" src/storage

# 找错误码或日志文本
rg -n "OB_NOT_INIT|server runtime is ready" src deps/oblib

# 找某个 CMake target 如何生成
rg -n "add_executable\(seekdb|add_custom_target\(observer" CMakeLists.txt src cmake
```

大型代码库里，符号跳转与 `rg` 应该配合使用。索引能告诉你“谁引用它”，文本搜索更擅长找宏、日志、配置名和跨生成代码的线索。

---

## 11. 从修改代码到本地验证
### 11.1 先定义最小影响面
开始编码前先回答：

+ 改动属于协议、SQL、存储、日志还是跨模块接口？
+ 是否引入了低层依赖高层的 include？
+ 行为变化应该由单元测试、mysqltest，还是两者共同覆盖？
+ 是否改变 SQL 兼容、数据格式、升级路径或用户可见行为？

### 11.2 代码风格中最容易踩的规则
仓库的习惯与普通现代 C++ 项目不完全相同：

+ 文件一般以 `ob_` 开头，类以 `Ob` 开头，成员变量以 `_` 结尾；
+ 两空格缩进，不使用 Tab，单行目标不超过 100 字节；
+ 核心代码避免 STL/Boost 容器，优先使用 `ObSEArray` 等 OceanBase 容器；
+ 大多数函数使用 `int ret = OB_SUCCESS` 和单出口；
+ 用 `OB_FAIL`、`OB_SUCC`、`OB_ISNULL` 等宏，并检查返回值和指针；
+ 构造函数只做轻量初始化，复杂逻辑放 `init()`，资源释放放 `destroy()`；
+ 日志使用结构化键值，例如 `LOG_WARN("open failed", K(ret), K(path));`。

不要仅凭这份摘要机械改写代码。优先模仿同目录近期代码，再阅读 `coding-convention.md` 和 `coding-standard.md`。

仓库保留了 `tools/codestyle/astyle.sh`，但当前干净 checkout 缺少它期望的 OB 定制版 astyle 源码目录，不能把它当作外部贡献者可稳定复现的自动格式化命令。提交前至少执行：

```bash
git diff --check
```

然后人工检查缩进、空白、行宽以及与相邻代码的一致性。

### 11.3 编译受影响主目标
```bash
cmake --build build_debug --target seekdb -- -j4
```

`seekdb` 目标会连带执行模块层次检查。构建成功后再运行 `seekdb -V` 和相关 SQL 冒烟，不要只看编译器退出码。

### 11.4 单个单元测试
常规 Debug 配置会注册单测目录但不默认构建所有测试，可以按 target 编译：

```bash
cmake --build build_debug --target test_chunk_row_store -- -j4
./build_debug/unittest/sql/engine/basic/test_chunk_row_store
```

新增单测文件使用 `test_xxx.cpp`，并加入相应 `CMakeLists.txt`。测试目录通常与 `src` 模块结构相呼应。

### 11.5 全量单测
若需要让单测进入默认构建目标，重新配置：

```bash
bash build.sh debug --init -DOB_BUILD_UNITTEST=ON --make -j4
```

Linux 使用仓库依赖中的 CTest：

```bash
deps/3rd/usr/local/oceanbase/devtools/bin/ctest \
  --test-dir build_debug/unittest \
  --output-on-failure
```

macOS 使用系统/Homebrew CTest：

```bash
ctest --test-dir build_debug/unittest --output-on-failure
```

全量单测非常耗时。日常开发先跑受影响 target，再在准备 PR 时扩大范围。

### 11.6 mysqltest
mysqltest 用 `.test` 作为输入，把输出与 `.result` 逐行比较，特别适合验证 SQL 语义、优化器、错误码和兼容行为。最可靠的本地路径目前是 Linux。

先准备并部署一个测试实例：

```bash
SEEKDB_TEST_DATA_DIR=$(mktemp -d /tmp/seekdb-mysqltest.XXXXXX)
SEEKDB_TEST_NAME="seekdb-pr-$(id -u)-$(date +%s)"

./tools/deploy/obd.sh prepare \
  -b ./build_debug \
  -p "$SEEKDB_TEST_DATA_DIR"

./tools/deploy/obd.sh deploy \
  -c ./tools/deploy/single.yaml \
  -n "$SEEKDB_TEST_NAME"
```

`SEEKDB_TEST_DATA_DIR` 是新建的可丢弃临时目录，不能替换为承载重要数据的路径；后续命令要在同一个 Shell 中执行。`prepare` 只会在文件不存在时生成 `tools/deploy/single.yaml`，若本地已有该文件，先确认其中的 `home_path` 确实指向这次的临时目录。`deploy` 会强制重建同名部署，所以示例也生成唯一部署名。还要确认配置中的实际 `mysql_port`，不要假设一定是 10000 或 2881。

运行一个 case：

```bash
./tools/deploy/obd.sh mysqltest \
  -n "$SEEKDB_TEST_NAME" \
  --disable-reboot \
  --test-dir ./mysql_test/test_suite/alter/t \
  --result-dir ./mysql_test/test_suite/alter/r \
  --test-set alter_table
```

运行一个 suite：

```bash
./tools/deploy/obd.sh mysqltest \
  -n "$SEEKDB_TEST_NAME" \
  --disable-reboot \
  --suite alter
```

脚本默认可能重新部署或重启，已有实例时使用 `--disable-reboot`。`--record` 会切换为记录模式，默认把输出写到 `record-dir` 下的 `.record` 文件，而不是直接覆盖仓库中的 `.result`。只有确认行为变化正确时才使用；若要更新预期结果，应逐行审查 `.record` 与现有 `.result` 的差异，再显式修改目标文件。

### 11.7 测试选择表
| 修改类型 | 最低建议验证 |
| --- | --- |
| 文档、注释 | 链接/命令人工核对，`git diff --check` |
| 局部工具函数 | 受影响单测 target + Debug 编译 |
| Parser/Resolver/表达式 | 单测 + 精确 mysqltest case |
| Optimizer/执行器/DAS | 单测 + 相关 suite + 执行计划检查 |
| 事务、存储、日志 | 单测 + 重启/恢复相关测试 + 相关 mysqltest |
| 向量/全文索引 | DDL、写入、刷新、查询、重启各阶段测试 |
| 跨平台代码 | Linux 回归 + 目标平台原生编译与启动冒烟 |

---

## 12. 从 Issue 到 Pull Request
对外贡献以根目录 `CONTRIBUTING.md` 为当前规则来源。旧的 `docs/developer-guide/*/contributing.md` 仍有从 `master` 开分支的历史说明，不应用于当前 PR。

### 12.1 第一步必须是 Issue
所有贡献都应关联 GitHub Issue：

+ 先搜索是否已有同类问题；
+ Bug 使用 `[Bug]` 标题并给出最小复现、期望结果、实际结果、系统和版本；
+ 新能力使用 `[Feature]`，先说明使用场景，不要直接交一大块代码。

Bug 在维护者确认后可以开发，并应补回归测试。

### 12.2 大功能采用 Design-First
大型功能先在 Issue 讨论。维护者认可需求后：

1. 编写 `docs/design/YYYY-MM-DD-feature-name.md`；
2. 设计 PR 目标为 `develop`；
3. 标题使用 `[Design] Proposal for <Feature Name>`；
4. 设计合并后再提交实现。

当前仓库可能还没有 `docs/design/` 目录，第一次设计贡献前应在 Issue 中确认，由设计 PR 一并创建，而不是绕过流程。

### 12.3 Fork、配置远端并建立分支
先在 GitHub 页面 Fork `oceanbase/seekdb`，然后：

```bash
GITHUB_USER=your-github-name
git clone "https://github.com/${GITHUB_USER}/seekdb.git"
cd seekdb

git remote add upstream https://github.com/oceanbase/seekdb.git

# 可选：禁止误推到官方 upstream
git remote set-url --push upstream DISABLED

git fetch upstream
git checkout -b fix/short-description-123 upstream/develop
```

仓库明确的命名形态是：

```latex
type/description-issue-number
```

例如 `fix/vector-refresh-123`。仓库没有公布严格的 type 枚举；拿不准时在 Issue 中确认。

### 12.4 开发与提交前检查
```bash
git status
git diff
git diff --check
```

完成受影响编译和测试，把**实际执行过的命令与结果**保存下来，稍后写进 PR。然后交互式选择本次改动；新文件再用 `git add` 加入它的实际文件名：

```bash
git add -p
git diff --cached
git commit -m "fix: concise imperative summary"
```

仓库没有强制 Conventional Commits、DCO `Signed-off-by` 或 GPG 签名规则；清楚说明意图比机械套前缀更重要。

### 12.5 同步 `develop` 并推送
```bash
git fetch upstream
git rebase upstream/develop
git push -u origin fix/short-description-123
```

如果分支已经推送后又做了 rebase，只使用 `git push --force-with-lease`，不要使用普通 `--force`。

### 12.6 创建 PR
在 GitHub 创建 Pull Request 时：

+ head：你的 fork 和功能分支；
+ base：`oceanbase/seekdb:develop`；
+ 用 `Fixes #123` 关联 Issue；
+ 大功能同时链接设计 PR；
+ 按 `.github/pull_request_template.md` 填写全部相关字段。

PR 正文至少要让评审者看到：

```markdown
### Task Description

Fixes #123

### Solution Description

- 根因是什么
- 为什么选择这个边界和方案
- 哪些路径刻意没有改

### Passed Regressions

- `cmake --build build_debug --target ...`：通过
- `./build_debug/unittest/.../test_xxx`：通过
- mysqltest `suite.case`：通过
- 目标操作系统启动和 SQL 冒烟：通过

### Upgrade Compatibility

- 数据格式、配置、协议和旧版本兼容性结论

### Release Note

- 面向用户的一句话变化；纯内部改动可说明无需 Release Note
```

首次贡献会被提示签署 [OceanBase CLA](https://cla-assistant.io/oceanbase)。仓库没有要求 `git commit -s`，不要把 CLA 与 DCO 混为一谈。

### 12.7 Review 与 CI
收到意见后，先确认问题属于正确性、边界、可维护性还是测试覆盖，再提交小而清楚的后续 commit。不要把无关重构混入修复。

根贡献指南期望 Compile、Farm、单测、部分 mysqltest 和 Linter。当前核对的仓库快照里，公开 `Compile` 与 `SeekDB CI` 的 PR 触发器标记为临时关闭，且部分 Farm 依赖内部 runner。**没有自动检查出现，不等于改动已通过测试。** 外部贡献者应尽可能完成本地编译、相关单测和 mysqltest，并在 PR 中诚实写明未能运行的部分；完整 Farm 或无关失败重跑由维护者协助。

---

## 13. 常见问题与定位顺序
| 现象 | 先检查什么 | 建议处理 |
| --- | --- | --- |
| `--init` 下载失败 | 日志中的首个失败 URL、代理、证书、磁盘 | 重试并保留完整日志；不要随意混装不同版本工具链 |
| 编译进程被杀、机器卡死 | 系统 OOM、并发度 | 降为 `-j2` 或 `-j4` |
| 只生成构建目录，没有二进制 | 是否遗漏 `--make` / `--ninja` | Unix 加 `--make`，Windows 加 `--ninja` |
| 找不到 `build_*/bin/observer/seekdb` | 读到了旧文档路径 | 使用 `build_*/src/observer/seekdb` |
| Windows Release 找不到 `build_release` | `release` 映射到 `RelWithDebInfo` | 看 `build_relwithdebinfo` |
| `libaio.so.1` 缺失 | Ubuntu 24.04+/Debian 13+ | 安装 `libaio1t64` |
| macOS 编译器或头文件异常 | 系统版本、`uname -m`、Xcode CLT、Homebrew 前缀 | 只支持 macOS 13+ Apple Silicon |
| Windows 启动缺 DLL | 是否从 `seekdb.exe` 原构建目录运行 | 检查同目录 post-build DLL，并在干净机器复测 |
| 端口被占用 | 2881 或 OBD 生成端口 | 新 base-dir + `--port`；OBD 读取 `single.yaml` |
| 直接运行用 2881，OBD 文档却写 10000 | 两条启动路径不同 | 直接启动默认 2881；OBD 以生成配置为准 |
| 提示必须由初始用户启动 | base-dir 由另一用户初始化 | 换新的空 base-dir，或使用原初始化用户 |
| 改头文件后出现大量奇怪错误 | 旧 CMake cache、依赖描述变化 | 先重新运行对应 build 配置；确认后只清理相关 build 目录 |
| mysqltest 失败 | `.record`、服务日志、实际端口与部署名 | 先跑单 case，查看 `seekdb.log`，再扩大到 suite |

定位时优先找**第一处真正失败**，不要只看最后一行。大型构建往往在前面已经出现根因，后面只是级联错误。

---

## 14. 一次可落地的新人练习
可以把本期实践设计成下面的闭环：

1. 在 Linux/macOS/Windows 任选一个受支持平台，完成 Debug 原生构建；
2. 使用新的 base-dir 前台启动，并跑通建库、建表、写入、查询；
3. 从 `main → ObServer → ObMPQuery → ObSql` 跳转一次；
4. 选择一个已经被维护者确认的 Issue；
5. 找到同模块现有单测，先让测试复现问题；
6. 做最小修改，编译受影响 target；
7. 跑单测与相关 mysqltest；
8. 在 PR 中写清根因、方案、边界和真实测试结果。

对大型数据库项目来说，第一个高质量贡献不一定代码很多。能够找到正确层次、复现问题、补上精确回归测试，并让维护者十分钟内理解你的改动，就是很好的开始。

---

## 15. 最后总结
1. seekdb 是单进程、模块化的数据库内核，`observer` 负责装配，`sql/storage/logservice` 承担主数据路径。
2. 阅读源码先跟启动链和普通 SQL 链，再进入向量、全文、Hybrid 或 Fork 的具体实现。
3. Linux 的开发回归最完整；macOS 仅支持 Apple Silicon；Windows 是原生构建，但测试链仍需 Linux 补齐。
4. 贡献从 Issue 开始，当前从 `develop` 建分支并向 `develop` 提 PR；测试结果要具体、真实、可复现。

---

## 附录
编译参考：

+ Mac 编译手册(等待更新)
+ Windows 编译指南(等待更新)

资料发生冲突时，本文采用以下优先级：当前 `build.sh` / `build.ps1` 与 CMake 实现，其次是根 README 和根 CONTRIBUTING，最后才是可能存在历史漂移的开发者文档或旧教程。
