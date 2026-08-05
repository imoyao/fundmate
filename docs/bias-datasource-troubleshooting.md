# 乖离率数据获取失败 — 排查与协作手册

> 适用：任何人接手「多倍贝」乖离率（bias）数据为空的问题时，照此手册排查，避免重复踩坑。
> 创建：2026-08-02 ｜ 状态：进行中（数据源层未坐实根因）

---

## 0. 一句话结论（先讲清楚，省得再绕圈）

**应用层代码已经修通了**（落库 / 读取 / stale 透传 / 前端提示，全部有测试覆盖）。
当前乖离率拿不到数据，**断点在数据源层**：`akshare` 依赖的东方财富网页接口在本机连不上。

不是你项目代码的 bug，是**数据源（东财）2026 年普遍限流/封 IP + 本机系统代理残留**叠加导致。

> ⚠️ **2026-08-05 重要修正（见 `docs/working-notes/eastmoney-antiscrape-2026-08-05.md`）**：
> 原先归因为「DevSidecar 代理 TLS 干扰」**已被推翻**。今天实测根因是**系统代理残留**
> （已死的 `127.0.0.1:31181` 边车代理，代理软件关了但系统代理开关仍解析为 https 代理），
> 已在 `requests_patch.py` 用 `trust_env=False + proxies=None` 强制直连修复（`ProxyError` 消失）。
> 但**东财出口 IP 封是真实存在的第二层问题**（强制直连后 A/B 仍 `RemoteDisconnected`），代理开关都无效正因此。
> **替代源 baostock 已装并验证可达**，是绕开东财 IP 封的正解（不采纳 westock-data 等未知 CLI 源）。

> ⚠️ 关键提醒：**不要再到应用层（后端 service / 前端 vue）打转了**。那里已经测过、没问题。继续改代码解决不了「数据源连不上」。

---

## 1. 现象

- 前端「温度计」页 → 行业乖离度排行：长期显示「暂无乖离率数据」。
- 后端 `BiasJob` 实时抓取东财失败 → 无实时数据 → 旧文件缓存为空 → 落库 0 行。
- 任务调度（`pdm run sync --job temperature`）能跑，但产出为空。

---

## 2. 已排除项（代码层，已用测试坐实，请勿重复怀疑）

| 检查点 | 状态 | 证据 |
|---|---|---|
| 落库链路 `save_multi_items` | ✅ 已修 | 之前硬写 `stale=False` 且只认嵌套结构（bias 是扁平记录，导致落库恒为 0）；已重写为兼容两种入参 + 透传 `stale`。`tests/services/bias/` **12 passed** |
| 读取链路 `get_multi_items` / `get_latest_multi_items` | ✅ 已修 | 原 `.filter(stale.is_(False))` 会把滞后数据全滤掉；已去掉过滤并返回 `stale` 标记 |
| `stale` 透传（落库 + 返回） | ✅ 已修 | `BiasJob._convert_to_records` / `TemperatureJob._validate_data` 已放行 `multi` 类型 stale |
| 全局请求补丁覆盖 | ✅ 已验证 | `requests_patch` 覆盖 `requests.get` / `Session.get`，所有用到的 akshare 函数均走补丁；host 重写 `80.push2 → push2` 已生效（仅作保险，**非根因**） |
| 前端可观测 | ✅ 已加 | `temperature.ts` 补 `stale` 字段；`index.vue` 加「数据滞后」横幅 + 每行「滞后」标签 |

---

## 3. 当前断点（数据源层 — 真正卡住的地方）

### 3.1 乖离率实时依赖 akshare 东财接口
- `index_zh_a_hist`（行业指数）→ 第一步 `index_code_id_map_em()` 打 `https://80.push2.eastmoney.com/api/qt/clist/get` 解析 secid。
- `fund_etf_hist_em` / `stock_zh_a_hist` / `fund_open_fund_info_em` 等同样走东财。
- akshare 本质**是爬虫库**，底层抓东财网页接口，没有 SLA、随时被限流。

