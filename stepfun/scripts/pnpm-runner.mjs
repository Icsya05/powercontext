/**
 * 调用 pnpm 的小工具。
 *
 * 为什么绕这一下：
 *  - Windows 上 corepack 是 corepack.cmd，Node >= 18.20 的 spawnSync 出于安全考虑
 *    拒绝在没有 shell 的情况下启动 .cmd（EINVAL），所以必须显式经过 cmd.exe。
 *  - corepack enable 在这台机器上会报 EPERM（mkdir 'D:\'），所以 pnpm 的 shim
 *    装不上，只能直接用 `corepack pnpm`。
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const isWindows = process.platform === "win32";

function hasCommand(cmd) {
  const probe = isWindows ? "where" : "which";
  const result = spawnSync(probe, [cmd], { encoding: "utf8", shell: false });
  return result.status === 0 && Boolean((result.stdout || "").trim());
}

/** 返回可用的 pnpm 调用方式：["corepack", "pnpm"] 或 ["pnpm"]。找不到返回 null。 */
export function detectPnpm() {
  if (hasCommand("corepack")) return { cmd: "corepack", prefix: ["pnpm"] };
  if (hasCommand("pnpm")) return { cmd: "pnpm", prefix: [] };
  return null;
}

export function runPnpm(args, { cwd, stdio = "inherit" } = {}) {
  const detected = detectPnpm();
  if (!detected) {
    console.error(
      "\n找不到 pnpm。\n" +
        "  方案 A（推荐）：corepack enable   —— 但本机 root 盘不可写时会失败\n" +
        "  方案 B：npm install -g pnpm\n" +
        "  方案 C：corepack pnpm <命令>       —— 直接用 corepack 转发，不需要 enable\n",
    );
    process.exit(1);
  }

  const full = [...detected.prefix, ...args];
  console.log(`\n$ ${detected.cmd} ${full.join(" ")}   (cwd: ${cwd ?? process.cwd()})`);

  let result;
  if (isWindows) {
    // 交给 cmd.exe 解析 .cmd；用引号包住整条命令，参数里没有需要转义的字符。
    const line = [detected.cmd, ...full.map((arg) => (/\s/.test(arg) ? `"${arg}"` : arg))].join(" ");
    result = spawnSync(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", line], {
      cwd,
      stdio,
      shell: false,
    });
  } else {
    result = spawnSync(detected.cmd, full, { cwd, stdio, shell: false });
  }

  if (result.error) {
    console.error(`执行失败：${result.error.message}`);
    process.exit(1);
  }
  if (result.status !== 0) {
    console.error(`命令返回非零退出码：${result.status}`);
    process.exit(result.status ?? 1);
  }
  return result;
}

/** 在 stepfun/ 下定位某个相对路径。 */
export function stepfunPath(...parts) {
  const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
  return path.resolve(here, "..", ...parts);
}

export function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
