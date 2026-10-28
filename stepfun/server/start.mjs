/**
 * 服务端入口。
 *   node server/start.mjs
 *
 * 环境变量（都有默认值，见 server/src/config.mjs）：
 *   SEEKDB_HOST=127.0.0.1  SEEKDB_PORT=28811  SEEKDB_USER=root
 *   SEEKDB_PASSWORD=...    SEEKDB_DATABASE=stepfun_kb  SEEKDB_COLLECTION=kb
 *   HOST=127.0.0.1         PORT=8080
 */

import { start, stop } from "./src/server.mjs";

const server = await start();

const shutdown = async (signal) => {
  console.log(`\n[stepfun] 收到 ${signal}，正在关闭…`);
  await stop(server);
  process.exit(0);
};

process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));
