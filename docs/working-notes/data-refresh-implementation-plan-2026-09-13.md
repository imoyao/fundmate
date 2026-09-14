# 数据刷新 · 方案设计与实施规划（2026-09-13 第二轮）

**状态**：**方案设计 + 实施规划**（本轮在 v2「待拍板」底稿之上，把 9 项需求转成可落地的设计与 PR 拆分）。
**关联**：#1467（本机常驻调度，已完成并合入 `dev`）· #1476 / #1477 / #1480（前序 PR）· #1481（汇率修复，本轮已合入）· #1451（汇率口径决策）· #1436 / #1444（探市页）· #1407（估值历史分位）。

**前置底稿**：`data-refresh-scheduling-plan-2026-09-13.md`（v2，盘点 / 三类结构性问题 / 10 项待决）——本文聚焦本轮 9 项需求的**方案设计与实施规划**，不再重复盘点。

---

## 0. 结论先行

1. **9 项里 2 项已闭环或有明确结论**：
   - **#2 汇率数据**：根因已定位（akshare `currency_boc_sina` 默认日期硬编码成 `20230304~20231110`），**已修复并合入 `dev`（PR #1481）**；真值验证返回 2026-01-01~2026-09-12 的当前数据。
   - **#6 净值接口**：**实现正确**，无需修改（自实现的东财 `lsjz` 增量 + `pingzhongdata` 货基/全量，因 `xalpha 0.12.4` 坏；增量窗口 `last.date()-1 天` 合理）。
   - **#5 抓取范围**：**当前已是全用户**（`resolve_targets` 读 `positions` + `watchlist` 全库 distinct，**无 family/user 过滤**），与需求吻合，无需改代码。
2. **#7 CI 失败真因已查清**：**不是远端库/表未初始化**，而是缺 SQLAlchemy 的 **libsql 方言依赖**（`NoSuchModuleError: sqlalchemy.dialects:turso`）；`init_db()` 的 `create_all` 本就会自动建表。**本地准备 = 加依赖 + URL 归一**。
3. **#1 温度历史 / #3 本机不稳定 / #4 频率 / #8 部署 / #9 通知** 均有方案（见各节），其中 #3/#4/#8/#9 需新增少量代码，#1 需一个一次性回补脚本。
4. **#8 部署是全局阻塞项**：当前后端 API **未部署**（Vercel 只构建 landing 页），数据在线上**没有消费端**。计划用 EdgeOne Pages Python 函数（香港、免备案）承载 `api.duoduobei.com`，零改写，可行性 OK，阻塞只在执行。

---

## 1. 本轮 9 项核查结论（事实，会上只需确认）

