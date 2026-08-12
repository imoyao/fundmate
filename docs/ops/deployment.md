---
title: 部署架构规划（主站 / 应用站 / 文档站）
status: v2（2026-08，取代 v1）
owner: 阿垚
---

# 部署架构规划

> 视觉标准见 `docs/design/brand-v1.6.md`，应用站设计语言见 `frontend/design.md` 与 `frontend/design.dark.md`。
> 品牌资产归属与「应用站不部署落地页」决策见 `docs/spec/decisions.md`（2026-08-12 三条）与 issue #918。

## 0. v1 → v2 变更说明（冲突回溯）

v1（2026-08）基于两项已推翻的假设，本版据实修订：

1. **「主站同仓 `marketing/` 目录」假设已不成立**：主站已独立成仓 `imoyao/duoduobei-web`，落地页与品牌母本（`logo-delivery/`）统一在主站维护，应用站（fundmate）仅持本地构建副本。v1 §3/§4 的「单仓库多 project + 根 `vercel.json` rewrite 分发 `/app` `/docs`」整体作废。
2. **「单域名路径拆分」假设已不成立**：实际采用**子域架构**（`duoduobei.com` / `app.duoduobei.com` / `docs.duoduobei.com`），主站与应用站/文档站分仓分域。
3. **「仅 Vercel」假设已不成立**：应用站需 EdgeOne + Cloudflare + Vercel 三平台冗余，文档站 Cloudflare(主) + EdgeOne(备)。v1 全文未覆盖多平台，本版补全。

以下为本版（v2）现行规划。

## 1. 架构总览：子域 + 主站独立仓 + 三平台冗余

| 站点 | 仓库 | 域名 | 技术 | 收录 | 部署平台（优先级） |
|:---|:---|:---|:---|:---|:---|
| 主站（营销/落地页） | `duoduobei-web` | `duoduobei.com` | 静态 HTML/CSS + 原生 JS | 是（强） | EdgeOne(主) → Cloudflare(备) |
| 应用站（APP） | `fundmate` (`frontend/`) | `app.duoduobei.com` | Vue3 SPA（`vite build` → `dist`） | 否（noindex） | **EdgeOne(主) → Cloudflare(备) → Vercel(兜底)** |
| 文档站 | `fundmate` (`docs/`) | `docs.duoduobei.com` | Markdown → VitePress | 是（中） | EdgeOne(主) → Cloudflare(备) |
| 叽咕（投教/小游戏） | `fundmate`（`jigu/`，待确认具体路径） | `jigu.duoduobei.com` | 复用应用站技术栈 | 否（noindex） | EdgeOne(主) → Cloudflare(备) → Vercel(兜底) |
| 后端 API | `fundmate` (`backend/`) | `api.duoduobei.com`（或后端独立项目域名） | APIFlask（WSGI，零重写） | 否 | **仅 EdgeOne Pages Python 函数**（不三平台） |
| 定时抓取 | `fundmate` (`backend/scripts/`) | 无公开域名 | 离线 job（不入站） | 否 | 见 §1.3（混合：本机 + GitHub Action） |
> 2026-08 统一为三平台 EdgeOne→Cloudflare→Vercel 语义后，文档站亦改为 EdgeOne 优先、Cloudflare 备。
> 若仍希望文档站 Cloudflare 为主，改本表 + §3 文档站段落即可（待确认）。

> 应用站未登录访问跳**探市页（`/explore`）免登录体验**，注册后进入 welcome；落地页职能完全移交主站（见 decisions.md 2026-08-12）。

### 1.1 后端部署（仅 EdgeOne，不三平台）

