import { defineConfig } from "vite";

/**
 * 前端构建配置。
 *
 * 说明：
 * - optimizeDeps.exclude 是 Transformers.js 官方要求的，否则 onnxruntime-web 的
 *   wasm worker 路径会被预打包搞坏。
 * - build.target 用 esnext，因为 WebGPU / WASM SIMD 需要较新的语法。
 * - public/ort/ 里放的是 onnxruntime-web 的 wasm 文件，由 scripts/build-web.mjs
 *   从 node_modules 复制过来，保证离线可跑（不依赖 CDN）。
 */
export default defineConfig({
  base: "./",
  optimizeDeps: {
    exclude: ["@huggingface/transformers"],
  },
  build: {
    target: "esnext",
    chunkSizeWarningLimit: 4096,
    sourcemap: false,
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
  worker: {
    format: "es",
  },
});
