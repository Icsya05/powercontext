适用对象：AMD 学生环境交付及运维团队。

核查日期：2026 年 10 月 28 日。

## 1. 问题与已确认的原因
部分同学已经成功运行 seekdb，但训练营查询不到部署 UUID，部署题无法通过。在提供的一台标准 AMD 环境中，实际执行首次部署后复现了以下日志：

```latex
cluster bootstrap success
Failed to perform curl(cc=77)
failed to report bootstrap telemetry synchronously
```

数据库能够正常执行 SQL，但自动部署上报失败。该实例的环境为 Ubuntu 24.04.4，seekdb 版本为 1.4.0.0，程序报告的源码版本为：

```latex
de17949d57b9cd2240f141f8116d29bcd495d8d9
```

实际检查了 seekdb 二进制中 libcurl 的初始化逻辑，确认它默认使用：

```latex
/etc/pki/tls/certs/ca-bundle.crt
```

该路径在机器上不存在；机器上已经安装且可读取的系统证书是：

```latex
/etc/ssl/certs/ca-certificates.crt
```

因此，本次故障是程序默认证书路径与 Ubuntu 环境不匹配，导致 CA 证书文件加载失败。libcurl 的错误码 77 对应 CA 证书读取问题。

另外，本次实测通过环境预置代理可以访问 `openwebapi.oceanbase.com` 并完成 TLS 校验，强制直连则连接超时。系统 curl 能访问网站，不代表 seekdb 内置 libcurl 使用的证书配置正确，也不代表自动上报已经成功。

本结论已在上述机器上确认；相同交付环境、相同程序且出现同类错误的实例可以按本方案处理。其他错误码应另行定位。

## 2. AMD 需要怎样修复后续交付的环境
### 2.1 在首次启动 seekdb 之前执行修复
在实际运行 seekdb 的环境内，以 root 执行以下命令。如果 seekdb 运行在容器内，必须处理容器内的路径，仅修改宿主机不一定有效。

```bash
bash <<'SH'
set -eu

source_ca=/etc/ssl/certs/ca-certificates.crt
compat_ca=/etc/pki/tls/certs/ca-bundle.crt

if [ ! -r "$source_ca" ] || [ ! -s "$source_ca" ]; then
  echo "失败：系统 CA 证书缺失或不可读，请先修复 ca-certificates。" >&2
  exit 1
fi

if [ -e "$compat_ca" ] || [ -L "$compat_ca" ]; then
  if [ ! "$source_ca" -ef "$compat_ca" ]; then
    echo "失败：目标路径已有其他文件或链接，请检查，不要直接覆盖。" >&2
    exit 1
  fi
else
  install -d -m 755 /etc/pki/tls/certs
  ln -s "$source_ca" "$compat_ca"
fi

test -r "$compat_ca"
test -s "$compat_ca"
echo "完成：seekdb CA 兼容路径已就绪。"
SH
```

执行后的目标状态是：

```latex
/etc/pki/tls/certs/ca-bundle.crt
    -> /etc/ssl/certs/ca-certificates.crt
```

本次检查的标准环境已经具备系统证书，不需要为此重新编译 seekdb。该命令不会覆盖已有的其他证书文件，不会上传遥测，不会修改数据库数据或成绩。

### 2.2 将修复纳入实际环境交付流程
**不限定 AMD 使用镜像、环境初始化脚本还是其他交付方式。请将上面的操作加入实际准备学生环境的流程，保证每个新交付的环境在首次运行 seekdb 前已完成修复。**

仅修改当前排查的这一台机器，不能修复后续交付的其他机器；仅更新交付模板，也不会自动修复学生已经领取的环境。

需要保留现有 `https_proxy`、`http_proxy` 等代理配置，不要硬编码本次排查机器的代理地址。不要使用 `curl -k` 或关闭程序的 TLS 证书校验。

### 2.3 在启动入口加入前置检查
本次标准环境的启动脚本是：

```latex
/seekdb_workspace/scripts/start_observer.sh
```

在该脚本的 `set -e` 后、删除或初始化数据目录等操作之前，加入：

```bash
CA_FILE=/etc/pki/tls/certs/ca-bundle.crt

if [ ! -r "$CA_FILE" ] || [ ! -s "$CA_FILE" ]; then
  echo "seekdb 未启动：环境缺少可用 CA 证书，请联系 AMD 平台修复。" >&2
  exit 1
fi
```

如果其他交付环境采用不同启动入口，应在实际启动 seekdb 前做同样检查。这个检查用于避免路径缺失，不替代真实上报验收。