### 3.2 东财 2026 年普遍问题的社区实证
- **akshare issue #7027（2026-01-31）**：`index_zh_a_hist` 依赖的 `80.push2.eastmoney.com/api/qt/clist/get` 无法访问；换 IP 后能访问，但调用函数后该 IP 在 `80.push2` 上被封。
  👉 这正是本项目 `requests_patch._PUSH2_HOST_RE` 重写逻辑的来历（把它改成无前缀的 `push2.eastmoney.com`）。
- **akshare issue #7099（2026-02~03）**：`RemoteDisconnected: Remote end closed connection without response` 频发，东财侧主动断开；多名用户同期复现，维护者关闭为 completed（视为东财侧临时策略）。
- 技术文章（gitcode 等）结论一致：东财 2025 起大幅加强反爬（IP 封禁 / 验证码 / 频率检测），`RemoteDisconnected` 是典型表现。

### 3.3 本机叠加因素（2026-08-05 实测推翻旧结论）
- ❌ 旧结论「退出 DevSidecar 代理前 curl schannel 失败 = 代理 TLS 干扰」**不准确**。
- ✅ 真实情况：**系统代理残留**（已死的 `127.0.0.1:31181` 边车代理）。`requests` 默认 `trust_env=True`
  继承系统代理，把东财请求甩到已死端口 → `ProxyError`。代理软件关了残留仍在。
- 已在 `requests_patch.py` 用 `trust_env=False + proxies=None` 强制直连修复（`ProxyError` 消失）。
- **东财出口 IP 封是叠加的第二层真实问题**：强制直连后 `diag_em.py` A/B 仍 `RemoteDisconnected`
  （判读分支「A 与 B 都失败（非 Proxy）→ 出口 IP 被封」）。代理开关都试过不行，正因为根因在 IP 层。

---

## 4. 为什么是「怪圈」（务必看懂，否则会一直绕）

```
看到「暂无乖离率数据」
   → 以为是代码 bug，去改后端 service / 前端 vue
   → 改完跑测试，全绿（因为代码本来就没问题）
   → 部署/刷新，还是没数据（数据源层连不上，上层拿不到东西）
   → 再看到没数据，又去改代码……
```

**断点在最底层（数据源 / 网络），上层无论怎么改都拿不到数据。**
要跳出怪圈，必须把注意力从「应用代码」移到「数据源连通性 + 备用源 + 网络策略」。

---

## 5. 复现与诊断（在本机 backend/ 目录执行）

```bash
# 退出 DevSidecar 后跑，看 A/B/C 三段结果，判断是子域问题还是出口 IP 被封
pdm run python scripts/diag_em.py

# 直接验证单个数据源能否连通
pdm run python -c "import akshare as ak; print(ak.index_zh_a_hist('000300','daily','20260101','20260801'))"

# 触发乖离率任务，看 BiasJob 日志里抓取是否报 RemoteDisconnected
pdm run sync --job temperature
```

`diag_em.py` 判读：
- **A 失败 / B 成功** → 仅 `80.push2` 子域问题，全局补丁已重写，C 应转 OK（代码已覆盖）。
- **A 与 B 都失败** → 出口 IP 被东财封（含走代理也不行）→ 需换网络 / 代理轮转 / 换数据源。

---

## 6. 待排查 / 请协助搜索的方向（分门别类，方便认领）

### 方向 A：确认是否东财 IP 封禁（本机，最关键一步）
- [ ] 退出 DevSidecar 后跑 `diag_em.py`，记录 A/B/C 三段输出。
- [ ] 若 A+B 仍失败 → 坐实「出口 IP 被封」，下一步是换网络或代理轮转。
- [ ] 若 A 失败 B 成功 → 仅子域问题，host 重写应已修复（用 C 验证真实 akshare）。