| # | 需求 | 核查结论 | 证据 / 复现 |
|---|------|---------|------------|
| **#2** | 汇率数据补充 | 根因 = `akshare.currency_boc_sina` **默认日期硬编码 `20230304~20231110`** → 永远 2023 数据；**已修（PR #1481）**。真 DXY / 离岸 CNH 在 akshare **无稳定免费源**（`fx_spot_quote` 当前全 NaN、`forex_spot_em` 东财通道挂、中行不报离岸） | 读源码确认硬编码；真实接口实测传近期日期返回 219 行（2026-01-01~09-12）；PR #1481 已合入 |
| **#6** | 净值接口检查 | **实现正确**：`xalpha_adapter.fetch_fund_nav` 自实现东财 `f10/lsjz` 增量 + `pingzhongdata` 货基/全量（绕开坏掉的 `xalpha 0.12.4`）；增量窗口 `last.date()-1 天` 合理 | 读 `xalpha_adapter.py` + `fund_nav_job.py`；`fund_nav` job 历史 10 次成功（真库 `sync_logs`） |
| **#5** | 抓取范围确认 | **已是全用户**：`orchestrator._load_codes_from_database` 读 `Position.symbol` + `WatchlistItem.symbol` 全库 `distinct()`，**无 family_id/user_id 过滤** | 读 `orchestrator.py` 源码（§5 节详述）；CI 路径读 Supabase（全部用户） |
| **#7** | CI Secret 后仍报错 | **非 DB/表未初始化**：缺 `sqlalchemy-libsql` 方言包 → `NoSuchModuleError: sqlalchemy.dialects:turso`；`create_all` 会自动建表 | `gh run view 34712414320 --log-failed`；`pyproject.toml`/`pdm.lock` 无 libsql 依赖；环境未装 |
| **#9** | 通知通道 | **两个现有 token 均失效**：Resend `401`、WX Pusher `404`（qrcode 接口）；且无 WX Pusher 的 UID/主题配置 | `Invoke-RestMethod` 实测 Resend `401`、WX Pusher `404`；`.env` 含 `RESEND_TOKEN`/`WXPUSHER_APP_TOKEN` |
| **#3** | 本机不稳定 | 现有调度已具备 `misfire_grace_time=6h`、`coalesce`、启动补跑；**缺口**：>6h 过夜休眠整天不跑、无跨天重试、无告警 | 读 `daily_scheduler.py` + 真机进程探测（运行中的后端锁空闲） |
| **#4** | 更新频率 | 当前：温度 20:00、净值 21:30、探市 08:00（建议）；盘口指数 ~22:00 后更新 → 探市 08:00 取的是前一日收盘（可接受），净值 21:30 可能漏抓晚发布 | 读 `scheduler-tasks.md` + `daily_scheduler.py` 配置 |
| **#8** | 后端部署 | **未部署**：`vercel.json` 只构建 `build:landing`；计划 = EdgeOne Pages Python 函数 + 双库（Supabase 用户 + Turso 行情） | 读 `vercel.json`、`docs/ops/deployment.md` |
| **#1** | 温度历史补齐 | **官方合成温度（且慢/有知有行/韭圈儿）无历史 API**，只能从存储起始日算起；**可补齐 = 自算项**（股债利差/成交额/乖离率/拥挤度）+ **集思录中位 PB/PE**（历史下载 CSV，需 Cookie）；`all_pb.csv` 基线已在 `services/thermometer/data/` | 读 `fetchers.py`、`all_pb.csv` 实际路径；源码无历史接口 |

---

## 2. #1 温度计数据补齐（调研 + 方案）

### 2.1 哪些能补齐，哪些不能

| 温度组成 | 历史可得性 | 补齐方式 |
|----------|-----------|---------|
| 且慢 / 有知有行 / 韭圈儿（官方合成温度） | ❌ 无公开历史 API | **不能**补齐到存储起始日之前；只能从首次入库日起 |
| 自算估值分位（股债利差：沪深300 PE + 10Y 国债 + CPI） | ✅ akshare 有完整历史 | **可**重算历史 |
| 东财两市成交额 | ✅ 指数日线含成交量历史 | **可**重算历史 |
| 乖离率（31 行业 + 6 宽基） | ✅ 价格历史可得 | **可**重算历史 |
| 行业拥挤度 | ✅ 行情历史可得 | **可**重算历史 |
| 集思录中位 PB/PE 温度 | ✅ 集思录有历史下载 CSV（`data/indicator/download/...`） | **可**补齐，但**需 JSL Cookie**（与现有抓取同源） |

**结论**：温度页面的「组件」大多可回补，**「官方合成温度」本身不可回补**。这恰好印证 v2 的结论——历史分位依赖的历史**不依赖本库**，可以从数据源现算/回算。

### 2.2 实施规划

- **PR-E1（一次性回补脚本）**：`scripts/backfill_temperature_history.py`，对「自算项 + 成交额 + 乖离率 + 拥挤度」按各资产历史起点回算并写入 `market_composites` / `market_multi_items` / `market_single_values`。纯本地计算，无外部增量风险。
- **PR-E2（集思录历史 fetcher）**：在 `thermometer/fetchers.py` 增加「历史下载」入口（复用 JSL session），把中位 PB/PE 温度回补到可获取的起点；受 Cookie 有效性约束，失败则跳过该项（不阻断）。
- **不在范围**：官方合成温度的史前补齐（无源）。

