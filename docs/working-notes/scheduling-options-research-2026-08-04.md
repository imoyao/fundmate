# 定时调度方案调研（无云服务器，免费优先）（2026-08-04）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 调研日期：2026-08-04
> 背景：功能借鉴分析 flagged「市场温度是空模型」——`thermometer/fetchers.py` 写好但无 job 落库；用户确认下一步重点＝让调度跑起来。
> 约束：暂不买云服务器；已有 free overseas deploy；数据是 A 股（东财 / 腾讯 / 新浪 / 天天基金）。
> 关联：[bias-datasource-replacement-2026-08-03](./bias-datasource-replacement-2026-08-03.md)、[datasource-priority-plan-2026-08-03](./datasource-priority-plan-2026-08-03.md)。

---

## 一、先定一个设计原则：调度 与 计算 解耦

**不要让"定时器"去跑 Python 重活。** 正确姿势：

- **计算**（抓数据 / 落库）留在 Flask 应用里，封装成可触发单元（`job` 函数 或 `/api/cron/*` 端点）。
- **调度器**只负责在正确时间"喊一声"（HTTP 调用 / 调 Edge Function）。

好处：计算在你已有的海外部署上跑（它本就能连东财/腾讯），调度器可随时替换、不绑死平台、不怕 60 天禁用。

---

## 二、候选方案对比（按真实约束）

| 方案 | 适用 | 优点 | 风险 / 约束（已核实） |
|---|---|---|---|
| **A. APScheduler 进程内**（本地 + 部署同进程） | 部署不休眠时首选 | 零新基础设施，代码最简，任务状态内存可见 | 部署若休眠（Render free）则随进程死；多实例会重复跑（需加锁） |
| **B. GitHub Actions 定时**（curl 你的端点） | 每日低频、零成本 | 不用买服务器，私有库含免费额度 | **已核实：仓库 60 天无活动会自动禁用定时 workflow**（搜到多个真实例）；触发为 best-effort 不保证准点；runner 在 Azure 美/欧，连 A 股端点可能慢/被限（未实测，需验证）；每次冷启动 |
| **C. Supabase 定时 Edge Function → curl 端点** | 已用 Supabase | 复用现有基建，亚洲区域近源 | Edge Function 是 TS 非 Python，只能做"触发器"调你的端点；免费档限调用次数；`pg_cron` 需 Pro 计划（待确认） |
| **D. 外部 cron 服务**（cron-job.org / EasyCron 免费档）→ curl 端点 | 部署休眠时的唤醒+触发 | 专做定时、简单可靠、免费档够每日几次 | 依赖第三方；端点必须鉴权防滥用 |
| **E.【反转】先别选调度器，先确认"部署会不会休眠"** | — | 决定 A 是否可直接用 | 若已用 Fly/Railway（不休眠）→ A 一步到位；若 Render free → 必须 B/C/D 触发 |

---

## 三、推荐落地路径

1. **本地**：APScheduler（`BackgroundScheduler`）+ `SQLAlchemyJobStore`（存 Supabase Postgres）跑通 job，验证 fetchers 真能落库。（你已有 `BiasJob` / 净值 job / 温度聚合的代码骨架）
2. **判定现有 free overseas deploy 是否休眠**：
   - **不休眠（Fly / Railway）** → 生产直接 APScheduler 进程内，加 DB/Redis 锁防重复。✅ 最简。
   - **休眠（Render free）** → 部署只做"被调用时跑"，由外部触发：首选 Supabase Edge cron（C），备选 GitHub Actions（B，加 keepalive commit 防 60 天禁用）或 cron-job.org（D）。
3. **所有 job 封装为 `/api/cron/{name}`** + 共享 secret header，幂等，带 `last_run` 记录，便于监控与手动补跑。
4. 把 `router.health()`（已在 [datasource-priority-plan-2026-08-03](./datasource-priority-plan-2026-08-03.md) 定义）接入 job 结束告警。

---

## 四、对你两个具体问题的直接回答

- **本地用 APScheduler？** ✅ 非常适合本地开发，也适合"部署不休眠"的生产。建议加持久化 jobstore。
- **远端用 GitHub Actions？** ⚠️ 能，但只把它当**触发器**（curl 你的端点），别让它 `pip install` 跑 Python；且必须处理 **60 天禁用**（随便提交 / keepalive workflow）与 **A 股端点可达性**（先在 Actions runner 实跑一次验证）。不是最稳的主力，可作备份。
- **更好实现？** ＝ **调度/计算解耦** ＋ **按部署是否休眠选触发器**；已用 Supabase 就让它当触发器最省事，不必新买服务器。

---

## 五、针对「美区 runner 连 A 股」的补充解法（不备案 / 不翻墙 / 尽可能免费）

> 核心认知：**真正要优化的是「fetch 发生在哪里」，不是「scheduler 在哪里」。** 调度（curl 一下）从任何地方都稳；只有「抓东财/腾讯」这一步需要对中国友好的出口。且东财/腾讯这些 JSON 端点本身不是 GFW 硬墙，风险主要是**数据中心 IP 被限流/偶发拦截**，而非连不通。

