---
title: 且慢官方调仓接口实测：调仓历史不必再靠快照推导
---

# 且慢官方调仓接口实测（2026-11-03）

> **一句话**：我们此前认定的「且慢没有官方历史调仓接口」是**错的**。
> `POST https://qieman.com/alfa/v1/graphql` 的 `Adjustment` operation 返回完整官方调仓
> （含主理人原文、逐基金调前/调后比例、调入调出语义），**匿名可取、签名可复刻、无需登录**。
> 基于「没有官方接口」建立的一整套快照推导（0.5pp 阈值、repair 脚本、免责声明、
> `has_official_rebalances=False`）**前提不成立**。

## 一、结论（先看这四行）

1. **接口存在且可用**：`POST /alfa/v1/graphql`，`operationName: "Adjustment"`。
2. **不需要 cookie、不需要登录、不需要 MCP token** —— 唯一的门槛是请求头 `x-sign`。
3. **`x-sign` 无密钥，算法写在公开 bundle 里**，可逐字节复刻（见 §二）。
4. **覆盖率实测 13/15**（抽样 15 个库内且慢组合）：2 个返回空的是真没有调仓
   （`LONG_WIN` 长赢计划、`SI000090` U定投，属计划/定投类），**0 个不可用**。

## 二、`x-sign` 算法（唯一门槛，已被复刻并验证）

来源：`https://cdn3.qieman.com/alfa/zeus-dist-po/js/app.3519f25d.js`，webpack 模块 `54165`
= `js-sha256`。同文件里的签名函数原样如下：

```js
Qe = function xSign() {
  var o = Date.now();
  return o + Re()(Math.floor(1.01 * o).toString()).toUpperCase().substring(0, 32)
}
```

即：

```text
x-sign = str(now_ms) + SHA256(str(floor(1.01 * now_ms))).hexdigest().upper()[:32]
```

（`.substring(0, 32)` 是把 64 位 SHA-256 十六进制**截前 32 位**，不是 MD5。）

**验证方式不是「读得像」**，是拿浏览器真实抓包的两组 `(时间戳, 签名)` 反算：

| 时间戳 | 预映像 `floor(1.01*ts)` | 抓包得到的后 32 位 | Python 复算 |
|---|---|---|---|
| 1793698943139 | 1811635932570 | `D8AD0383028C65F910AAA7802F0DCE58` | `D8AD0383028C65F910AAA7802F0DCE58` ✅ |
| 1793698943830 | 1811635932573 | `A31A6C5FD239FFE4543B5A9B2952DDB8` | 同上 ✅ |

顺带解出同一文件里的 `x-request-id`：`"zeus." + SHA256(...).slice(-20).toUpperCase()`，
20 位十六进制，与抓包 `zeus.EE6A9B40B372ED4B5467` 同形——它只是追踪号，不是校验项。

### 头部的三个必需/可选性（三组对照实测）

| 组 | 发送的头 | 结果 |
|---|---|---|
| A | 只有 `content-type` / `origin` / `referer` | 200，但 `data:null` + `INTERNAL_SERVER_ERROR`（`portfolio` 解析器失败） |
| B | A + `x-broker: 0008` + `sensors-anonymous-id` | 同 A |
| C | B + **抓包得到的 `x-sign`（已过期约 5 分钟、且不带 cookie）** | **200，49909 字节全量数据** |

⇒ `x-sign` 是唯一必需项；`cookie` 不需要。另可确认**签名与 body 无关**：
同一次页面加载里 body 长度 1716 与 359 的两个请求，`x-sign` **完全相同**。

## 三、返回结构（与前端现有字段的对应关系）

```text
portfolio.adjustments.totalCount            20
portfolio.adjustments.pageInfo              {hasMore, cursor}
portfolio.adjustments.adjustments[]:
  adjustmentId   1806373      ← 官方稳定主键（幂等键）
  date           2026-08-12T00:00:00+08:00
  comment        「市场的结构分化和调整…」   ← 主理人原文（我们快照推导永远拿不到）
  article        null（有则给 {text, link}）
  groups[]:
    categoryCode 3（混合型）/ 1（股票型）/ 4（货币型）
    movementName 调入|调出|调增|调减|持平
    beforePercent / afterPercent   0.04 = 4%
    parts[]:
      fund {fundCode, fundName}
      movementName  ← **逐基金的动作，与 group 的不同**（group 是分类汇总）
      beforePercent / afterPercent
```

