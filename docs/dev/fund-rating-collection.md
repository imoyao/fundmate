# 晨星星级评级采集设计（#1440 落地）

> 状态：**设计评审中，未写代码** · 2026-10-24 · 关联 [issue #1440](https://github.com/imoyao/fundmate/issues/1440)

---

## 0. 结论先行

1. **晨星 3 年期星级评级可以从东财聚合页直接采到**，不需要爬晨星官网（Akamai 反爬），也不需要 Scrapling——issue #1440 的调研结论成立，且本文档已完成其"待验证"清单的全部实证（§1）。
2. **平台晨星 MCP 的定位是"对账核验器"，不是生产采集链路**（§7）：当前会话工具不可调，且架构上后端接不了平台 OAuth 令牌。
3. 本设计相对 issue 待办有**两处修正**（均有实证依据）：
   - 解析逻辑**自写**，不调 `ak.fund_rating_all()`——akshare 的内部解析是位置黑箱，改版即静默错位（§3）；
   - 存储**先落当期值列、不建快照表**（§5，决意点 D1 待拍板）。

---

## 1. 数据源实证（2026-10-24 实测，非文档转述）

**数据源**：`https://fund.eastmoney.com/data/fundrating.html`（天天基金·基金评级总汇，晨星评级由晨星授权、东财聚合展示）。

| 验证项 | 实测结果 |
|---|---|
| 端点存活 | 18,568 只基金，**每记录 27 字段**（与 akshare `fund_rating_all()` 列映射当前完全对齐） |
| 晨星评级覆盖 | 14,315 / 18,568 = **77.1%**；分布 1★1458 / 2★3201 / 3★5005 / 4★3185 / 5★1466 / 空 4253 |
| 评级口径 | **3 年期**（反证链见下） |
| 旁证 | 756 只货币基金**零**晨星评级——符合晨星不给货基评级的惯例 |

### 1.1 字段映射表（位置即契约，0-based）

`var fundinfos` 字符串，记录以 `|_` 分隔、字段以 `|` 分隔：

| 位置 | 列名 | 用途 |
|---|---|---|
| 0 / 1 / 2 / 3 / 5 | 代码 / 简称 / 类型 / 基金经理 / 基金公司 | 关联键与展示 |
| 7 | 5星评级家数 | 各家给 5 星的总数（自洽校验用，§2.4） |
| 8 / 9 | 疑似海通证券 / 较上期 | akshare 未解析，**本设计不采** |
| **10** | **招商证券（3年）** | 已验证 |
| 12 | 上海证券（3年） | 已验证 |
| **14** | **晨星评级（3年）** | **本设计唯一目标** |
| **15** | **晨星较上期（delta）** | 实测 000001 = -1（上期降 1 星） |
| 16 | 济安金信 | 已验证 |
| 18 | 手续费 | 本设计不采 |

### 1.2 位置映射的 100% 反证链

用各家**评级专页**（akshare 的 `fund_rating_sh` / `fund_rating_zs` / `fund_rating_ja` 同源）反查综合页：

| 专页 | 专页字段 | 综合页位置 | 命中 |
|---|---|---|---|
| fundrating_2（招商证券） | 3年评级 | pos10 | **15,576 / 15,576** |
| fundrating_3（上海证券） | 3年评级 | pos12 | **382 / 382** |
| fundrating_4（济安金信） | 评级 | pos16 | **46 / 46** |

三家专页的 3 年期评级与综合页对应位置 100% 相等 ⇒ 综合页各家列均为 3 年期口径；pos14 = 晨星由"剩余机构排除法 + akshare 映射"双重确认。样本抽查 000001=3★、161725=1★、110011=1★ 均与公开表现一致。

### 1.3 akshare 路线的隐患（为什么不直接调 `ak.fund_rating_all()`）

akshare 实现（`akshare/fund/fund_rating.py`，2023-12-12 版）两步位置解析：`data_text.split("var")[6]` 取第 7 个 `var`，再按 27 列**序号硬映射**。上游一旦增删字段或调整顺序：要么字段数对不上、pandas 响亮报错；要么**数量不变仅换序**——静默把招商证券的值当晨星落库。今天对齐（27 字段全表一致），但黑箱漂移时我们无感知，且 akshare 升级节奏不受我们控制。

---

## 2. 采集契约

### 2.1 请求

- `GET https://fund.eastmoney.com/data/fundrating.html`，走全局 `requests_patch` 通道（东财该端点无反爬，历史上该域无 TLS 问题）。
- 响应 ≈3.1MB，单次请求返回全市场列表 ⇒ 满足 `docs/spec/data-strategy.md` §4.3.3「`__full__` 仅当单次调用不产生逐条外部请求」的全量例外（同 `fund_scale` 先例）。

### 2.2 解析目标

`div#fundinfo > script` 内的 `var fundinfos = "..."`；记录分隔 `|_`，字段分隔 `|`；按 §1.1 表取 pos14 / pos15（及 pos0/1/2 作关联键）。

### 2.3 归一化

- 评级：`'' → None`；`'1'~'5' → int`。
- delta：`'' → None`；否则转 int。
- 基金代码：6 位数字字符串，前导零保留（`'000001'`）。

### 2.4 校验规则（响亮失败，不静默错位）

1. **字段数恒等**：每条记录必须 27 字段；出现任何其他长度 ⇒ 整体抛错、不写库。
2. **代码形态**：`^[0-9]{6}$`。
3. **评级值域**：`{'', 1..5}`；越界即结构漂移信号。
4. **delta 值域**：整数且 `|v| ≤ 4`（星级 1–5，单期理论最大变 4；实测仅见 -1/0/1）。
5. **5星家数自洽**：pos7 == 各家 5 星列计数之和（廉价一致性断言）。
6. **存在性探针**：`000001` / `110011` / `161725` 必须出现在结果中——用**存在性而非固定星级值**（评级月度会变，固定值会误报）。
7. **分布漂移告警**：记录数或有效评级数与上期偏差 > 30% ⇒ 记 WARNING（不阻断，供人工复核）。

### 2.5 失败语义

- 结构不符（校验 1–5 任一失败）⇒ 抛错，**不写库**，上期数据自然保留。
- 空返回 / 上游 5xx ⇒ job 层 `_allow_empty_data = True`（同 `fund_scale_job.py:40-42`），前端降级显示 `—`。

---

## 3. 解析实现范围

`fetch_fund_rating()` 预计 ~60 行（取数 + 切分 + §2.3/§2.4 校验），放在 `AkshareAdapter` 内。**不进** `DataSourceAdapter` 抽象基类——与 `fetch_fund_scale` 同例（该法就是 AkshareAdapter 私有方法，不在 `base.py` 中）。项目已有"akshare + 直连东财端点"混合先例：`akshare_adapter.py:91` 的 `_EM_HYPZ_URL`。

akshare 依赖保留（其余方法在用），仅本方法不走它的解析。

---

## 4. 代码落点（file:line 级）

| 文件 | 改动 |
|---|---|
| `backend/app/services/adapters/akshare_adapter.py` | 新增 `fetch_fund_rating() -> List[dict]`（§2 契约） |
| `backend/app/services/sync/jobs/fund_rating_job.py` | 新建 `FundRatingSyncJob(SyncJob)`，范本 `fund_scale_job.py`（全量例外、只更新本地已有基金、`bulk_update_by_key` 批量化 #2522 先例） |
| `backend/app/services/sync/orchestrator.py` | ① `_register_jobs()`（:264 起）注册 `self.jobs['fund_rating']`；② job 计划第三梯队加 `('fund_rating', ['__full__'])`（:214 附近）；③ `WEEKLY_JOBS`（:135）加入 `'fund_rating'`——上游月度更新，日跑是 3MB×365 的无效下载 |
| `backend/app/core/migrations.py` | 加列 migration，范式 `_add_columns_if_missing`，参考 `migrate_advisor_portfolio_metrics`（:509，可空列直接 ALTER ADD COLUMN） |
| `backend/app/domains/funds/models.py` | `Fund` 模型加列（§5 方案 A） |
| `backend/tasks.py` | **无需改动**——`grab.job <name>` 本就是透传（:104-109），`grab.all` 自动覆盖新 job |

**频率说明**：入 `WEEKLY_JOBS` 后是"双保险"——日常 daily 跳过，weekly 批次执行（orchestrator.py:172 注释的名录类同款机制）。晨星月度更新，周频足够且能在更新后一周内落到库。

---

## 5. 存储设计（D1 待拍板）

### 方案 A（推荐）：`funds` 表加当期值列

```text
morningstar_rating        SMALLINT NULL   -- 1~5，空=无评级
morningstar_rating_delta  SMALLINT NULL   -- 较上期变化，空=未知
morningstar_rating_asof   DATE NULL       -- 数据快照日期（东财页当日）
```

- 与 `scale` / `recent_shares` 先例完全一致（当期值覆盖写）。
- 符合"按需存、禁止全量堆砌"：当前**全仓无任何评级消费方**（2026-10-24 全仓 grep 实证），无消费者即无历史需求；delta 的含义在写入期已定格。
- 升级路径：方案 B 可随时从 A + 东财日期版页面重建（评级月度更新，历史有限）。

### 方案 B（issue 原待办）：`fund_rating` 快照表

`(fund_code, rating_date, rating, delta)` 追加式。保留历史，代价是月增 ~1.4 万行、且当前没有读者。

**建议 A**；若产品侧明确要做"星级变化趋势"展示，再升 B（届时本设计的解析层原样复用，只换 job 的 `_save_data`）。

### D2：其他机构评级采不采

招商 / 上海 / 济安三家的坐标已在同一响应里验证过（§1.2），加列即可扩展。**建议否**——issue 目标只是晨星，避免一次采全市场用不上的数据。

---

## 6. 调度与成本

- 单次 HTTP ≈3.1MB → 18,568 条解析（纯字符串切分，秒级）；
- 写入只更新本地已有基金（同 `fund_scale`，不把全市场灌进来）；批量化 UPDATE（#2522 先例，Turso 上逐行 = 每行一次 HTTP 往返）；
- 无逐只外部请求，`data-strategy.md` §4.3.3 全量例外成立；
- 周频执行，估算流量 ~13MB/月。

---

## 7. 晨星 MCP 的定位（回应"优先用 MCP 完成"）

### 7.1 现状（2026-10-24 实测）

- 平台连接器状态 `connected`，但**本会话工具索引为空**：多组 ToolSearch 查询全负，直接调用报 `not found in the deferred tools index`。
- 恢复路径：用户在连接器菜单对晨星连接器重连（或新开会话），之后我才可实测其工具返回。

### 7.2 架构约束（为什么它进不了生产链路）

- 平台 MCP 是 **agent 侧工具**：OAuth 令牌在平台侧，Flask 后端拿不到。
- 后端要接 MCP，需要 `MORNINGSTAR_MCP_URL` + `MORNINGSTAR_MCP_TOKEN`（`services/mcp/providers/wind.py` 的 `WindEndpointMissing` 教训：没有可确认的地址常量时，宁可不写默认值，让缺失当场抛出）。目前**两者均无证据存在**。

### 7.3 MCP 的三步用法

1. **对账（本 issue 内闭环）**：连接器恢复后，用 `getFundPerformance` 对 N 只抽样基金（含 000001/110011/161725）交叉验证 pos14；不一致时以晨星为准并排查东财口径——这把 issue"待验证"里的口径遗留问题变成可持续机制。
2. **富化（另开卡）**：费率、持仓穿透、经理信息等东财没有的维度。
3. **未来后端 provider（S4+）**：若晨星开放可编程端点，按 `wind.py` 范本加 `MorningstarProvider`（`services/mcp/providers/morningstar.py` + 注册表 + 凭据登记），设计文档 `docs/dev/mcp-integration.md` §4.2 的钩子已就位。

---

## 8. 回滚

- 新增列全部可空；停 job、删列均无损；
- 解析校验失败时不写库，上期数据自然保留；
- 数据为 L3 缓存性质（同 `fund_scale` 分层定位），前端无消费方时纯冗余、不出事。

---

## 9. 未决项（需拍板）

| # | 事项 | 建议 |
|---|---|---|
| D1 | 存储：当期值列（A） vs 快照表（B） | **A** |
| D2 | 是否同批采招商/上海/济安 | **否**，先晨星 |
| D3 | 前端展示卡片 | 另开 issue（当前绿地） |
| D4 | fund_rating 入 WEEKLY_JOBS | **入** |

---

## 10. 参考

- issue #1440：Scrapling 评估与晨星评级采集方案
- akshare 源码：`akshare/fund/fund_rating.py`（`fund_rating_all` / `fund_rating_sh` / `_zs` / `_ja`）
- 本项目范本：`backend/app/services/sync/jobs/fund_scale_job.py`、`backend/app/services/sync/orchestrator.py`、`backend/app/core/migrations.py`
- 规范：`docs/spec/data-strategy.md` §4.3.3（全量例外）、`docs/dev/mcp-integration.md`（MCP provider 接入设计）
