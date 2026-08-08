# 免费云服务清单（2026-08-09）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。**不存放任何密钥**——只记服务用途、免费额度、风险与替代方案。凭据一律只在 `.env` / 本地密钥管理。
> 维护规则：新增/变更/废弃云服务时同步更新本表；凭据密钥不入库。

## 总表

| 服务 | 用途（fundmate） | 免费额度（2026-08 实测/官方） | 风险 / 限制 | 替代方案 |
|---|---|---|---|---|
| **Supabase** | 用户域：Auth（JWT 验签）+ Postgres 用户账本缓存；身份认证与家庭核心账本云端权威 + 本地 SQLite 缓存（D3 修订后） | 免费层：500MB 数据库、50k MAU、50 万次 API 调用 | **7 天不活动暂停实例** → 保活 `supabase-keep-alive.yml`（每 6 天 ping `/auth/v1/settings`，不触东财，无 403 风险）；免费层无 PITR/备份 | 自建 Postgres（成本高）；Turso 只做市场域，不能替代用户域 |
| **Turso** | 市场域：基金净值/估值等大数据（免费 9GB），libsql 方言，SQLAlchemy 兼容 | 免费 9GB 存储、140M 行读取/月、42 天历史（时间旅行） | 冷启动（空闲后首请求慢）；SQLite 方言子集 | Cloudflare D1 —— **已否决**（无 SQLAlchemy 方言、绑 JS 生态、单线程写） |
| **EdgeOne**（腾讯云） | 边缘部署：Pages 托管（Python/WSGI 零重写跑 APIFlask）+ SCF 定时触发器（抓取任务）+ CDN；香港节点**只读不抓东财** | Pages 免费流量；SCF 每月免费调用/GBs 额度 | 定时触发器**无需备案**（平台内部调度、无公网入站）；香港节点到东财链路受限 | Vercel（East Asia 节点；但 Vercel 服务器 IP 可能被东财封） |
| **火山引擎 Ark** | OCR 截图导入（doubao vision，seed 档） | 新用户一次性 50 万 tokens×30 天 ≈ **仅 500 次调用**（只够试用，不够生产） | 真计费：0.8 元/M 输入 + 8 元/M 输出；单次 ≈ 0.0037 元（600 in + 400 out）；1000 用户×5 次/天顶格 ≈ 555 元/月，现实 20% ≈ 74 元/月；缓存命中 1.2 元/M 可省 80% | 本地 tesseract.js（客户端 OCR，基估宝用，精度低）；付费升级档 |
| **Resend** | 邮件（登录 OTP / 通知） | 免费 100 封/天（约 3000 封/月） | 免费层每日配额、发送域名需验证 | Supabase Auth 自带邮件（受限）、SMTP 自建 |
| **GitHub Actions** | CI（lint/test/build）+ 保活 workflow | 公共仓库免费；私有仓库 2000 分钟/月 | **禁止跑东财抓取任务**（出口 IP 被东财封，`eastmoney-antiscrape-2026-08-05.md` 实证为 IP 级封禁） | EdgeOne SCF 定时触发（抓取）、Windows 任务计划程序 schtasks（过渡期增量） |
| **Vercel** | 落地页部署（`vercel.json` 构建时 `pnpm run build:landing`） | Hobby 免费版（带宽/构建有限额） | 服务器 IP 可能被东财拦截（若未来落地页需代理行情）；Hobby 无团队协作 | EdgeOne Pages、Cloudflare Pages |

## 分工原则（与 `backend-restructure-edgeone-dualengine.md` 对齐）

- **用户域**（身份、家庭账本）→ Supabase 云端权威 + 本地 SQLite 缓存；**市场域**（净值/估值大数据，本机实测 868MB）→ Turso。
- **高频估值**（30s/1m/90s 轮询，≈24 万次/天）→ **前端直连行情源**，不走任何云（成本黑洞，见 explore-watchlist-replan §9.1）。
- **抓取任务**：EdgeOne SCF 定时触发器（首选）> Windows 任务计划程序（过渡期）；**GitHub Actions 禁止**。

## 变更记录

- 2026-08-09：初建（来源：`backend-restructure-edgeone-dualengine.md`、`eastmoney-antiscrape-2026-08-05.md`、会话决策墙）。
