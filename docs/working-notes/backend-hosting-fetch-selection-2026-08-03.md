# 后端托管与 fetch 落点选型（免费优先，不备案 / 不翻墙）（2026-08-03）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 调研日期：2026-08-03
> 背景：后端放哪未定；想尽量免费；问「EdgeOne 能否跑后端」「腾讯云香港是否太贵」。
> 约束：免费 / 极廉；Python（Flask）；能稳连 A 股（东财 / 腾讯 / 新浪）；不备案；不翻墙。
> 关联：[scheduling-options-research-2026-08-04](./scheduling-options-research-2026-08-04.md)（fetch 落点＝后端托管地，本文定落点，调度文定触发器）。

---

## 一、先纠两个误解

1. **EdgeOne 不只是前端**：EdgeOne Pages＝前端静态 + Node Functions（JS 后端）；Edge Functions＝JS 边缘；**Cloud Functions（云函数）支持 Python / Node / Go 且运行时更长**——后端能跑，但是「无服务器（serverless）」形态，不是常驻 Flask 进程。且腾讯云 **SCF（云函数）原生带定时触发器（cron）**。
2. **「免费无解」是错觉**：真正免费 + 常驻 + Python + 对华友好出口的交集很窄，但有两个站得住的解（见下 A / B）。

---

## 二、候选对比

| 方案 | 形态 | Python | 对华出口 | 费用 | 备注 |
|---|---|---|---|---|---|
| **A. 腾讯云 SCF 云函数 + 定时触发器** | serverless | ✅ | ✅（可选 HK / 上海区） | 免费档 1M 次/月 + 40 万 GBs，日常够 | **首选免费解**；定时器直接替代 APScheduler；默认域名 / 纯定时器 → 不备案 |
| **B. Oracle Always-Free VM（Asia）** | 常驻 VM | ✅（自装） | 视区域（东京 / 新加坡近华，但常满容） | 永久免费、不休眠 | 需信用卡；亚洲区（东京 / 首尔）常无容量，可能只拿到美 / 欧（对华风险） |
| **C. EdgeOne Cloud Functions（Makers）** | serverless | ✅（Python/Flask 原生） | ✅（可选上海 / 香港区） | 前端免费 + 函数按量 | 后端绝佳：原生 Flask→APIFlask 直接可用；但**无原生 cron**，定时需外部触发（见 scheduling-options-research §七） |
| **D. 腾讯云轻量 香港** | 常驻 VM | ✅ | ✅✅（最近） | 入门约 ¥30–60/月（大促更低），2C4G 常规 ~¥480/月 | 出口最好但非免费；「太贵」因 HK 国际带宽贵 |
| **E. Render / Railway / Fly（海外）** | serverless / VM | ✅ | ⚠️（美区风险） | 免费档 / 低价 | 美区连 A 股有风险（见 scheduling-options-research §五） |

---

## 三、推荐栈（免费 + 不备案 + 不翻墙 + 对华友好）

- **前端**：**EdgeOne Pages**（免费，全球 CDN，适合 Vue SPA）——EdgeOne 跑前端正是它的强项。
- **后端 API + 定时任务**：**腾讯云 SCF（云函数，Python）+ 定时触发器**。
  - 免费额度覆盖日常（每日几次聚合 + NAV 同步 + 少量 API 调用远在 1M 次/月内）。
  - Python 可包裹现有 **APIFlask（Flask 子类）**，经 API 网关或函数 handler，不必大改架构。
  - 定时器直接替代 APScheduler（无需常驻进程）。
  - 选 **HK 或上海区** → 对华出口极佳；用默认 `*.scf.tencentcs.com` 域名 / 纯定时器触发 → **不备案**。
  - **备选后端：EdgeOne Cloud Functions（Makers）**——Python 原生支持 Flask / APIFlask、可选上海 / 香港区，前端 Pages + 后端同平台更省事；但**无原生 cron**，定时需用外部调度器（SCF 定时器 / 家里机 cron / EasyCron）触发其 `/api/cron/*` 端点（见 [scheduling-options-research-2026-08-04](./scheduling-options-research-2026-08-04.md) §七）。
- **DB / Auth**：维持 **Supabase**（已用）。
- **连通**：SCF 与 Supabase 走 HTTPS；抓数在腾讯云近华出口完成，不受 GFW 影响。

> 这一组合 ＝ **全免费 + 无服务器 + 无备案 + 无翻墙 + 对华友好出口**，正是你以为「没有」的解法。

> 落地步骤见 [deployment-implementation-guide-2026-08-04](./deployment-implementation-guide-2026-08-04.md)（确定性方案：SCF 后端 ＋ 原生定时触发器，前端 EdgeOne Pages；经 2026-08-04 官方文档复核）。

---

## 四、何时才需要买服务器

若 SCF 免费额度不够（高频 / 大计算），或你想保留「常驻 Flask + APScheduler 进程」不改架构，再考虑：

- **廉价常驻**：腾讯云轻量香港入门型（~¥30–60/月）——出口最稳，但花钱。
- **免费常驻**：Oracle Always-Free（亚洲）——免费永久，但亚洲容量靠抢 + 需信用卡。

---

## 五、代码改造量评估（SCF 不是推倒重来）＋ Cloudflare Containers 评估

