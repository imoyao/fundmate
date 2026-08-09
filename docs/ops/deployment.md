---
title: 部署架构规划（主站 / 工具站 / 文档站）
status: v1（2026-08）
owner: 阿垚
---

# 部署架构规划

> 本文定义多倍贝三套界面的部署拓扑与仓库布局。视觉标准见 `docs/design/brand-v1.6.md`，工具站设计语言见 `frontend/design.md` 与 `frontend/design.dark.md`。

## 1. 决策：单域名 + 路径拆分

早期采用**单域名 `duobeibei.com`**（www 为规范名），按路径拆分三套界面，而非多子域名。

理由：

- **SEO 集中度**：单一域名积累权重，避免主站与工具站分散权威。
- **早期运维**：一条 DNS、一份证书、一个域名权威，最省心。
- **工具站本就不参与收录**：Vue SPA 属登录后应用，应 `noindex`，因此"SEO 分散"无实质损失；需集中权威的只有主站营销内容。

> 注：标准 SaaS 的 `app.` 子域名解法适合有多产品线、需独立品牌的团队。个人单产品项目早期不必；待产品矩阵扩张再考虑子域名。

## 2. 三套界面

| 路径 | 站点 | 技术 | 构建 | 收录 |
|:---|:---|:---|:---|:---|
| `/` | 主站（营销/落地页） | 静态 HTML/CSS + 原生 JS | 免构建 / 11ty·Astro | 是（强） |
| `/app` | 工具站 | Vue3 SPA（`frontend/`） | `vite build` → `dist`（base `/app`） | 否（noindex） |
| `/docs` | 文档站 | Markdown → VitePress | `vitepress build` | 是（中） |

## 3. 仓库布局

- `frontend/` → 工具站（Vue 应用，构建 base 设为 `/app`）
- `marketing/` → 主站静态（迁入 `landing.html` + `demo-liquid.html` + CSS）
- `docs/` → 文档站（补 VitePress 配置后静态产出）
- 根目录通用 `vercel.json` 改为路由配置（见 §4），不再作纯静态文件服务

## 4. Vercel 配置（单仓库多项目 + 路由）

单仓库内多 project，各自 root 与 build；根 `vercel.json` 用 rewrite 分发路径：

```json
{
  "version": 2,
  "rewrites": [
    { "source": "/app/:match*", "destination": "https://<app-project>.vercel.app/:match*" },
    { "source": "/docs/:match*", "destination": "https://<docs-project>.vercel.app/:match*" }
  ]
}
```

要点：

- 主站项目：根目录 = `marketing/`，静态输出。
- 工具站项目：root = `frontend/`，build `vite build`，output `dist`，`base: '/app'`。
- 文档站项目：root = `docs/`，build `vitepress build`，output `docs/.vitepress/dist`。

## 5. SEO 要点

- 主站：语义化 HTML、`<meta name="description">`、Open Graph、JSON-LD（Organization / SoftwareApplication）；液体动效为装饰层，正文为真实文本，不影响抓取。
- 工具站：`<meta name="robots" content="noindex, nofollow">`，不参与收录。
- 单一域名权威集中，外链统一指向 `https://www.duobeibei.com/`。

## 6. 暗色模式边界

- 主站：浅色优先，不提供切换（见 `brand-v1.6.md` §3.3）。
- 工具站：完整暗色（`frontend/design.dark.md`，`data-theme` 驱动）。

## 7. 待办

- [ ] 将 `landing.html` / `demo-liquid.html` 迁入 `marketing/`
- [ ] `frontend/` 构建 base 改为 `/app`
- [ ] `docs/` 补 VitePress 配置
- [ ] 根 `vercel.json` 替换为 §4 路由配置
- [ ] 工具站上线 `noindex`