## 3. 已领取机器的学生愿意重新部署时怎么处理
采用“先修证书，再重新初始化”的方式，无需给学生提供手工上报接口或允许任填 UUID 的补报脚本。

1. **先修复现有环境。** 由 AMD 批量执行第 2.1 节命令，或将命令作为 Notebook 的修复步骤提供给学生。必须在实际运行 seekdb 的环境中执行。
2. **保存学生数据。** 保存 Notebook、代码和需要保留的数据库数据。重新初始化会建立新实例，不会自动迁移旧数据。
3. **停止当前 seekdb。** 确认停止的是本 Notebook 使用的实例，并等待进程退出；不能在旧进程占用相同端口时再启动一个实例。
4. **将旧数据目录改名备份，不直接删除。** 本次 Notebook 使用 `/workspace/run/obs1`。其他环境必须先核对实际目录。当前启动脚本在某些条件下会清理传入的数据目录，因此不要未经备份就直接反复运行启动脚本。
5. **在已修复的同一环境中，重新运行原 Notebook 的初始化和启动单元格。** 使用空数据目录完成首次初始化，让 seekdb 自行产生并发送真实部署上报。只重启原实例、只重新提交评测，都不等于重新初始化。
6. **读取本次生成的部署 UUID。** 本次默认文件为 `/workspace/run/obs1/run/telemetry.json`，提交其中的 `content.id`。不要使用 Notebook 的中间标识；UUID 不一定变化，应以实际文件为准。
7. **确认自动上报成功后再提测。** 修复后的实例仍需通过正常的上报查询及队伍认领校验，不直接给分。

请 AMD 将“精确停止实例、确认退出、备份原数据目录、重新初始化”整理为与实际 Notebook 匹配的操作步骤，先在验收环境验证，再通知学生。不要让学生执行不区分实例的批量杀进程或删除目录命令。

如果学生选择销毁并重新领取环境，必须先确认新领取的环境已经包含第 2 节修复，否则会重复遇到同一问题。新环境不自动保留旧环境中的学生数据。

## 4. 为什么仅重启或等待不能解决
本次核查版本在首次初始化完成后尝试上报部署事件 `bootstraped`。上报失败不阻断数据库启动；这条链路没有定时重试，普通重启通常不会再次执行首次初始化上报。

所以：

+ `telemetry.json` 存在，不等于平台已收到上报。
+ 修复 CA 路径后，不能承诺旧实例自动补报。
+ 本方案面向接受重新部署的学生，通过真实的重新初始化触发上报，不伪造部署记录。

## 5. AMD 交付前的验收标准
先完成单机验收，再批量推广；至少覆盖下面两种情况。

### 新领取环境
从 AMD 平台正常领取一个新环境，按学生原有 Notebook 流程首次启动 seekdb，确认：

1. 默认就具备正确的 CA 兼容路径，无需学生额外修复。
2. seekdb 启动成功，SQL 查询正常。
3. 自动上报没有 `cc=77` 或其他上报失败。
4. 由主办方只读查询确认平台已收到 `content.id` 对应的部署记录。
5. 使用该 UUID 提测，能够正常完成部署题核验。

### 已领取的旧环境
选择一个已经复现上报失败的验收实例，先保存数据，再按第 3 节操作，确认修复和重新初始化后能够上报、查询和提测。

**验收不能只看“脚本执行成功”“数据库能连接”或“系统 curl 能访问网站”。以 seekdb 真实自动上报被平台接收为准。** 若修复 CA 后出现其他错误，应继续检查代理、请求超时及实际接收情况，不能将其他故障都归为本次 CA 问题。

## 6. AMD 需要反馈的结果
+ 修复加入了哪个实际交付环节，以及从哪个环境版本或时间点开始生效。
+ 新领取环境的单机验收结果。
+ 现有环境的修复和重新部署步骤，以及一次完整验证结果。
+ 验收实例的部署 UUID 与主办方确认的平台接收结果；不需要提供登录密码、私钥或评测 Token。

## 参考依据
+ [libcurl 错误码定义：77 为 CA 证书文件读取问题](https://curl.se/libcurl/c/libcurl-errors.html)
+ [libcurl 默认证书路径由构建时配置决定](https://curl.se/libcurl/c/CURLOPT_CAINFO.html)
+ [本次程序报告版本的首次初始化上报入口](https://github.com/oceanbase/seekdb/blob/de17949d57b9cd2240f141f8116d29bcd495d8d9/src/standby/standby_module.cpp#L335)
+ [本次程序报告版本的遥测实现](https://github.com/oceanbase/seekdb/blob/de17949d57b9cd2240f141f8116d29bcd495d8d9/src/share/ob_telemetry.cpp)
