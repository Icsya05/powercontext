/** Probe: getCollection with embeddingFunction: null (the supported way to stay embedding-free). */

import { SeekdbClient } from "seekdb";

const client = new SeekdbClient({
  host: "127.0.0.1",
  port: 28811,
  user: "root",
  password: "StepFun@2026",
  database: "stepfun_kb",
});

try {
  const collection = await client.getCollection({ name: "kb", embeddingFunction: null });
  console.log("getCollection({embeddingFunction:null}) OK:", collection.name);
  console.log("  count:", await collection.count());
  console.log("  describe:", JSON.stringify(await collection.describe()));
  const hasEf = Boolean(collection.embeddingFunction);
  console.log("  集合上挂着 embedding 函数吗？", hasEf ? "是（不该出现）" : "否 ✅");
} catch (error) {
  console.log("失败:", error.constructor.name, "|", error.message);
}

await client.close();