### 方向 B：akshare 版本是否有修复
- [ ] 当前**锁定 1.18.64**（`pdm run python -c "import akshare; print(akshare.__version__)"` 已确认）。
- [ ] 查 PyPI 最新版：维护者在 issue 中惯于建议 `pip install akshare --upgrade`。
- [ ] 升级后在隔离环境验证 `index_zh_a_hist` 是否仍打 `80.push2`、请求策略是否变化。
- [ ] 风险：升级可能引入 breaking change，需评估依赖兼容性。

### 方向 C：替代数据源（避开东财反爬）
- [ ] **akshare 内置备用源（已源码核实，未实网验证）**：
  - `stock_zh_a_hist_tx`（腾讯源）、`fund_etf_hist_sina`（新浪源），symbol 用 `sh`/`sz` 前缀。
  - 需退出代理后实网验证连通性、字段结构、与现有 `PriceFetcher` 的对接成本。
- [ ] 社区方案：`akshare-proxy-patch`（helloYie，issue #7027 提及）——原理是给 akshare 请求加代理/改 host，需评估是否契合本项目。
- [ ] 正规数据 API（**注意甄别，网上多为推广软文**）：AlphaFeed / TickFlow 等。涉及成本与合规，**非本次默认推荐**，仅列作可选方向，待用户拍板。

### 方向 D：网络 / 代理策略
- [ ] DevSidecar 是否必须？能否对东财域名做**规则分流直连**（绕过边车 TLS 干扰）。
- [ ] 是否有其他出口 IP 可做对照实验（手机热点等）。

---

## 7. 决策点（需用户拍板，非技术可单方面决定）

1. 主链路失败时的策略：当前已有「缓存 + stale 降级」，但**空库时无解**。是否要接入备用源 / 正规 API？
2. 是否投入成本接入备用源或付费数据 API（收益 vs 成本）？
3. 部署形态已定：EdgeOne 香港只承载读取，抓取须国内 IP（见 `docs/backend-restructure-edgeone-dualengine.md` §14）。

---

## 8. 相关文件索引

| 文件 | 角色 | 状态 |
|---|---|---|
| `backend/scripts/diag_em.py` | 东财 clist 连通性诊断 | 可用，待本机退出代理后跑 |
| `backend/app/core/requests_patch.py` | 全局请求补丁（host 重写 + 重试 + 浏览器头） | 已加 DEBUG 日志，host 重写仅作保险 |
| `backend/app/services/bias/calculator.py` | `PriceFetcher` 抓取 + 文件缓存 + stale | 已实现缓存/回退；缺实网验证的备用源 |
| `backend/app/services/bias/job.py` | `BiasJob` 落库 | stale 透传已修 |
| `backend/app/services/thermometer/service.py` | `save_multi_items` / 读取 | 已修（落库兼容 + stale 透传 + 去过滤） |
| `backend/app/services/thermometer/jobs.py` | `TemperatureJob` 校验 | 已放行 multi 类型 stale |
| `backend/tests/services/bias/test_multi_stale_chain.py` | 链路实证测试 | 4 条，passed |
| `frontend/src/api/temperature.ts` | `MultiItemsResponse` 类型 | 已补 `stale` |
| `frontend/src/views/temperature/index.vue` | 乖离度表 + 滞后提示 | 已加横幅 / 标签 |

---

## 9. 参考链接

- akshare issue #7027（80.push2 子域被封）：https://github.com/akfamily/akshare/issues/7027
- akshare issue #7099（RemoteDisconnected 频发）：https://github.com/akfamily/akshare/issues/7099
- akshare 官方文档：https://akshare.akfamily.xyz
- `akshare-proxy-patch`（社区绕过方案）：https://github.com/helloYie/akshare-proxy-patch

---

## 10. 最新进展记录

- 2026-08-02：应用层全部修通并测试通过（12 passed）；产出本手册，明确断点在数据源层。
- 待办：方向 A（退出代理跑 diag_em）坐实根因；方向 C 备用源待退出代理后实网验证。
