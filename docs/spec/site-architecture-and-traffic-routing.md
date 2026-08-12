---
title: 站点架构与导流方案
---

# 站点架构与导流方案

> 本文档固化多倍贝（duoduobei.com）旗下各站点的职责边界、导流顺序、身份互通与数据隔离决策。
> 历史讨论来自 fundmate issue #914 / #915 / #916，已整合于此，原 issue 关闭并关联本文档。

## 一、域名与站点总览

主域名：**duoduobei.com**（多多贝）。各站点均为其子域或子路径：

| 站点 | 地址 | 性质 | 技术形态 | 职责 |
|---|---|---|---|---|
| 主站（营销站） | `duoduobei.com` | 营销/品牌层 | 纯静态（landing/about/story + H5） | 品牌展示、流量入口、导流 |
| 投资人格测试 H5 | `duoduobei.com/personality` | 主站子路径 | 纯静态单页 | 引流小游戏，导用户去 app |
| 应用站 FundMate | `app.duoduobei.com` | 应用层（终点） | Nuxt/Vue 前端 + 后端 | 用户注册/登录/使用产品，**最终落脚地** |
| 探市 | `app.duoduobei.com/explore` | app 子路由 | app 内路由（免登录沙盒） | 研究页，引流到 app 转化 |
| 极谷（新） | `jigu.duoduobei.com` | 过渡产品线 | Next.js 静态导出 | 基金估值追踪，过渡期可用产品 |
| 极谷（旧） | `jigu.masantu.com` | 待下线 | 旧部署 | 旧用户数据，计划下线 |
| FeedLog 反馈站 | `feedback.duoduobei.com` | 独立反馈平台 | Nuxt 4 + Postgres | 收集用户反馈/路线图/变更日志 |

## 二、三层结构

```
                     duoduobei.com  ── 营销层（主站 + 人格测试 H5）
                          │ 导流入口
                          ▼
     ┌──────────────────────────────────────────────────┐
     │   app.duoduobei.com  ── 应用层（终点 / FundMate）   │
     │   /login /profile /temperature /explore(探市)       │
     └──────────────────────────────────────────────────┘
                          ▲
     jigu.duoduobei.com  ── 平行过渡产品线（保留，不二次开发）
     feedback.duoduobei.com ── 独立反馈平台（独立数据库）
```

- **营销层**：只做引流，不产生核心价值。
- **应用层**：所有流量最终落点，用户在此注册/登录/转化。
- **过渡产品线（极谷）**：现在能用就留着，不投精力二次开发，未来退役、流量归并主站导流链。

## 三、导流顺序

```
外部流量 → 主站(landing)
   ├─→ 人格测试 H5(/personality) ──→「使用产品」→ app.duoduobei.com
   └─→ 探市入口(未来主站挂 /explore 链接) → app.duoduobei.com/explore

极谷(jigu.duoduobei.com) ──（保留过渡）→ 未来退役 → 流量归并主站
```

- 极谷**不排入「导流到 app」的链路**作为一环，它是平行产品线；退役时其域名 301 到主站对应入口。
- 「免费开始 / 使用产品」主按钮直接跳 `https://app.duoduobei.com`。

## 四、身份互通与数据隔离

### 4.1 极谷 ↔ app（同主域，必选 SSO）

- 极谷与 app **指向同一个 Supabase project**（改 env 不改代码）。
- 用户登极谷 = 在 app 注册，反之亦然；`user_id` 隔离，天然共享用户池。
- 跨子域会话：用 `@supabase/ssr` 把 session 存到 `.duoduobei.com` 父域 cookie，实现「登一个、全站登录」。
- GitHub 快捷登录：只需**一个 GitHub OAuth App**，回调填 Supabase 的 `auth/v1/callback`；在 Supabase Auth 的 Site URL / Redirect URLs 中把 `jigu.duoduobei.com` 与 `app.duoduobei.com` 都登记。

### 4.2 FeedLog 反馈站（独立数据库，可选 JWT 桥 SSO）

- FeedLog 用**独立 Postgres**（Supabase Postgres / Neon / 自有），不占主 Supabase 免费额度（500MB）。
- 数据隔离诉求满足；反馈数据不进主库。
- 身份打通：FeedLog 内置 **JWT SSO 消费端**（`/api/sso/jwt`，HS256 + `FEEDLOG_SSO_SECRET`）。主站（app）作为签发方，对已登录用户预签 JWT（payload: email/name/picture/exp），用户点链接即可带身份进入 FeedLog 自动登录。
- 该 SSO 为**可选集成**：不接也能匿名提交反馈；接了体验更好。**不需要 Supabase 层 SSO**。

### 4.3 结论

- SSO 必选范围 = **jigu ↔ app**（Supabase 父域 cookie）。
- FeedLog 走独立数据库 + 可选 JWT 桥，**不纳入 Supabase SSO**，复杂度可控。

## 五、极谷新旧迁移策略

### 新极谷（jigu.duoduobei.com，指向主 Supabase）

- 复杂度低：与 app 同 project，用户/数据天然共享，无需迁移。
- 上线新极谷，同步下线 `jigu.masantu.com`。

### 旧极谷（jigu.masantu.com，旧 Supabase project）

- 真正复杂度来源：独立 project + 已有用户/数据。
- **推荐策略（显式迁移为主）**：不硬合并 `auth.users`（避免密码哈希/冲突噩梦）；旧站发通知引导用户去新站用同邮箱注册/魔术链接登录；后台脚本按 `user_id` 复制该用户的业务数据到主 project。
- 旧站保留只读一段时间作为窗口期，再 301 到新极谷或主站。
- 跨子域 cookie 方案就绪后，新极谷与 app 登录互通自然成立；旧用户迁过来后同样适用。

## 六、部署形态

- 主站 / 人格测试 H5：静态站，部署到 **EdgeOne Pages**（仓库 `duoduobei-web`，根目录即产物，`/personality` 为子路径）。
- 极谷：Next.js `output: export` → `out/`，EdgeOne Pages，绑定 `jigu.duoduobei.com`。
- app：FundMate 前端，EdgeOne，绑定 `app.duoduobei.com`。
- FeedLog：Nuxt 4，部署到 Cloudflare Workers / Vercel / Docker，绑定 `feedback.duoduobei.com`，独立 Postgres。
- 本文档站：VitePress，部署到 `docs.duoduobei.com`（本仓库 `docs/`）。

## 七、待决事项

- `duoduobei.com` 主站备案与 EdgeOne 国内加速进展。
- 极谷退役具体节奏（先保留过渡）。
- FeedLog JWT 桥是否在首版接入（建议二期）。
- 主 Supabase 的 GitHub Provider 与跨子域 cookie session 落地（阻塞「导流后自动登录」最后一公里）。
