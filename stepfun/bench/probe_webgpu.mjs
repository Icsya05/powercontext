/** Probe: which Playwright launch options give Edge a working WebGPU adapter? */

import { chromium } from "playwright";

const EDGE = "msedge";

const CASES = [
  { label: "默认", options: {} },
  { label: "ignoreDefaultArgs:--disable-gpu", options: { ignoreDefaultArgs: ["--disable-gpu"] } },
  {
    label: "ignore --disable-gpu + unsafe-webgpu",
    options: {
      ignoreDefaultArgs: ["--disable-gpu"],
      args: ["--enable-unsafe-webgpu", "--enable-features=Vulkan,WebGPU"],
    },
  },
  {
    label: "ignore --disable-gpu + unsafe + 禁沙箱",
    options: {
      ignoreDefaultArgs: ["--disable-gpu"],
      args: [
        "--enable-unsafe-webgpu",
        "--enable-features=Vulkan,WebGPU",
        "--no-sandbox",
        "--disable-gpu-sandbox",
      ],
    },
  },
  {
    label: "headed + ignore --disable-gpu",
    options: { headless: false, ignoreDefaultArgs: ["--disable-gpu"] },
  },
];

for (const testCase of CASES) {
  let browser;
  try {
    browser = await chromium.launch({ channel: EDGE, ...testCase.options });
    const page = await browser.newPage();
    await page.goto("http://127.0.0.1:8080", { waitUntil: "domcontentloaded" });
    const result = await page.evaluate(async () => {
      const nav = navigator;
      if (!nav.gpu) return { gpu: false };
      try {
        const adapter = await Promise.race([
          nav.gpu.requestAdapter(),
          new Promise((resolve) => setTimeout(() => resolve("TIMEOUT"), 8000)),
        ]);
        if (adapter === "TIMEOUT") return { gpu: true, adapter: "timeout" };
        if (!adapter) return { gpu: true, adapter: "null" };
        let info = {};
        try {
          info = adapter.info ?? {};
        } catch {
          /* ignore */
        }
        let device = "n/a";
        try {
          const dev = await adapter.requestDevice();
          device = dev ? "ok" : "null";
        } catch (error) {
          device = `threw: ${String(error).slice(0, 80)}`;
        }
        return {
          gpu: true,
          adapter: "OK",
          device,
          info: { vendor: info.vendor, architecture: info.architecture, description: info.description },
        };
      } catch (error) {
        return { gpu: true, adapter: `threw: ${String(error).slice(0, 120)}` };
      }
    });
    console.log(`${testCase.label.padEnd(38)} ${JSON.stringify(result)}`);
  } catch (error) {
    console.log(`${testCase.label.padEnd(38)} LAUNCH FAILED: ${String(error).slice(0, 160)}`);
  } finally {
    await browser?.close().catch(() => {});
  }
}
