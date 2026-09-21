import { defineConfig, devices } from "@playwright/test";

/**
 * 前端 E2E 配置（#1568）。
 *
 * 用途：给「路由守卫 ↔ permission store ↔ 布局组件」这类**跨层联动**缺陷建回归网——
 * 这类缺陷单测覆盖不到（要 mock 掉守卫与 store，等于把出问题的那层挖掉），
 * 首个用例即 #1565（首次从探市首屏跳转进自选页后侧边栏不渲染，由 #1566 修复）。
 *
 * 三条刻意的取舍：
 * 1. **自带 dev server（端口 8849，不用 8848）**：与手工调试用的 dev server 互不打扰，
 *    且 `reuseExistingServer: false` 保证每次都是干净的、可复现的构建环境。
 * 2. **不依赖后端**：用例只断言「路由与侧边栏渲染」，后端接口 404 / 连接失败不影响结论
 *    （会话由 cookie 注入，见 e2e/support/session.ts）。
 * 3. **不进 per-PR 门禁**：浏览器 ~130MB + 一次完整构建，per-PR 跑不划算；
 *    由 .github/workflows/e2e.yml 的 workflow_dispatch / nightly 触发，手工命令 `pnpm test:e2e`。
 */

const PORT = Number(process.env.E2E_PORT ?? 8849);
const BASE_URL = `http://127.0.0.1:${PORT}`;

// E2E 用的**假** Supabase 项目：@supabase/ssr 只要 URL/anon key 非空就能建客户端，
// 会话由测试注入的 cookie 提供，全程不打真实 Supabase（也不需要任何真实凭据）。
const E2E_SUPABASE_URL =
  process.env.VITE_SUPABASE_URL ?? "https://e2etest.supabase.co";
const E2E_SUPABASE_ANON_KEY =
  process.env.VITE_SUPABASE_ANON_KEY ?? "e2e-anon-key";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // 共用一个 dev server：串行执行，避免并发用例互相影响
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["github"]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure"
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `pnpm exec vite --port ${PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      // 仓库只入库 .env.production / .env.staging（.env.development 被刻意忽略，见 .env.example 的 #1028 说明），
      // 因此全新 worktree / CI 上跑 dev server 必须显式给出这几个值——否则 `VITE_PUBLIC_PATH` 为
      // undefined，platform-config.json 会请求到 `undefinedplatform-config.json`（404）→ 配置为空
      // → 布局主题 hook 取到 undefined 直接抛错（实测：`Cannot read properties of undefined (reading 'replace')`）。
      VITE_PUBLIC_PATH: "/",
      VITE_APP_ENV: "development",
      VITE_HIDE_HOME: "false",
      VITE_CDN: "false",
      VITE_SUPABASE_URL: E2E_SUPABASE_URL,
      VITE_SUPABASE_ANON_KEY: E2E_SUPABASE_ANON_KEY,
      // 钉住 hash 模式：与生产 .env.production 一致，深链形态确定（/#/explore）
      VITE_ROUTER_HISTORY: "hash"
    }
  }
});