解法（按「免费 + 不备案 + 不翻墙」排序）：

1. **家里常驻机（NAS / 树莓派 / 旧电脑）跑 APScheduler** —— 最稳最省。家庭宽带＝中国出口，东财/腾讯原生响应；个人使用不备案、不翻墙、零服务器费。前提：24h 开机机器 + 家用上行稳定。直接消除风险。
2. **GitHub Actions 只当触发器，计算留在本就有证明的部署上** —— 你现有 free overseas deploy 若能展示行情，说明它已能连东财/腾讯。让 GitHub US runner 只做 `curl https://yourapp/api/cron/x`（US→你的 app HTTPS 很稳），真正抓数仍在你的 app（亚洲/家用）跑。免费 cron 保留，且 fetch 永不在美区发生。
3. **把计算迁到近中国的免费/低价 PaaS（HK / 新加坡 / 东京）** —— 如 Fly.io 选 `hkg`/`sin`/`nrt` 区域。地理近中国→延迟低、被拦概率远低于美区 Azure；海外节点不备案、不翻墙。Fly 免费档（或小额）即可选区域。
4. **降低对中国端点的依赖：在 router 里把海外友好源（Yahoo / Stooq，经 yfinance）设为优先 tier** —— 多数 A 股股票/ETF/宽基在 Yahoo 有对应代码（如 `600519.SS`、`000300.SS`、`000001.SZ`），yfinance 从美区 runner 原生可用（`daily_stock_analysis` 已用 yfinance）。只在 Yahoo 没有的数据（如申万行业）才回落东财/腾讯。直接缩小暴露在「中国出口风险」下的面。需实测：yfinance 对你具体标的的覆盖率与稳定性。
5. **Supabase 定时 Edge Function 当触发器 + 计算在亚洲/家用 app** —— 同解法 2 思路，触发器改放 Supabase（亚洲区域），复用现有基建。
6. **连通性拼图（让家用/亚洲 app 可被触发器访问，无需备案）** —— 用 **Cloudflare Tunnel**（免费）把本地/小机 app 暴露成 `*.trycloudflare.com` 或自有域名子域，不开端口、不备案（Cloudflare 边缘在海外，不触发国内 ICP 要求），GitHub/Supabase 即可稳定回调触发。

> **反转结论**：别再纠结「调度器放哪」，先定「fetch 放哪」。首选＝家里常驻机 或 现有部署加 APScheduler；GitHub Actions 只做触发器；并用 Yahoo/Stooq 把能绕开的 China 端点绕开。

## 六、边界

- **事实**：GitHub Actions 定时 workflow 在仓库 60 天无活动后自动禁用（搜到多个真实 workflow 示例证实）；功能借鉴分析确认温度是"空模型"（fetchers 在、落库 job 未接）；`daily_stock_analysis` 已用 yfinance 拉海外源。
- **推断**：A 股端点从 GitHub 美区 runner 可达但可能慢/被限（未实测）；`pg_cron` 在 Supabase 免费档可能不可用（待确认）；现有部署是否休眠未知；家庭宽带出口对东财/腾讯通常原生可达。
- **未知**：现有 free overseas deploy 具体平台与休眠行为；Supabase 免费档 Edge Function 额度；yfinance 对你具体 A 股标的的覆盖率；各端点从非中国区的真实延迟；多实例部署时的去重锁方案。

> **关联文档**：fetch 落点即「后端托管地」，具体选型（EdgeOne / 腾讯云 SCF / Oracle 免费 VM 对比）见 [backend-hosting-fetch-selection-2026-08-03](./backend-hosting-fetch-selection-2026-08-03.md)。

---

## 七、EdgeOne 后端下的调度框架（无原生 cron → 外部触发）

> 2026-08-04 复核：上轮把后端放 SCF 主要因为「原生 cron」。但复核发现 **EdgeOne Makers 的 Cloud Functions 原生支持 Python / Flask（APIFlask 为子类直接可用）、可选上海 / 香港区、代码包 128MB、单请求最长 120s**——是比此前认知更强的 Python 宿主。唯一缺口：Cloud Functions 由 HTTP 请求触发，**官方未提供原生 cron/timer 触发器**（「定时任务」仅列为适用场景，无 timer 触发器类型）。结论因此调整为：**EdgeOne 可当后端，调度仍需外部触发**（与 §一 解耦原则一致）。

### 7.1 直接回答：EdgeOne 上用什么替 APScheduler？

**外部调度器「喊一声」→ EdgeOne Cloud Function 的 `/api/cron/*` 端点跑活。** serverless 下没有常驻进程，APScheduler 本就不能用；也没有原生 cron。调度与计算继续解耦（§一）。

### 7.2 框架长这样

