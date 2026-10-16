import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// #1792：单测只圈定 src 下的 __tests__，避免与 Playwright 的 e2e/*.spec.ts 撞车
export default defineConfig({
  // 与 vite.config 的 resolve.alias 同源语义（"@": src）：
  // 不配则被测模块里所有 `@/` 运行时导入都无法解析
  //（type-only 导入在编译期擦除不受影响，故此前未暴露）。
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url))
    }
  },
  test: {
    environment: "node",
    include: ["src/**/__tests__/**/*.spec.ts"]
  }
});