两个必须注意的点：

1. **`groups[].movementName` 与 `parts[].movementName` 不是一回事**。实测 `ZH012926`
   2026-08-12 那一次：group 是「调减」，而内部 parts 同时含「持平 / 调出 / 调增 / 调减」。
   **取数要取 `parts`，不能取 group 的动作名**，否则整组基金被套上同一个动作。
2. 比例是**小数**（`0.04`），而库内 `pre_ratio/after_ratio` 存的是**百分点**
   （`10.31` 表示 10.31%）。换源时必须 ×100，否则显示成 `0.04%`。

## 四、覆盖率与分页

抽样 15 个库内且慢组合（`size=50`）：

| 结果 | 数量 | 说明 |
|---|---|---|
| 有官方调仓 | 13 | `ZH012926` 20 条 / `ZH030684` 35 / `ZH013136` 47 / `ZH012636` **118** / `ZH006498` 53 … |
| 空（真没有调仓） | 2 | `LONG_WIN`（长赢计划）、`SI000090`（U定投）——计划/定投类不是 `alfa/portfolio` |
| 不可用 | 0 | — |

- **`size=50` 是单页上限**：`ZH012636` 的 `totalCount=118` 但单页只回 50，
  必须按 `pageInfo.cursor` 翻页（`cursor` 是 base64 序号，如 `"MQ=="` = 1）。
- 分页实测：`ZH012926` `size=15` → 第一页 15 条 `hasMore=true cursor="MQ=="`，
  第二页 5 条 `hasMore=false`，合计 20 = `totalCount`。
- 非且慢组合按平台不该调用：`XCOVSEX`（天天基金）返回 `BAD_USER_INPUT 策略不存在`。

## 五、现状的代价（这套推导到底欠了什么）

| 缺陷 | 说明 | 官方接口是否解决 |
|---|---|---|
| **历史起点被截断** | 推导从**我们第一次抓到持仓快照**那天起算，更早的真实调仓**不可回溯** | ✅ 成立以来全量（`ZH012926` 最早到 2017-07-24） |
| **没有主理人说明** | `reason` 只能写「由 X 持仓快照推导（变化 N pp）」，用户看不到「为什么调」 | ✅ `comment` 是主理人原文，`article` 还有原文链接 |
| **微调被阈值吞掉** | `ADVISOR_ADJUST_MIN_DELTA_PCT = 0.5`（#1622 的 2×p99 标定）⇒ 低于 0.5pp 的真实调仓不记 | ✅ 官方给的是真正发生过动作的基金，不用猜 |
| **同一次动作被拆成多条** | 主理人分多日执行 ⇒ 每天都超阈值 ⇒ 落成多条（已登 tech-debt，实测 2/1378 段） | ✅ 官方以 `adjustmentId` 为一次动作 |
| **动作语义缺失** | 推导只能按比例增减推「加仓/减仓」，分不清「调入（新建仓）」与「调增」 | ✅ `movementName` 直接给 |

⚠️ 但**已有数据不能一律废弃**：`advisor_adjust_histories` 里的行分三类，
`source` 是分界线（`models.py:649` 的注释写着 `qieman(快照推导)`）：

- `tiantian` / `howbuy` 等**官方**行 —— 本来就走官方接口，不动；
- `qieman`（快照推导）—— 官方接口覆盖到的组合，应**以官方数据为准**；
- `qieman_manual`（手工导入）—— 人工灌的，保留。

## 六、落地建议（换源不需要改前端）

> ⚠️ 本节是**当时的建议稿**，实际实现与它有两处差异（`fetch_adjustments` → `fetch_rebalances`、
> `has_official_rebalances` → `official_rebalance_source`），**以 §九 的实施记录为准**。

现有通道是「后端表 → `/api/funds/advisors/<code>/adjusts/` → 前端 `Adjusts`」，
字段为 `adjust_date / reason / source / items[{fund_code, fund_name, op_name, pre_ratio, after_ratio}]`
（`fund_service.py:982` `build_advisor_adjusts`）。**官方数据能完整填满这套字段**：

