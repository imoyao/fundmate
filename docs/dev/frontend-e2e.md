---
title: 前端 E2E（Playwright）
status: v1（2026-09-18，#1568 落地）
owner: 阿垚
---

# 前端 E2E（Playwright）

> 决策与首例交付见 issue **#1568**（#1565 的回归网）；本文件是**用法与边界**的单一入口。
> 后端测试另见 `docs/dev/`（pytest，单进程）与 `.github/workflows/ci.yml`。

## 1. 为什么要 E2E（而不是组件单测）

前端长期**零测试框架**，像 #1565（首次从探市首屏跳转进自选页后侧边栏不渲染）这类缺陷
落在「**路由守卫 ↔ permission store ↔ 布局组件**」的联动缝里：

- 组件级单测要把它跑起来，必须 mock 掉守卫与 store——**正好把出问题的那层挖掉**；
- 而这类缺陷的现场是「真实跳转 + 真实菜单组装 + 真实 CSS 加载态」，只有真浏览器能复现。

故选 **Playwright（方案 A）**，而非 Vitest 组件测试（方案 B）。这也是业界对
「端到端回归网」的默认选择：一个运行时同时覆盖路由、存储、渲染与网络失败路径。

## 2. 怎么跑

```bash
cd frontend
pnpm test:e2e          # 全部用例（自带 dev server）
pnpm test:e2e:ui       # 调试用 UI 模式（可看 trace / 逐步回放）
pnpm exec playwright test e2e/explore-sidebar.spec.ts -g "对照组"   # 只跑一条
```

- **自带 dev server**：端口 **8849**（刻意避开日常调试的 8848），`reuseExistingServer: false`
  ——每次都是干净环境，不受你手工起的 dev server 影响；
- **不依赖后端**：用例只断言路由与渲染，后端接口 404 / 连接失败不影响结论；
- **不依赖真实 Supabase**：会话由 cookie 注入（见下），用的是一个假项目
  `https://e2etest.supabase.co`，**不会**碰到任何真实用户数据；
- 首次运行若报缺浏览器：`pnpm exec playwright install chromium`（本机缓存里有可跳过）。

## 3. 会话注入（免真实登录的关键）

`@supabase/ssr` 的浏览器客户端把会话存在 cookie 里，`supabase.auth.getSession()` 直接读它，
所以「已登录」可以用一个 cookie 造出来（`e2e/support/session.ts`）：

| 项 | 值 |
|---|---|
| cookie 名 | `sb-<project-ref>-auth-token`（project-ref = Supabase URL 主机名第一段，即 `e2etest`） |
| cookie 值 | `base64-` + base64url(会话 JSON) |
| 会话要点 | `expires_at` 取未来时间（否则 supabase-js 会尝试 refresh 打网络）；`user_metadata.roles` 供守卫的权限判断 |

> ⚠️ 这两条格式来自**读 `@supabase/ssr` 源码**（`BASE64_PREFIX` / `combineChunks`：值 URI 编码后
> < 3180 字符时用 base 名，不分块），不是猜的；升级该包时若注入失败，先回来核对这里。

## 4. 环境变量：为什么 E2E 必须显式给 dev 变量

仓库只入库 `.env.production` / `.env.staging`，**`.env.development` 被刻意忽略**
（见 `frontend/.env.example` 的 #1028 说明）。因此全新 worktree / CI 上直接起 dev server 会缺
`VITE_PUBLIC_PATH`，`platform-config.json` 会被请求成 `undefinedplatform-config.json`（404）→
配置为空 → 布局主题 hook 取到 `undefined` 直接抛
`Cannot read properties of undefined (reading 'replace')`，页面白屏、侧边栏自然也不存在。

`playwright.config.ts` 的 `webServer.env` 因而显式注入：
`VITE_PUBLIC_PATH=/`、`VITE_APP_ENV=development`、`VITE_HIDE_HOME=false`、`VITE_CDN=false`、
`VITE_SUPABASE_URL/ANON_KEY`（假项目）、`VITE_ROUTER_HISTORY=hash`（与生产一致，深链形态确定）。

## 5. 现在覆盖了什么

`e2e/explore-sidebar.spec.ts`（#1565 回归网）：

1. 已登录首屏落在 `/#/explore` → 点「前往自选页」→ 断言 URL 到 `/#/watchlist`、
   **侧边栏菜单项 > 0**、**无 `el-loading-mask` 常驻**；
2. 对照组：首屏直达 `/#/watchlist` 的菜单项数量与「先探市后跳转」**一致**；
3. 反向保护：未登录访问 `/#/watchlist` 仍被守卫拦到 `/#/login`（防止菜单兜底把权限放水）。

**证伪能力（有效性证据）**：临时回滚 #1566 的守卫修复后，用例 1 / 2 **必然失败**
（菜单项 0），恢复后 **3/3 通过**。一条不能证伪的回归网等于没有——新增用例请一并证明这一点。

## 6. CI 编排与成本边界

- `.github/workflows/e2e.yml`：**`workflow_dispatch` + 每夜 19:00 UTC**（北京 03:00），
  **不进 per-PR 门禁**（理由：Chromium ~130MB + 完整 dev server，per-PR 性价比低，
  而 merge 门禁 `ci.yml` 的定位是快速红灯）；
- 浏览器走 `actions/cache`（key 跟 `@playwright/test` 版本），命中后不再下载；
- 若将来要把某类 PR 纳入，建议**按 label 触发**（如 `e2e`）而非全量开——改工作流时把理由写进注释。

## 7. 加新用例的约定

- 放 `frontend/e2e/*.spec.ts`，共享工具放 `frontend/e2e/support/`；
- **只断言外部可观察行为**（URL / 可见元素 / 计算样式 / 请求），不碰 Pinia 内部状态——
  碰内部状态就又回到「把出问题的那层挖掉」的老路；
- 依赖后端数据的场景：要么用 `page.route` 打桩，要么把断言限定在不依赖数据的部分
  （本轮就是后者）；
- 单条用例应能在 15s 内跑完；超时说明它在等外部依赖，先修依赖而不是加 timeout。