```
[外部调度器] --HTTPS POST(cron, 带 X-Cron-Secret)--> [EdgeOne Cloud Function /api/cron/*]
                                                  │
                                                  ├─ 校验 secret → 401
                                                  ├─ 调 job：fetch(东财/腾讯/申万)+算乖离+落 Supabase
                                                  └─ 返回 200 / 失败告警(router.health())
```

- **计算层**：EdgeOne Cloud Function（Python，APIFlask app 作为 HTTP 端点；原生支持 Flask）。
- **调度层（外部，可叠加）**：
  1. **SCF 定时器（推荐）**：免费、原生 cron、可选上海区，handler 只 `requests.post` 你的 EdgeOne 端点；后端零改动。＝「SCF 只管喊，EdgeOne 只管算」。
  2. **GitHub Actions**：免费 cron，但 60 天自动禁用 + 美区风险（见 §五）→ 仅备份。
  3. **家里机 cron / EasyCron**：最稳，家庭宽带＝中国出口（见 §五 解法 1）。
- **鉴权**：端点必须密钥保护（防公网滥用）；job 幂等 + `last_run` 记录。

### 7.3 代码骨架（直接可用）

APIFlask cron 蓝图（计算层，留在 EdgeOne）：

```python
# cron_bp.py —— 部署在 EdgeOne Cloud Function（Python/Flask 原生）
import os, time
from flask import Blueprint, request, jsonify
from your_app.jobs import run_bias_job, run_nav_job   # 你已有的 job 函数，原样保留

cron_bp = Blueprint("cron", __name__)
SECRET = os.environ["CRON_SECRET"]

@cron_bp.post("/api/cron/bias")
def cron_bias():
    if request.headers.get("X-Cron-Secret") != SECRET:
        return jsonify(err="forbidden"), 401
    run_bias_job()                 # fetch+算+落库，原逻辑不动
    return jsonify(ok=True, ts=int(time.time()))

@cron_bp.post("/api/cron/nav")
def cron_nav():
    if request.headers.get("X-Cron-Secret") != SECRET:
        return jsonify(err="forbidden"), 401
    run_nav_job()
    return jsonify(ok=True)
```

外部调度器示例 A —— SCF 定时器 handler（仅 curl，不跑 Python 重活）：

```python
# scheduler_handler.py —— 部署在腾讯云 SCF，绑定时触发器
import os, requests
def handler(event, context):
    url = os.environ["ENDPOINT"] + "/api/cron/bias"
    r = requests.post(url, headers={"X-Cron-Secret": os.environ["CRON_SECRET"]}, timeout=110)
    return r.status_code
```

外部调度器示例 B —— GitHub Actions（标注风险，仅备份）：

```yaml
# .github/workflows/cron.yml
on:
  schedule: [{ cron: "0 1 * * *" }]   # UTC；注意美区 runner 连 A 股风险 + 60 天禁用
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl -X POST -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" ${{ secrets.ENDPOINT }}/api/cron/bias
```

### 7.4 与上一轮结论的关系

- 上轮把 SCF 当「后端 + 定时」一体；现可改为：**EdgeOne Cloud Functions 当后端（Python/Flask 原生、上海/香港区），SCF 定时器只当免费调度器**——或用家里机/EasyCron 完全免去 SCF。后端代码（APIFlask + jobs）两种落点都零改动。
- akshare 体积：EdgeOne Cloud Functions 代码包上限 **128MB**（SCF 同样有体积顾虑），压 akshare 仍是必要优化（与之前一致）。
- 超时：EdgeOne 单请求最长 **120s**（默认 30s 可调）；每日聚合 + 净值若超 120s 需拆分 job 或迁 SCF（最高 900s）。

### 7.5 边界

- **事实**：EdgeOne Cloud Functions 支持 Node.js/Python/Go，原生支持 Flask/FastAPI/Django/Sanic，可选上海/香港等区，代码包 128MB、单请求最长 120s（官方文档 127418，2026-07-07）；Cloud Functions 由 HTTP 请求触发，官方未提供 timer 触发器类型；「定时任务」列为适用场景但未配原生 cron（官方概览 127415）。
- **推断**：EdgeOne 无原生 cron → 必须外部触发；APIFlask 作 Flask 子类在 Cloud Functions 直接可用；SCF 定时器 curl EdgeOne 端点可组成免费调度。
- **未知**：EdgeOne Cloud Functions 实际 Python 入口格式（是否需特定 handler 签名）；免费额度与冷启；128MB 是否够装削减后的依赖；上海区连东财/腾讯实测延迟。

### 7.6 确定性结论与下一步

经 2026-08-04 官方文档复核，最终落地方案＝**SCF 后端（Web 函数跑 APIFlask）＋ SCF 原生定时触发器跑 job**，前端用 EdgeOne Pages。理由：SCF 有原生 cron，维护项最少；EdgeOne 虽后端更零配置但无原生 cron，反需外加调度器。具体步骤见 [deployment-implementation-guide-2026-08-04](./deployment-implementation-guide-2026-08-04.md)。