- **宿主**：EdgeOne Pages **Python 函数**（独立后端项目，选中国香港/境外加速区 → **无需 ICP 备案**），APIFlask 原样跑 WSGI 模式，零重写。
- **为什么只部署 EdgeOne**：Cloudflare Pages Functions 是 Workers（JS/Wasm，不原生跑 Python），Vercel 函数对 Python 有限制且不必要；后端仅在能原生跑 Python 的 EdgeOne 部署，前端三平台的流量降级不涉及后端（后端单点）。
- **数据库双库**（容量所迫，非并发所迫）：
  - **用户域 → Supabase（Postgres，免费 500MB）**：账本/组合/持仓/交易/自选/标签等，体量 MB 级。
  - **市场/金融大数据 + 二鸟说 → Turso（libSQL，免费 9GB）**：本地库实测 ~1.8GB，Supabase 装不下，必须拆出。
  - 见 `docs/backend-restructure-edgeone-dualengine.md`（P0–P6 待落地，当前仍单 SQLite）。
- **成本**：EdgeOne 免费 + Supabase 免费 + Turso 免费 ≈ 全免费。
- **域名**：后端独立项目域名（如 `api.duoduobei.com` 或 EO 分配域），不进 Cloudflare LB（后端不降级）。

### 1.2 定时抓取（国内 IP 矛盾 + 不备案约束）

**矛盾**：A 股数据源（东财/天天基金等）需**国内 IP**才能稳定抓取；但用户**不做域名备案**，国内云服务器/函数（绑公网 IP + Web 服务）普遍强制备案，不可行。

**决策（2026-08-12）：不备案**，采用**混合抓取**，抓取与后端解耦（后端 EdgeOne 香港仅承载读取）：

| 数据源类型 | 执行点 | 理由 |
|:---|:---|:---|
| 海外可访问源（二鸟说、部分公开行情） | **GitHub Actions**（海外 runner，定时 07:00/19:00 北京，复用 WeChatRSS 通道） | 免费、可靠、自动化 |
| 强国内源（东财/天天基金等 A 股） | **本机 Windows 任务计划**跑 `backend/scripts/*` 抓取脚本（国内家庭宽带 IP） | 零成本、国内 IP、不备案；关机容忍（数据 T+1 延迟，stale 透传兜底） |

- 抓取值接写 Supabase/Turso，不经过 EdgeOne 后端。
- 不可行项（已排除）：国内云函数（需备案）、纯海外 Action 抓 A 股（限流空数据）、代理/中转（合规风险）。
- **待决策**：本机抓取依赖开机，若需生产级可靠性，后续可评估「不绑域名的纯计算国内资源」或专用抓取服务（仍须规避备案）。当前以成本+合规优先。

### 1.3 叽咕（投教/小游戏）部署与旧站迁移

- **新叽咕** `jigu.duoduobei.com`（统一正式名「叽咕」，非"极谷/基股"）：复用应用站技术栈，**三平台部署**（EdgeOne 主 → Cloudflare 备 → Vercel 兜底），与全站优先级一致。
- **旧叽咕** `jigu.masantu.com`：待数据迁移完成后**下线，或 301 重定向到新叽咕**（`jigu.duoduobei.com`）。迁移前新旧共存，用户数据从旧站导入新站（见 decisions.md 2026-08-12「jigu↔app 共享数据库」）。
- 叽咕与 app 同数据库（用户域 Supabase），登录互通（jigu 登录即 app 用户）。

## 2. 部署优先级与自动降级（核心机制）

**原则**：三个平台都部署同一份产物，但流量按优先级承载；低优先级平台（尤其 Vercel，免费额度有限）仅作容灾兜底，日常不消耗其额度。

**优先级排序（全站统一语义）**：

1. **EdgeOne（主）** —— 用户首选入口，体验最佳。
2. **Cloudflare（备）** —— EdgeOne 不可达时降级。
3. **Vercel（兜底）** —— 前两者皆不可达时的最后防线；正常情况下不承载流量，额度不被日常消耗。

### 实现方式：Cloudflare Load Balancer（推荐）

域名 DNS 托管在 Cloudflare，直接复用 **Cloudflare Load Balancer** 实现优先级 + 健康检查降级（无需迁移 DNS）：

