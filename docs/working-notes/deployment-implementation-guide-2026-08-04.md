# 部署实施指南（确定性方案）（2026-08-04）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 结论日期：2026-08-04
> 选型依据：综合 [backend-hosting-fetch-selection-2026-08-03](./backend-hosting-fetch-selection-2026-08-03.md) 与 [scheduling-options-research-2026-08-04](./scheduling-options-research-2026-08-04.md) ＋ 本轮官方文档复核（腾讯云 SCF / EdgeOne 官方文档）。
> **最终架构**：前端 EdgeOne Pages ＋ 后端与定时都用腾讯云 SCF（Web 函数跑 APIFlask；事件函数＋原生定时触发器跑 job）。
> **一句话理由**：两种平台都能零改动跑 APIFlask；但 SCF 有**原生定时触发器**——cron 是平台内置、零额外代码、不需要 24h 开着的机器、不依赖第三方。EdgeOne Cloud Functions 后端部署更「零配置」，但它**没有原生 cron**，反而逼你再多挂一个调度器（再开 SCF / 养台机器 / 靠第三方），长期维护更烦。要维护的东西最少 → 选 SCF。

---

## 一、架构一览

```
[用户/前端] --HTTPS--> [EdgeOne Pages：Vue SPA，免费全球 CDN]
                           |
                           v  调用 API
                 [腾讯云 SCF Web 函数：api-flask]
                           |  APIFlask app，端口 9000，经 API 网关(默认域名，不备案)
                           |
     [腾讯云 SCF 事件函数：jobs-runner] <== 原生定时触发器(cron，每日定点)
                           |
                           v
              run_bias_job() / run_nav_job() / 温度聚合
                           |
                +----------+----------+
                v                     v
          [Supabase Postgres]   [上游：东财/腾讯/申万]（SCF 上海/广州区，对华出口友好）
```

- **计算**（抓数 / 落库）留在 SCF 函数里，封装成 job 函数；业务代码不动。
- **调度**（cron）由 SCF 原生定时器直接触发 `jobs-runner`，不需要 APScheduler、不需要外部调度器。
- **前端**静态放 EdgeOne Pages（免费、全球 CDN），只调 SCF 的 API。

---

## 二、前置条件

1. 腾讯云账号（需实名认证，SCF 要求）。
2. EdgeOne 账号（前端用，免费版套餐即可）。
3. Supabase 项目（已有，DB / Auth）。
4. 代码已具备：`app.py`（APIFlask）＋ `jobs/`（BiasJob / 净值 / 温度）＋ `fetchers/` ＋ `calculator/` ＋ `router/`（数据源优先级路由，已在 [datasource-priority-plan-2026-08-03](./datasource-priority-plan-2026-08-03.md) 验证）。

---

## 三、第一部分：前端 → EdgeOne Pages（最简，一次性）

1. EdgeOne 控制台 → Pages → 新建项目 → 连 GitHub 仓库（Vue3＋Vite 项目）。
2. 构建命令 `npm run build`，输出目录 `dist`。
3. 部署后拿到 `*.edgeone.app` 域名（免费、全球加速），**无需备案**。
4. 前端里调后端的 base URL 设为下一步拿到的 SCF API 网关地址。

> 前端几乎零维护：每次 push 自动构建发布。

---

## 四、第二部分：后端 API → SCF Web 函数（APIFlask，零业务改动）

> 官方机制（文档 58183 / 56126 / 1154-40495）：SCF Web 函数用 `scf_bootstrap` 启动一个 Web 服务（gunicorn），`type: web` 后**无需指定入口函数**；Flask 有官方部署模板。你的 `app.py` 基本原样用。

### 4.1 仓库结构（只新增部署文件，不动业务代码）

```
showbuy/                     # 现有后端仓库
├── app.py                   # APIFlask app（已有，原样）
├── jobs/  fetchers/  calculator/  router/   # 业务代码，原样
├── requirements.txt         # 依赖（flask/apiplask/sqlalchemy/supabase/削瘦后的数据源依赖）
├── scf_bootstrap            # 新增：启动 gunicorn
└── serverless.yml           # 新增：SCF 部署配置
```