| 现有字段 | 官方来源 |
|---|---|
| `adjust_date` | `date`（截 10 位） |
| `reason` | `comment`（主理人原文，比「推导」那句有用得多） |
| `source` | 新增值 `qieman_official`（与推导的 `qieman` 区分） |
| `op_name` | `parts[].movementName`（调入/调出/调增/调减/持平） |
| `pre_ratio` / `after_ratio` | `beforePercent*100` / `afterPercent*100` |

因此工作量集中在后端三件事：

1. **适配器**：`qieman_advisor_adapter` 增加 `fetch_adjustments()`（签名 + 分页 + 解析），
   `has_official_rebalances` 由 `False` 改 `True`；
2. **job**：`advisor_portfolio_job` 对且慢组合优先走官方接口（**幂等键 = `adjustmentId`**），
   接口失败 / 该组合不适用时**降级回快照推导**（保留现有实现，不删）；
3. **词表**：`op_name` 新增 `调入/调出/调增/调减` 四个值。
   ⚠️ **前端颜色映射必须同步**：`utils/advisorAdjust.ts` 的 `advisorOpTone` 目前只认
   `加仓/减仓`，其余一律 neutral ⇒ 官方数据会**整片变灰**（看起来像功能坏了）。
   颜色语义：`调入/调增 → add`、`调出/调减 → cut`、`持平 → neutral`。

**前端唯一需要改的**是「推导口径声明」的文案：现有实现按 `source` 判断
（`advisorAdjustModel.ts` 的 `derivedFromSnapshots`），换源后官方行自动不挂免责，
但 `source='qieman'` 的**历史存量行**仍会挂——这是对的，除非决定一并清洗。

## 七、待拍板（三件，互不阻塞）

> **三件均已于 2026-11-04 拍板**，处置与依据见 §九。

1. **#2853 怎么处置**：它让调仓**可见**（用户第一诉求），实现（共用列表 + 脚注层级）仍然有效；
   但正文与代码注释里「且慢没有官方调仓接口 / pmapi 五路径全返 SPA」**已是失实**，
   必须改成「我们尚未接入官方接口」。是**先合再换源**，还是**并进同一批**？
2. **存量快照推导行怎么处理**：官方覆盖到的组合，是（a）删除重灌、（b）并存但前端只显示官方、
   还是（c）保留为「历史补充」？**注意 (c) 会让同一时间段出现两套数据。**
3. **`LONG_WIN` / `SI000090` 这类计划型**：官方接口不适用，继续用快照推导（现状），
   还是干脆不显示调仓？

## 八、回滚

- 适配器/job 改动全部落在 `qieman_*` 分支内，**保留快照推导路径** ⇒ 把
  `official_rebalance_source` 改回 `None`（原 `has_official_rebalances = False`）即回到今天的行为，
  无需回滚数据。
- 数据侧按 `source` 可精确区分（`qieman_official` vs `qieman`）：清洗/重灌都只针对一个值。

## 九、实施记录（2026-11-04，含真机验证数字）

### 9.1 三件拍板结论（回应 §七）

| 待拍板 | 结论 | 依据 |
|---|---|---|
| #2853 与换源的先后 | 先合 #2853（已完成，dev tip `f2009c326`），换源另开一支 | 可见性是一件事、数据源是另一件；混在一支里回滚粒度太粗 |
| 存量推导行 | **删推导、以官方为准**，不并存 | (b) 只在前端藏起来 = 库里仍是两套真相；(c) 同段时间两套数据必然对不上 |
| `LONG_WIN` 类计划型 | **保留推导 + 改文案** | 官方接口对它们返回空（真没有调仓记录），推导是唯一来源 |

### 9.2 实现与 §六 建议稿的四处差异（都是踩过之后改的）

| 建议稿 | 实际 | 为什么 |
|---|---|---|
| `fetch_adjustments()` | `fetch_rebalances()` | 契约端口 `AdvisorPortfolioSource` 里这个数据面本来就叫 rebalances（天天基金适配器已实现同一方法）；另起名字会让 job 里长出平台分支 |
| `has_official_rebalances: bool` | `official_rebalance_source: Optional[str]` | job 需要的不是「有没有」，而是「官方行该写哪个 `source` 值」，落库与幂等判断都直接用它 |
| 幂等键 = `adjustmentId` | **仍是 `adjust_date`** | 实测 5 个组合 441 条调仓，`adjustmentId` ↔ `adjust_date` 严格 1:1（一次动作一天）；改键要动唯一约束 `(portfolio_id, adjust_date, fund_code)` 与既有 1378 行，收益为零 |
| `op_name` 映射成「加仓/减仓」 | **原样保留官方用词**，只按语义补 `op_code` | 主理人说「调出」跟「减仓」不是一回事（调出=清仓），抹平会丢信息。`调入→4 / 调增→2 / 调出→3 / 调减→3` |