### 5.1 SCF 到底要改多少代码？（APIFlask 同样无需重构）

**结论：不是推倒重来，是「适配入口 ＋ 去 APScheduler ＋ 打包依赖」。** 多多贝后端是 **APIFlask**——它是 Flask 的直接子类，仍是标准 WSGI 应用；腾讯云 SCF **Web 函数**的官方 Flask 模板本质是用 gunicorn 包住一个 WSGI `app`，所以「**无需改动业务代码，一键部署**」（已搜证）对 APIFlask 同样成立。

**为什么 APIFlask 不用重构**：

- APIFlask 的 `@app.get` / `@app.post` / `@app.input` 等装饰器在运行时只是给底层 Flask 注册路由并生成 OpenAPI，**最终都落到标准 Flask 路由表**，gunicorn 起的是同一个 WSGI 对象。
- 部署时 SCF 模板只需在 `wsgi.py` 里 `from app import app`（APIFlask 实例），再 `gunicorn app:app`，与 Flask 完全一致；你现在的 `app.py` / 工厂函数几乎不用动。
- 唯一可选优化：APIFlask 默认注入 `/docs` `/openapi.json` 等路由，在 SCF Web 函数下仍是正常 HTTP 路由、不影响运行；若不想暴露，关 `app.spec` 即可。

**保留不动（核心）**：

- 所有 `model` / `service` / `fetcher` / `calculator` / `route` —— 原样保留。
- `BiasJob` / 净值 job / 温度聚合 等作业函数 —— 原样保留。

**真正要动的（都在边缘）**：

1. **入口**：Web 函数用官方 Flask / APIFlask 模板 / `scf_bootstrap` 起 gunicorn，模板代劳，几乎零改。
2. **定时任务**：把各作业包成 3 行 `def handler(event, context): run_xxx_job()`，绑**定时触发器**；**APScheduler 直接删掉**（被定时器替代，是简化不是重写）。
3. **依赖打包**：SCF 需把依赖打进层 / zip。**akshare 很重**（传递依赖多），塞进 SCF 可能超体积 / 拖冷启——但我们已经在减少 akshare 依赖（bias 改直连、router 主推直连上游，仅留 xalpha 净值 + 少量元数据），正好对齐。把 akshare 压下去，包就瘦了。
4. **无常驻进程**：任何"进程内常驻缓存 / 调度"假设要改；状态在 Supabase（好），`tempfile` 缓存是单次调用内（可接受）。
5. **超时**：SCF 默认超时可能短（默认几秒～60s，最高可配到 900s）；每日聚合抓 5 源 ＋ 净值可能 >60s，需把超时调高。
6. **冷启 / 连接复用**：Python 冷启秒级，每日低频无碍；暖实例可复用 SQLAlchemy engine（小优化）。

> 真实工作量 ≈ 「加入口文件 ＋ 把 N 个 job 包成 handler ＋ 调依赖 / 超时配置」，不是重写业务逻辑。最大隐患是 **akshare 打包体积**——而它恰是我们在削减的。

### 5.2 Cloudflare Containers 能跑我们的 Docker / APIFlask 吗？

**能，但不适合本项目的免费 ＋ 对华目标。**

- 事实：Cloudflare **Containers** 于 2025-07 进入 public beta，可在 Cloudflare 全球网络跑 Docker 容器，与 Workers / Durable Objects 集成、scale-to-zero（休眠）（已搜证）。你的 Flask Docker 镜像**技术上能跑**。
- 但三点不匹配：
  1. **不免费**：Containers 按 vCPU / GB 秒计费，没有 Oracle 那种永久免费档；免费目标不达。
  2. **对华出口不确定**：Cloudflare 在中国大陆本就时好时坏（靠合作方节点），且容器跑在 Cloudflare 全球网络、不能像 VM 那样指定单一近华区域；容器出站连东财 / 腾讯不如腾讯云 HK / 上海区稳。
  3. **仍是 serverless**：scale-to-zero，进程不常驻，APScheduler 同样不能直接用（需 Cron Triggers 调容器端点），与 SCF 同构。
- 结论：Cloudflare Containers 适合「以后想用 Docker 部署且愿付费」的场景；**当前免费 ＋ 对华友好，仍首选 SCF（Web 函数 ＋ 定时触发器）**。

## 六、边界

- **事实**：EdgeOne Cloud Functions 支持 Python / Node / Go（搜证）；Oracle Always-Free 永久免费不休眠、亚洲常满容（搜证）；腾讯 HK 贵、内地需备案（搜证）；**SCF Web 函数部署 Flask / APIFlask 无需改动业务代码**（搜证，APIFlask 为 Flask 子类、同属标准 WSGI）；**Cloudflare Containers 2025-07 public beta 可跑 Docker 但付费且对华不确定**（搜证）。
- **推断**：SCF 定时器 ＋ 默认域名可规避备案；SCF HK / 上海区对华出口优于美区；akshare 打包体积是 SCF 主要隐患、恰与减 akshare 方向一致。
- **未知**：SCF 精确免费额度与区域可用性；Oracle 亚洲实例可抢性；SCF 冷启动 / 连接 Supabase 延迟；Cloudflare Containers 当前精确计费与是否 GA。