### 4.2 scf_bootstrap（新增）

```bash
#!/bin/bash
# SCF Web 函数启动文件；监听 0.0.0.0，端口用 SCF 注入的 $PORT（默认 9000）
export PYTHONPATH=/var/user:/opt
gunicorn app:app -w 1 -b 0.0.0.0:${PORT:-9000} --timeout 120
```

- `app:app` 即你的 APIFlask 实例（`app.py` 里的 `app = APIFlask(__name__)`）。APIFlask 是 Flask 子类，gunicorn 照常起。
- 给 `scf_bootstrap` 加可执行权限：`chmod +x scf_bootstrap`。

### 4.3 serverless.yml（新增）

```yaml
component: scf
name: duoduobei-backend
inputs:
  src: ./
  type: web                 # Web 函数
  name: api-flask
  region: ap-shanghai       # 上海区，对华出口好；不备案用默认 *.scf.tencentcs.com
  runtime: Python3.9
  timeout: 120              # API 请求最长 120s
  memorySize: 256
  # Web 函数自动配 API 网关，默认域名无需备案
```

### 4.4 部署

```bash
npm i -g @serverlesscomponents/tencent-scf   # 或官网 SCF CLI
scf deploy                                   # 首次扫码授权
```

部署完在 SCF 控制台「函数管理 / api-flask」看到 API 网关访问路径（形如 `https://xxx.apigw.tencentcs.com/...`）。

### 4.5 验证

```bash
curl https://<你的API网关地址>/api/health     # 应返回 200
```

（需你已有 `/api/health` 或任意已注册路由；没有就临时加一个。）

---

## 五、第三部分：定时任务 → SCF 事件函数 ＋ 原生定时触发器（核心：替掉 APScheduler）

> 这是「无 APScheduler」的落地：用 SCF **原生 cron** 直接触发一个事件函数，事件函数里跑你的 job。不需要常驻进程、不需要外部调度器、不需要密钥。

### 5.1 jobs-runner 函数（事件函数，只跑 job，不对外）

```
showbuy/jobs_runner/
├── index.py                # main_handler：被定时器调用
├── requirements.txt        # 同后端（或只含 job 所需依赖）
└── serverless.yml          # 默认事件函数 ＋ 定时触发器
```

`index.py`：

```python
# 由 SCF 原生定时器直接调用，无需 HTTP、无需密钥
from jobs.bias_job import run_bias_job
from jobs.nav_job import run_nav_job
from jobs.thermo_job import run_thermo_job

def main_handler(event, context):
    run_bias_job()
    run_nav_job()
    run_thermo_job()
    return {"ok": True}
```

- 复用 `jobs/` 下已有函数；与 Web 函数共享同一份业务代码，**不重复写**。
- 若想手动补跑 / 调试，也可在 `api-flask` 里加一个 secret 保护的 `/api/cron/*` 端点（见 [scheduling-options-research-2026-08-04](./scheduling-options-research-2026-08-04.md) §七），二者不冲突。

### 5.2 serverless.yml（带定时触发器）

```yaml
component: scf
name: duoduobei-jobs
inputs:
  src: ./
  name: jobs-runner
  region: ap-shanghai
  runtime: Python3.9
  timeout: 120
  memorySize: 256
  events:
    - timer:                # 原生定时触发器
        name: daily-agg
        parameters:
          # SCF 定时触发器用 7 字段 cron：秒 分 时 日 月 星期 年（非 Linux 5 字段）
          cronExpression: "0 0 1 * * * *"   # 每天 UTC 01:00（≈北京 09:00），按需在控制台改
          enable: true
```

- cron 是 SCF **原生能力**；控制台「触发器」页也能图形化加、改频率。无需任何第三方。

### 5.3 部署 ＋ 绑定

```bash
cd jobs_runner && scf deploy
```

部署后在 SCF 控制台 `jobs-runner` → 触发器 看到 `daily-agg`，状态「已启用」。

---

## 六、第四部分：联调验证