---

## 3. #2 汇率数据补充（已交付 PR #1481）

- **根因**：`akshare.currency_boc_sina(symbol='美元')` 的**默认 `start_date/end_date` 硬编码为 `20230304~20231110`**，与传入参数无关 → 探市页「美元指数 / 离岸人民币」两张卡永远显示 2023 年数据。
- **修复（PR #1481，已合入 `dev`）**：`market_service._fetch_close_series` 对 `currency_boc_sina` 强制传入近期窗口（`start_date=今天-900天`、`end_date=今天`），既拿当前汇率又保留 ≥500 交易日用于分位。新增回归测试锁住「必须传近期日期」。
- **真值验证**：真实接口返回 **2026-01-01~2026-09-12 共 219 行**当前数据（美元中间价 ~669~702），不再是 2023。
- **剩余缺口（不在本 PR）**：真 DXY / 离岸 CNH 在 akshare 无稳定免费源（`fx_spot_quote` 全 NaN、`forex_spot_em` 东财挂、中行不报离岸）。#1451 已明确这两张卡是「在岸中行牌价替代」，标签与 `caliber` 口径标注沿用既有决策；若需真值，需另找源（scraping），单列 issue。

---

## 4. #3 本机运行环境（长期开机、偶尔关机）

本机被视作「长期开机、偶尔关机」，方案必须覆盖不稳定性。现有 `daily_scheduler.py` 已具备 `misfire_grace_time`（默认 6h）、`coalesce`、`run_on_start` 启动补跑；**缺口与加固**：

| 场景 | 当前行为 | 缺口 | 加固（PR-C） |
|------|---------|------|------|
| 合盖过夜 / 休眠 >6h | 唤醒后距触发 > grace → 整天不跑 | **grace 6h 太小** | `misfire_grace_time` → **24h**（覆盖「晚睡、早开机」） |
| 断网 / 当天失败 | 单 job 重试 3 次后仍失败记 `failed`，当天不再重试 | **无跨天补偿** | 启动补跑判定放宽为「最近一次成功早于上一计划时刻」→ 隔天开机也能补 |
| 长期不开机 | 全部跳过，下次开机补当天 | 可接受（数据源可回溯） | 保持 |
| 失败无人知 | 仅日志（窗口一关即失） | **无告警** | 见 §10 通知（PR-F），本机至少「失败落盘 + 开机自检摘要」 |
| 并发双跑 | ✅ 单实例文件锁 | — | 保持 |

**结论**：本机通道适合「每日新鲜度」（净值 / 行情 / 快照 / 温度 / 探市），**不适合**承担元数据回填、逐只类等「错过一次就长期缺口」的重活——后者归 CI / 服务器。扩到 7 项可行，但**先做上面两处加固**。

---

## 5. #4 更新频率调整

### 5.1 先澄清一个混淆

v2 文中「探市 08:00」是**探市快照**，不是温度计。当前实际设定（来自 `daily_scheduler.py` 默认 + `scheduler-tasks.md`）：

| 任务 | 当前触发（北京） | 说明 |
|------|----------------|------|
| 温度计 | **20:00** | 集思录中位 PB / 韭圈儿 / 行业拥挤度盘后即出 |
| 基金净值 | **21:30** | 场外净值 19:00~24:00 陆续公布 |
| 探市快照（建议新增） | **08:00** | 美股 04:00/05:00 收盘后；与商品 08:00 口径统一 |

### 5.2 频率评估与建议