另外两条实现口径：

- **持平行不落库**：官方把整个组合的调前/调后都回传，`movementName=持平` 占 50%~70%，
  全落会把列表淹掉；逐基金动作取自 `parts[].movementName`，**不是** `groups[]`（后者是分类汇总，踩过）。
- **比例是小数**：`beforePercent` / `afterPercent` 需 ×100 存百分点，否则全组合显示 0.17%。

### 9.3 存量处置（`backend/scripts/purge_advisor_stale_data.py`）

| 模式 | 判据 | 为什么这样判 |
|---|---|---|
| `--mode derived` | **纯库内比较**：同一 `portfolio_id` 同时存在 `qieman` 与 `qieman_official` | 不联网、不猜覆盖；没跑过同步的组合不会被误清（它还没有官方行） |
| `--mode fixtures` | 代码前缀 `ZH9000`（常量，不接受「名字像测试就删」） | 真实且慢码是 `ZH`+6 位数字，撞不上；有用户持仓引用则**拒删并报出** |

**job 侧也会清**：`_purge_derived_adjusts` 在该组合官方落库成功后同事务删推导行 ⇒
存量按组合**自愈**；脚本是「事后看结果对不对」的那一层，不是唯一的清理手段。

实测（本机 `invest.db`）：

- 换源同步时自动清：`ZH012926` 15 行、`ZH000129` 2 行；之后 `--mode derived` 干跑报「无」——
  两条写路径（job 内清 / 脚本清）结论一致；
- `--mode fixtures --apply`：清 9 个组合 + 4 条子行（`ZH900005` 2 持仓 + 1 调仓、`ZH900008` 1 持仓），
  清后四张子表**孤儿子行 0**；
- `--verify-no-regression`：跑 `test_advisor_profile.py`（15 passed）前后 `advisor_portfolios`
  均 105 行、`max(id)` 均 105 ⇒ **夹具不再落真实库**（conftest 的库安全网有效）。

### 9.4 真机验证（换源后实测，非推测）

| 组合 | 调仓行 | 调仓日 | 交叉验证 |
|---|---:|---:|---|
| `ZH012926` | 117 | 20 | 与探测脚本 `totalCount=20` 一致（换源前推导只有 15 行 / 7 日） |
| `ZH000129` | 302 | 138 | 最早 2014-01-03，官方成立以来全量 |

形态核对（`ZH000129` / `ZH012926`）：

- `reason` 空值 49 / 0 —— 官方 `comment` 本来就有空（`ZH000129` 是「阈值型」策略，部分调仓只给数字）；
- `pre_ratio` / `after_ratio` 无 `None`、**无 `pre == after`**（持平行确实被滤掉）、`after` 最大 100.0（百分点口径正确）；
- `op_name` 分布 `调入/调出/调减/调增`，`op_code` 与 §9.2 映射一致；
- `LONG_WIN` 15 行 / `LONG_WIN_S` 14 行 **仍是 `qieman`（推导）**，未被误清；
- 全库：`advisor_adjust_histories` 1802 行 = `qieman` 176 + `qieman_official` 419 + `tiantian` 1206。

### 9.5 未做 / 已知边界（别读成「全库已换源」）

- **另外 16 个组合仍是推导行**：它们还没跑过换源后的同步，下一次调度按时**按组合自愈**。
  这不是遗漏，是脚本刻意不做的部分（不联网、不猜覆盖）。
- **无 `QIEMAN_API_KEY` 时整个 QIEMAN 平台被跳过**（`_fetch_data` 的 `McpTokenMissing` 分支）——
  官方调仓接口本身匿名可用，但持仓/概览拿不到，落库没有意义。生产已配 token，本轮未改这层门禁。
- `ADVISOR_ADJUST_MIN_DELTA_PCT = 0.5`（#1622 的 2×p99 标定）**未动**：官方路径不用它，
  但计划型组合仍走推导，动了会连带改它们的行为。