1. **手动触发**：`jobs-runner` 控制台 → 测试 → 触发，看日志跑完 3 个 job、落库成功。
2. **验证调度**：等下一个 cron 点，或临时把 cron 改成近期时间，确认自动跑。
3. **前端联调**：EdgeOne Pages 域名打开，确认能拉到 SCF API 的数据。
4. **告警**：把 `router.health()`（已在 [datasource-priority-plan-2026-08-03](./datasource-priority-plan-2026-08-03.md) 定义）接入 job 结束告警。

---

## 七、边界与注意（官方复核 2026-08-04）

- **事实**：
  - SCF Web 函数 `type: web` ＋ `scf_bootstrap` 跑 Flask，无需指定入口函数（官方 58183 / 56126）；Flask 有官方部署模板（1154 / 40495）。
  - SCF 新用户前 3 个月每月 **100 万次调用 ＋ 100 万 GBs** 免费；**第四个月起不再有免费额度，转为按量计费**（官方 17299）。按量单价（官方 12281）：调用 **0.0133 元/万次**、资源 **0.00011108 元/GBs**、外网出流量 **0.80 元/GB**（大陆 / 新加坡等，香港 1.00）。
  - API 网关第一年每月 **100 万次调用 ＋ 1GB 流量** 免费；**首年后免费额度结束，转按量**（官方 628 / 39300 / 48792）：调用阶梯 **0.06 元/万次**（≤1000 万）、0.04、0.03；出流量 **0.80 元/GB**（大陆）。
  - 个人低频项目（约 3000 次 API 调用 ＋ 30 次 job/月，出流量 1–3GB）实测账单约 **3–5 元/月**，金额可忽略（官方定价估算）。
  - SCF **原生定时触发器**（timer）为内置能力，cron 表达式驱动。
  - EdgeOne Cloud Functions 支持 Python / Flask 原生（零配置、自动扫依赖），代码包 128MB、单请求 120s，但**无原生 cron**（官方 130012 / 127415）。
- **为什么不是全栈 EdgeOne**：EdgeOne 后端部署更省事（自动依赖、零配置），但缺原生 cron → 必须外加调度器，维护项反而更多。仅在「强需求单平台」时选（见 [scheduling-options-research-2026-08-04](./scheduling-options-research-2026-08-04.md) §七 / 本文件 §八）。
- **akshare 体积**：SCF 代码包有体积约束；EdgeOne 上限 128MB。继续削减 akshare（乖离度改直连、router 主推直连上游）正好对齐。
- **不备案**：SCF 用默认 `*.scf.tencentcs.com` / API 网关默认域名，不开自定义域名即不触发 ICP；EdgeOne Pages 默认域名同理。
- **区域**：后端选 `ap-shanghai`（上海）或 `ap-guangzhou`，对华出口好、连东财 / 腾讯稳。
- **未知 / 待验证**：API 网关默认域名长期免费政策（首年明确免费）；SCF 冷启动对每日低频无碍（待实测）；上海区连各上游实测延迟；压瘦后依赖体积是否达标；`app = APIFlask(...)` 是否被 EdgeOne 的 WSGI 自动检测识别（SCF 用 gunicorn 无此问题）。

---

## 八、备选：想全栈放 EdgeOne（单平台）

若你更看重「前后端一个平台」，可：前端＋后端都放 EdgeOne（Cloud Functions，零配置 Flask），**定时用外部触发器**：

- **最简**：家里常驻机 / 旧电脑加系统 cron，每天 `curl -XPOST 带密钥 /api/cron/bias`（家庭宽带＝中国出口，最稳）。
- **或 EasyCron**（免费档够每日几次）触发 `/api/cron/*`（端点必须密钥保护）。
- **或仍用 SCF 定时器**只 `curl` EdgeOne 端点（但这样又开了 SCF，没省平台）。

> 该路线维护成本高于 SCF 一体方案（多一个调度器要管），仅在「强需求单平台」时选。代码骨架见 [scheduling-options-research-2026-08-04](./scheduling-options-research-2026-08-04.md) §七。
