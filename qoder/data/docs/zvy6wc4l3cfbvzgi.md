适用于 AMD 标准 Notebook 环境：seekdb 已经部署，但日志出现 `Failed to perform curl(cc=77)`，训练营查询不到部署 UUID。

原因是 seekdb 要读取的证书路径不存在，导致自动上报失败。**先修复证书，再重新初始化 seekdb，最后获取部署 UUID 提测。仅重启旧实例或反复提测不能解决。**

以下命令在 AMD Notebook 的终端中以 root 执行，不是在 SQL 编辑器中执行。仅适用于程序路径 `/seekdb_workspace/bin/seekdb`、数据目录 `/workspace/run/obs1` 的标准环境；路径不一致时不要照搬。

## 1. 修复证书路径
复制整段执行。已有正确配置会直接通过，不会覆盖其他证书文件。

```bash
bash <<'SH'
set -eu
source_ca=/etc/ssl/certs/ca-certificates.crt
compat_ca=/etc/pki/tls/certs/ca-bundle.crt
test -r "$source_ca" && test -s "$source_ca" || {
  echo "系统证书缺失，请联系 AMD 平台处理。"; exit 1;
}
install -d -m 755 /etc/pki/tls/certs
if [ ! -e "$compat_ca" ] && [ ! -L "$compat_ca" ]; then
  ln -s "$source_ca" "$compat_ca"
fi
test "$source_ca" -ef "$compat_ca" || {
  echo "目标路径已有其他文件，请联系 AMD 平台检查，不要强制覆盖。"; exit 1;
}
echo "证书修复完成，请继续下一步。"
SH
```

保留环境原有的代理配置，不要关闭 HTTPS 证书校验，也不要修复后又销毁环境、领取尚未修复的旧环境。

## 2. 停止旧实例并备份
**先保存 Notebook、代码和需要保留的数据。重新初始化不会自动迁移原数据库中的数据。操作期间不要同时运行 Notebook 的启动单元格或数据库任务。**

下面的命令只针对上述标准实例：先核对进程，再正常停止，最后将旧数据目录移动到备份目录；不会删除原数据。如果停止失败或发现其他实例，会停止操作，不强制杀进程。

```bash
bash <<'SH'
set -eu
base=/workspace/run/obs1
command -v pgrep >/dev/null || {
  echo "缺少进程检查工具，请联系 AMD 平台处理。"; exit 1;
}
if [ ! -e "$base" ] && [ ! -L "$base" ]; then
  echo "没有旧数据目录，可直接进行第 3 步。"; exit 0
fi
test -d "$base" && test ! -L "$base" || {
  echo "数据目录异常，请联系 AMD 平台检查。"; exit 1;
}
test -f "$base/run/seekdb.pid" || {
  echo "找不到实例 PID 文件，请联系 AMD 平台检查，不要删除目录。"; exit 1;
}
pid=$(tr -d '[:space:]' < "$base/run/seekdb.pid")
[[ "$pid" =~ ^[0-9]+$ ]] && [ "$pid" -gt 1 ] || {
  echo "PID 文件异常，已停止操作。"; exit 1;
}
if [ -d "/proc/$pid" ]; then
  test "$(readlink "/proc/$pid/exe")" = /seekdb_workspace/bin/seekdb &&
    tr '\0' '\n' < "/proc/$pid/cmdline" | grep -Fxq -- "--base-dir=$base" || {
      echo "PID 不属于此 seekdb 实例，已停止操作。"; exit 1;
    }
  kill -TERM "$pid"
  for i in {1..60}; do
    [ ! -d "/proc/$pid" ] && break
    sleep 1
  done
fi
if [ -d "/proc/$pid" ]; then
  echo "实例尚未退出，请联系 AMD 平台检查；尚未移动数据目录。"; exit 1
fi
if pgrep -x seekdb >/dev/null; then
  echo "仍有 seekdb 进程，请联系 AMD 平台检查；尚未移动数据目录。"; exit 1
else
  status=$?
  [ "$status" -eq 1 ] || {
    echo "进程检查失败，已停止操作；尚未移动数据目录。"; exit 1;
  }
fi
backup=$(mktemp -d /workspace/run/obs1-backup.XXXXXX)
mv -- "$base" "$backup/obs1"
echo "旧数据已保留在：$backup/obs1"
echo "可继续第 3 步；不要删除备份。"
SH
```

看到“旧数据已保留在……”后再继续。如果出现错误，保留提示并联系 AMD 平台，不要改用 `kill -9` 或 `rm -rf`。备份仍占用磁盘空间；空间不足时不要继续重新部署或擅自删除备份。

## 3. 按原 Notebook 重新部署
回到原来的 Notebook，按原部署顺序执行初始化、导入和启动 seekdb 的单元格。不要跳过初始化步骤，也不要仅重启 Notebook 内核。

原启动步骤应在新的空数据目录 `/workspace/run/obs1` 中完成首次初始化，由 seekdb 自动生成并发送部署上报。无需手工调用上报接口，无需重新运行与部署无关的压测来触发上报。

## 4. 获取部署 UUID 并重新提测
启动成功后，以 Notebook 输出的 `telemetry.json` 中的 `content.id` 为准。也可以在终端执行：

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('/workspace/run/obs1/run/telemetry.json')
if not p.is_file():
    raise SystemExit('尚未生成遥测文件，请先确认 seekdb 已完成初始化。')
data = json.loads(p.read_text())
content = data['content']
if isinstance(content, str):
    content = json.loads(content)
print('部署 UUID：', content['id'])
PY
```

复制这个 UUID，回到训练营“seekdb 基础实践”的部署 UUID 输入框重新提测。**UUID 不一定变化，以本次实际生成的文件为准，不要使用 Notebook 的其他中间标识。**

文件生成不等于上报成功。如果仍无法通过，请提供本次 UUID 和日志中的上报错误，联系 AMD 平台或赛事工作人员进一步检查；不要反复重新部署。不要发送账号密码、私钥或完整环境变量。

> 本说明针对已复现的 `cc=77` 证书路径问题。修复后的完整流程仍需由 AMD 先完成单机验收，再统一通知学生操作；其他错误不能直接套用本方案。
>