- 每个站点建一个 Load Balancer（如 `app.duoduobei.com` 的 LB）。
- 配置多个 **Origin Pool**，按 Priority 排序：
  - Pool 1（Priority 1）：EdgeOne 主机名（CNAME 指向 EdgeOne 分配给本域的地址）
  - Pool 2（Priority 2）：Cloudflare 自身（本域直接由 Cloudflare 代理）
  - Pool 3（Priority 3）：Vercel 主机名（`*.vercel.app` 或自定义域 CNAME）
- 开启 **Health Check**（HTTP 探测各源站健康），EdgeOne 探测失败 → 自动把流量切到 Priority 2；Priority 2 也失败 → 切 Priority 3。用户无感知，DNS 一次性解析到 LB Anycast IP，降级在 LB 层完成。
- Vercel 仅在 EdgeOne + Cloudflare 同时不可达时才承接流量，免费额度基本不被日常占用。

**代价**：Cloudflare LB 按健康检查探测次数 + 托管域名数计费，小流量处于免费/极低成本区间。

> 备选（不推荐）：纯 DNS 多记录 + 低 TTL 无法做健康检查降级，且会平白消耗 Vercel 额度，违背「省着用」初衷，故不采用。

## 3. 各平台部署要点

### 应用站（`app.duoduobei.com`，Vue SPA）

- **构建**：`frontend/` 下 `vite build` → `dist/`。
- **EdgeOne**：静态资源 + SPA 回退（`/index.html` 兜底路由）；绑定 `app.duoduobei.com`，SSL 自动。
- **Cloudflare**：Pages 或 Workers 静态托管 `dist/`；本域由 Cloudflare 代理即天然承接备线。
- **Vercel**：导入 `fundmate` 仓库，`root=frontend`，build `vite build`，output `dist`；自定义域 `app.duoduobei.com` 仅作为 LB 的 Priority 3 源（日常不解析到它）。
- SPA 路由回退（`history` 模式）三平台均需配置「未知路径 → index.html」。
- 上线 `<meta name="robots" content="noindex, nofollow">`（应用站不参与收录）。

### 文档站（`docs.duoduobei.com`，VitePress）

- **构建**：`docs/` 下 `vitepress build` → `docs/.vitepress/dist`。
- **EdgeOne（主）**：静态托管 `dist/`；绑定 `docs.duoduobei.com`，作为 LB Priority 1 源。
- **Cloudflare（备）**：Pages 托管 `dist/`；作为 LB Priority 2 源。
- 文档站内 `working-notes/`、`srcExclude` 屏蔽内容不参与构建（见 `docs/spec/internal-index.md`），不对外泄露。

### 主站（`duoduobei.com`，静态）

- 仓库 `duoduobei-web`，落地页源 `landing.html`/`about.html`/`story.html` 由 `build-landing.mjs` 生成。
- **EdgeOne（主）** 静态托管；**Cloudflare（备）** Pages/Workers 托管。
- 主站不参与三平台 LB 的 Vercel 兜底（Vercel 额度留给应用站），备线仅 Cloudflare。

## 4. 待办（替代 v1 §7）

- [ ] 三站点各自配置 EdgeOne / Cloudflare / Vercel 部署（应用站三平台全配，其余按上表）
- [ ] 为每个子域建 Cloudflare Load Balancer，按 §2 优先级 + Health Check 串联源站
- [ ] 应用站 `vercel.json` 的 `build:landing` 重定：应用站不再构建落地页，build 改为 `vite build`（落地页已移交主站）
- [ ] 各平台 SPA / VitePress 路由回退配置核对
- [ ] 应用站上线 `noindex`

## 5. SEO 要点（延续 v1）

- 主站/文档站：语义化 HTML、`<meta name="description">`、Open Graph、JSON-LD；装饰动效不挡正文抓取。
- 应用站：`noindex, nofollow`，不参与收录。
- 外链统一指向权威域名（主站 `duoduobei.com`）。
