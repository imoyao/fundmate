import { defineConfig } from "vitest/config";

// #1792：单测只圈定 src 下的 __tests__，避免与 Playwright 的 e2e/*.spec.ts 撞车
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/__tests__/**/*.spec.ts"]
  }
});