- **温度计 20:00**：集思录 / 韭圈儿约 20:00 发布，合理；若其指数成分类组件延迟到 22:00，可微调到 21:00（**保留 20:00 即可，无需急改**）。
- **净值 21:30 → 建议「21:30 + 次日 07:30 补抓」**：部分平台净值 24:00 后才出，21:30 可能漏抓；次日早间补一次可兜底。21:30 与 07:30 取较新者，幂等覆盖。
- **探市 08:00**：取的是前一交易日收盘（盘口指数 22:00 后更新，08:00 已就绪）；若要求「当日盘后即时」，可改 22:30，但一天一次足矣，**维持 08:00**。
- **你问的「7 点还是 8 点」**：指净值早间补抓——建议 **07:30**（早于开盘 09:30，确保盘中看到最新净值）。

---

## 6. #5 抓取范围确认（已满足，仅记录证据）

`orchestrator._load_codes_from_database` 的真相（读 `backend/app/services/sync/orchestrator.py`）：

```python
positions = self.db.query(Position.symbol).distinct().all()      # 全库持仓，无 family 过滤
watchlist = self.db.query(WatchlistItem.symbol).distinct().all()  # 全库自选，无 family 过滤
```

→ **已经是「系统内所有家庭/用户」的持仓 + 自选**，与需求「对所有用户持有的数据都抓取」完全一致。
- **CI 路径**（生产）：`self.db` 路由到 **Supabase 用户库**（全部用户）→ 全量。
- **本机路径**：路由到**本机 SQLite**（只有本机用户的本地数据）→ 自然是「本机用户」。
- **注意**：逐只类（`fund_position` 等）与全市场大调用（`fund_scale` 37s、`fund_name_em` 20s）**不进本机**（v2 D6），只在 CI / 手动跑。

**结论**：无需改代码；仅建议在 `fund_nav` job 增加「目标池为空则告警」（与 #1467 已 unittest 的 `_allow_empty_data=True` 风险闭环）。

---

## 7. #6 净值数据接口检查（结论：正确）

`xalpha_adapter.fetch_fund_nav` / `_fetch_lsjz_incremental`：
- 直连东财 `api.fund.eastmoney.com/f10/lsjz`（日期区间分页），**绕开坏掉的 `xalpha 0.12.4`**；
- 货基走 `pingzhongdata/<code>.js` 取 `millionCopiesIncome`；全量回退同样路径；
- 增量窗口 `start_date = last.date() - timedelta(days=1)`（`fund_nav_job.py`），首跑 `today-30天`；
- `WAF` 用 `Referer` 头规避，失败单只跳过不影响整体。

**结论**：实现正确，无需修改。唯一风险是「目标池为空时 `_allow_empty_data=True` 静默成功」——已在 #1467 用单测钉死（探测目标池非空 + 告警），与 §10 通知闭环。

---

## 8. #7 CI Secret 与方言修复（根因 + 本地准备）

### 8.1 根因（已查实，非 DB/表未初始化）

`gh run view 34712414320 --log-failed` 末尾：

```
sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:turso
```

- `APP_ENV=production` 时，`db_factory.for_app()` 走 **Turso** 行情库（`TURSO_DATABASE_URL` 未设 → 回退 `DATABASE_URL`，其值为 `turso://...`）；
- SQLAlchemy 需要 **libsql 方言**才能解析 `turso://` scheme，但 `pyproject.toml` / `pdm.lock` / 运行环境**都没有该依赖**；
- `init_db()` 的 `create_all` **会自动建表**，所以**不是表未初始化**——装好方言后首次 `pdm run scheduler` 即自建表。

### 8.2 本地 / CI 准备（PR-B）

1. **加依赖**：`pyproject.toml` 增加 `sqlalchemy-libsql`（prod, required）；`pdm install` 同步 lock。
2. **URL 归一**（`db_factory.build`）：把 `turso://` / `libsql://` 重写为 `sqlite+libsql://`，并把 `auth_token` 从 query 提取到 `connect_args`（Turso 需要）。
3. **验证**：本地用 `APP_ENV=production` + 占位 Turso URL 跑 `create_engine`，确认不再 `NoSuchModuleError`；CI 重建后 `daily-snapshot` 应能连库并 `create_all`。
4. **CI secrets 复核**：确认 `DATABASE_URL`（或 `TURSO_DATABASE_URL`）已设为 `turso://...?authToken=...` 且 token 有效（当前 `TURSO_DATABASE_URL` 未设，需补或确认 `DATABASE_URL` 即 Turso）。

> 这一步同时解锁 #8：CI 能写生产库后，部署才有意义。

---

## 9. #8 后端 API 部署（评估 + 方案）

### 9.1 现状

- `vercel.json` 仅 `build:landing`（落地页），**后端 API 未纳入任何部署** → 线上**无消费端**，数据只在本机可见。
- 计划（已写 `docs/ops/deployment.md` v2）：**EdgeOne Pages Python 函数**（香港、免备案）承载 `api.duoduobei.com` + 双库（Supabase 用户 + Turso 行情）；前端走 EdgeOne/Cloudflare/Vercel。

### 9.2 可行性

- 后端是标准 Flask/`APIFlask`，**零改写**即可上 Python 函数；
- 环境依赖（apscheduler 等）需打进函数包；本机常驻调度只在 `SCHEDULER_ENABLED` 开时启动，部署侧应**关闭**（`CI=true` 已天然不启动），改由 CI `daily-snapshot` 承担每日抓取；
- **阻塞只在执行**：需建 EdgeOne 项目、配双库 secret、打通 `APP_ENV=production` 路径（依赖 §8.2 的方言修复）。

### 9.3 实施规划（PR-F）

- 建 EdgeOne Pages Python 函数工程（复用 `app/`），`APP_ENV=production`、`SCHEDULER_ENABLED=0`；
- 配 `DATABASE_URL`(Turso) / `SUPABASE_*` secrets；
- 部署后接 §10 通知做失败告警；
- 前端 `VITE_API_BASE` 指向 `api.duoduobei.com`。

---

## 10. #9 通知通道（Resend + Webhook + WX Pusher）

### 10.1 现状（已实测）

- **Resend**：`.env` 有 `RESEND_TOKEN`，但 `GET /domains` 返回 **401** → **失效/过期**。
- **WX Pusher**：`.env` 有 `WXPUSHER_APP_TOKEN`，但 qrcode 接口 **404** → **token 失效或服务变更**；且**无 UID/主题**配置（即使通了也没发送目标）。
- 仓库**无通知代码**（仅 `docs/ops/email-service.md` 讲 Supabase 验证码用 Resend，与告警无关）。

### 10.2 方案（PR-F 内）

新增 `app/services/notify.py`，**配置驱动**、三通道可插拔：

| 通道 | 触发可用性 | 备注 |
|------|-----------|------|
| 邮件（Resend） | 需重发 token | 给用户发摘要/告警邮件 |
| Webhook | **无需预配置 token**（给个 URL 即可） | **推荐做主通道**（CI / 本机失败告警最稳） |
| WX Pusher | 需重配 token + UID/主题 | 用户微信即时推送，待用户补充配置 |

- **告警阈值**：关键 job（净值 / 资产快照 / 温度 / 探市快照 / JSL 保活）**连续 1 次失败即告警**；非关键 **3 次**。
- **本机**：失败落盘 + 开机自检摘要（即使没配通道也不丢信息）。
- 用户说「后续会补充相关配置信息」→ 模块先就位，**token/URL/UID 作为配置项接入即可**，不阻塞代码合并。

---

## 11. 实施路线图（PR 拆分与顺序）

| PR | 范围 | 依赖 | 风险 | 状态 |
|----|------|------|------|------|
| **#1481** | 汇率修复（#2） | — | 低 | ✅ 已合入 |
| **PR-B** | CI Turso 方言修复（#7 本地准备） | — | 中（改 DB 连接） | 待做 |
| **PR-C** | 本机可靠性加固（#3：grace 24h + 跨天补跑） | — | 低 | 待做 |
| **PR-D** | 频率调整（#4：净值 07:30 补抓） | — | 低 | 待做 |
| **PR-E** | 温度历史补齐（#1：回补脚本 + 集思录历史 fetcher） | — | 中 | 待做 |
| **PR-F** | 部署（#8 EdgeOne）+ 通知（#9 notify 模块） | PR-B | 中 | 待做 |
| **PR-G** | 抓取范围文档化 + 空目标池告警（#5/#6 收口） | — | 低 | 待做 |
| **PR-H** | 文档收口（`decisions.md` + `data-refresh-inventory.md` + `scheduler-tasks.md`） | 全部 | 低 | 待做 |

**推荐顺序**：#1481（完成）→ PR-B（解锁 CI/生产库）→ PR-C/D（本机加固，立竿见影）→ PR-F（部署+通知，让数据有消费端）→ PR-E（历史补齐）→ PR-G/H。

---

## 12. 验收标准与回滚（通用）

- **通用回滚原则**：新增路径 + 开关，默认保持旧行为；本机调度开关 `SCHEDULER_ENABLED`，CI 失败告警开关独立。
- **PR-B 验收**：CI `daily-snapshot` 不再 `NoSuchModuleError`；本地 `APP_ENV=production` 能 `create_all`。回滚 = 移除方言依赖（URL 归一仅作用于 Turso scheme，对 SQLite 无影响）。
- **PR-C 验收**：合盖过夜 >6h 后开机，当天任务成功补跑（真机/`sync_logs` 可见）。回滚 = grace 改回 6h。
- **PR-D 验收**：净值在 07:30 与 21:30 各跑一次，幂等无重复。回滚 = 关 07:30 任务。
- **PR-E 验收**：回补脚本对自算项写入历史行；集思录历史 fetcher 在 Cookie 有效时补齐，无效时跳过该项不阻断。回滚 = 不跑回补脚本（历史为 0 不影响现有每日逻辑）。
- **PR-F 验收**：`api.duoduobei.com` 上线，探市/温度页可公开访问；CI 失败触发 Webhook。回滚 = 切回未部署（数据仍在本机可见）。

---

## 13. 议程建议（60 分钟，会前异步预读本文 + v2 底稿）

1. **5 分钟**：过 §1 事实核查表（有异议只提事实）。
2. **15 分钟**：拍 **PR-B（CI 方言）/ PR-C（本机加固）/ PR-D（频率）** —— 这三项是本机与 CI 能跑通的前提。
3. **15 分钟**：拍 **PR-F（部署 + 通知）** —— 决定数据是否有消费端、失败能否被感知。
4. **15 分钟**：拍 **PR-E（温度历史）/ PR-G（范围文档化）** —— 历史补齐与范围确认。
5. **10 分钟**：确认 §11 顺序与 §12 验收，分派 PR 负责人。

---

## 14. 附录：关键实测证据

- **汇率**：`currency_boc_sina('美元', start_date='20260101', end_date='20260913')` → 219 行，尾部 2026-09-12（PR #1481 前为 2023-11-10）。
- **CI 失败**：`gh run view 34712414320 --log-failed` → `NoSuchModuleError: sqlalchemy.dialects:turso`。
- **通知**：Resend `GET /domains` → 401；WX Pusher `GET /api/fun/qrcode/<token>` → 404。
- **抓取范围**：`orchestrator._load_codes_from_database` 读 `Position`/`WatchlistItem` distinct，无 family 过滤。
- **部署**：`vercel.json` 仅 `build:landing`；`docs/ops/deployment.md` 为 EdgeOne Pages Python 函数方案。
- **温度历史**：`all_pb.csv` 基线位于 `backend/app/services/thermometer/data/all_pb.csv`；`fetchers.py` 仅当前值、无历史接口。
