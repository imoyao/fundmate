# 个股估值分位数据源探针（#2944，2026-11-06）

> 状态：**已真机实测**（不是静态推断）。结论：**万得股票域已有可用的个股 PE/PB 历史分位，且一次问句可批量取多只 ⇒ 不启动 iFinD 配额评估，也不走「同行业相对分位」降级形态**。
> 本卡只做「先探数据源」这一步；接入实现另开卡跟踪，落地前须按 §5 重跑一次。
> 证据：本文 §2 内嵌脱敏真机返回（问句 / 返回行数 / 关键字段名 / 数值）；一次性脚本与原始输出在 worktree 的 `.tmp/`（Git 忽略区，未入库）。

## 0. 结论先行

| 卡面待判问题 | 结论 | 依据 |
|---|---|---|
| 万得股票域有没有个股估值分位工具 | **有** | `tools/list` 返回 10 个工具；`get_stock_fundamentals` 的 description 明写「PE、PB、PS（TTM 口径）、股息率、总市值与流通市值**及其历史分位数**，随交易日变动」；真机问句返回近 5 年 PE/PB 分位（§2.3） |
| 要不要回 iFinD 配额评估 | **不要** | Wind 已满足「个股估值历史分位」这一原始诉求；本次 **0 次 iFinD 调用** |
| 要不要走降级形态（同行业相对分位） | **不要** | 拿到的是正式历史分位，不是「只给绝对值」的降级，故无需在卡面写「它不回答什么」 |
| 是否覆盖港美股 | **未验证，不宣称** | 只测了 3 只 A 股；#1785 另议 |

⚠️ #2944 卡面把 `get_stock_fundamentals` 写成「只出现在 #2749 评论里、候选待确认」。本次实测把它从「候选」变成「**上游已确认可用**」——但仓库代码仍只登记 2 个能力（`backend/app/services/mcp/providers/wind_stock_data.py:44-50`）。「上游有」与「本仓已接」是两件事，别混为一谈。

## 1. 为什么必须真机

仓库内证据只够判定「没验过、更没接」，不够判定「上游有没有」：

- `wind_stock_data.py:29-33` 把 `get_stock_fundamentals` / `get_stock_price_indicators` 等明确标为**留白**；`stock_search`「留给人工探针」，全仓零调用方、零测试；
- 2026-10-30 那次 17 端点采样只在 `wind_direct.py:6-8` 留下「10 个能拉到工具」的计数，**逐工具 `tools/list` 清单从未落盘**；
- `backend/app/tools/mcp_probe.py:60` 硬编码 `_PROVIDER = 'wind'`，`--list` 打的是静态能力表，`transport.py` 没有 `tools/list` 请求构造 —— 现成 CLI 探不到股票域。

按 `ark-model-availability-2026-09-28.md:16` 的「写『可用』必须是第 3 层实测 OK」纪律，只有真机 `tools/list` + 问句能定论。

## 2. 探针方法与真机输出

### 2.1 方法

- 时间：2026-11-06 21:15–21:17（本机）；provider `wind_stock`；URL `https://mcp.wind.com.cn/vserver_stock_data/mcp/`。
- 凭据只读 `backend/.env` 的 `WIND_MCP_TOKEN`（同一张 Token 覆盖全 Wind 域）；地址走 `WIND_MCP_BASE` 默认值，可用 `WIND_STOCK_MCP_URL` 定向覆盖。**本文不含任何凭据值**。
- 共 **8 次 HTTP 请求**，全部只读：`initialize` → `notifications/initialized` → `tools/list` → 5 次 `tools/call`；无写接口、无 iFinD 调用、不写 `mcp_call_logs`、不改任何业务表。
- 返回统一是 `{"data": {"data": [{"columns": [...], "rows": [...]}]}}` 表格形状（行情快照那次是 `{"data": {"columns": ..., "rows": ...}}`）。

### 2.2 `tools/list`：10 个工具

| 工具 | 入参 | 与个股估值的关系 |
|---|---|---|
| `get_stock_fundamentals` | `question` | **本次正解**：财务原始指标 + 衍生估值指标（PE/PB/PS/股息率/市值）及其历史分位数 |
| `search_stocks` | `question` | 自然语言反查，也能返回「最新市盈率在历史中的分位数」（**上市以来**口径） |
| `get_stock_price_indicators` | `windcode` + `indexes` | 行情快照（时点、非时间序列），**不含估值**（§2.4） |
| `get_risk_metrics` / `get_stock_events` / `get_stock_kline` / `get_stock_basicinfo` / `get_stock_equity_holders` / `get_stock_quote` / `get_stock_technicals` | `question` 或结构化 | 与估值分位无关；`get_stock_basicinfo` 是已接入的 `stock_industry` |

`tools/list` 逐工具 `inputSchema` 与 description 摘要已内嵌在本文，故「10 个工具」这一结论可复核，不必重跑清单。

### 2.3 五条问句与返回（真机）

| # | 工具 / 参数 | HTTP | isError | 行数 | 关键字段 |
|---|---|---:|:---:|---:|---|
| 1 | `get_stock_fundamentals`：`600519.SH 贵州茅台 的市盈率 PE(TTM)、市净率 PB(LF) 当前值，以及最近 5 年历史分位数分别是多少？` | 200 | false | 2 张并列估值表 × 各 1 行 | `最新市盈率在近5年的分位数`、`最新市净率在近5年的分位数` |
| 2 | `get_stock_price_indicators`：同上问句塞进 `question` | 200 | **true** | 0 | 返回文本 `缺少必填参数: windcode` |
| 3 | `search_stocks`：`查询 600519.SH 贵州茅台 的市盈率 PE 历史分位数字段` | 200 | false | 1 | `最新市盈率在历史中的分位数`、`上市以来市盈率最大序号` |
| 4 | `get_stock_fundamentals`：`600519.SH、000858.SZ、601318.SH 这三只股票的最新市盈率在过去5年的分位数分别是多少？` | 200 | false | **3**（一次返回 3 只） | `最新市盈率在过去5年的分位数`、`过去5年市盈率最大序号` |
| 5 | `get_stock_price_indicators`：`{"windcode": "600519.SH"}` | 200 | false | 1 | `最新成交价` / `前收盘价` / `今日开盘价` / `今日最高价` / `今日最低价` / `成交量` / `Wind代码` —— **无 PE/PB/分位** |

关键返回片段（脱敏后原样，足以复核）：

```json
// #1 单只，两张并列表各 1 行；日期 2026-11-06
{"columns": [{"name":"Wind代码"},{"name":"证券简称"},{"name":"近5年市盈率"},{"name":"日期"},
              {"name":"近5年市净率"},{"name":"近5年市盈率序号"},{"name":"近5年市盈率最大序号"},
              {"name":"最新市盈率在近5年的分位数","unit":"%"}],
 "rows": [["600519.SH","贵州茅台",22.1075,"2026-11-06",6.6974,398,1212,32.7828]]}
// 第二张表：最新市净率在近5年的分位数 = 8.3402（序号 102 / 1212）

// #4 批量，一次 3 行
{"columns": [{"name":"Wind代码"},{"name":"证券简称"},{"name":"过去5年市盈率"},{"name":"日期"},
              {"name":"过去5年市盈率序号"},{"name":"过去5年市盈率最大序号"},
              {"name":"最新市盈率在过去5年的分位数","unit":"%"}],
 "rows": [["000858.SZ","五粮液",23.9895,"2026-11-06",832,1212,68.621],
          ["600519.SH","贵州茅台",22.1075,"2026-11-06",398,1212,32.7828],
          ["601318.SH","中国平安",10.0121,"2026-11-06",1183,1212,97.6053]]}
```

### 2.4 负结论可复核（卡面验收项）

`get_stock_price_indicators` 是本次唯一「拿不到估值」的工具，失败形态分两层，均**不是**「Wind 没有估值」：

1. **问句形态**：该工具 inputSchema 是 `windcode` + `indexes`，塞 `question` ⇒ HTTP 200 但 `isError: true`、`缺少必填参数: windcode`；
2. **正确参数形态**：`{"windcode": "600519.SH"}` ⇒ HTTP 200、1 行行情快照，列全是价量字段，无估值/分位；description 也写明「时点数据、非时间序列」，指标清单只到涨跌幅/成交量/换手率。

⇒ 下一个人不必重跑这条路径：估值分位走 `get_stock_fundamentals`，不要走行情快照工具。

## 3. 三个必须带进实现的坑

1. **列名随问句变化**。同一工具两次问句分别返回「近5年市盈率」/「过去5年市盈率」、「最新市盈率在**近**5年的分位数」/「最新市盈率在**过去**5年的分位数」。自然语言问句不是稳定契约 ⇒ 实现须固定问句模板 + 做列名归一，禁止按单一列名硬取。
2. **口径混用**。`get_stock_fundamentals` 给「近/过去 5 年」，`search_stocks` 给「上市以来」（茅台 32.7828% vs 32.7987%，看似差 0.02 实为窗口不同）；UI 必须标注窗口，别把两种分位混成一个数。
3. **不能复用 `source='wind_valuation'`**。`thermometer/wind_valuation.py` 落 `market_multi_items`，`item_type` 只有 `index|industry`、唯一键 `(source, item_type, item_code, collected_at)` 无个股位置，指标是成份股加权。个股需另定落库形状与 `source`。

另：批量实测 **3 只/次返回 3 行**，但**单次上限未测**。卡面「单次调用能批量几只」虽针对 iFinD，Wind 实现前同样要按用户持仓规模实测上限，不能拿 3 只外推。

## 4. 边界与后续（本卡不做什么）

- **不启动 iFinD 配额评估**：卡面「2000 次/期」在仓库内零落盘证据（仅见卡面措辞，iFinD 数据接入代码亦为零），本次也未产生任何 iFinD 调用；若日后 Wind 不可用再另开卡评估。
- **不改代码**：不动 `wind_stock_data.py` 能力表、不动 `thermometer/wind_valuation.py`、不新增表/列/job/页面 —— 「先探数据源」的范围止于结论。
- 不覆盖港美股（#1785）、不做同行业相对分位、不解决基金持仓股加权分位（`thermometer/README.md` 的 P0 规划）、不塞「击败 X% 基民」这类无源指标。
- **接入实现另开卡**，至少包含：① 能力表登记 `stock_valuation` → `get_stock_fundamentals`；② 固定问句模板 + 列名归一；③ 批量上限实测；④ 落库形状与 `source`；⑤ 口径窗口标注；⑥ 持仓股范围按「用户触达口径」（`positions ∪ watchlist`），不做全市场扫描。

## 5. 复跑方式与复跑缺口

- **现成 CLI 探不到**：`pdm run mcp-probe` 的 `_PROVIDER = 'wind'` 写死、`--list` 只列静态能力表、`transport.py` 无 `tools/list`。复跑需对 `/vserver_stock_data/mcp/` 自行发 `initialize` → `notifications/initialized` → `tools/list` → `tools/call`，或先给探针 CLI 加 `--provider` / `--list-tools`（属实现卡范围）。
- 前置：`WIND_MCP_TOKEN`（必填）；`WIND_MCP_BASE` / `WIND_STOCK_MCP_URL`（可选覆盖）。按 `mcp_probe.py` 退出码纪律：2 = 本地配置缺失「**没有结论**」，不得据此写「Wind 没有」。
- **历史快照只代表当日**：上游订阅范围与列名可能变；实现前重跑一次，别把本文数值当长期契约。

## 6. 关联

- #2944（主卡）、#2749（拆卡来源）、#2758（宽基 / 申万一级行业估值，口径不可复用）、#1785（港美股）
- `backend/app/services/mcp/providers/wind_stock_data.py`、`backend/app/tools/mcp_probe.py`、`backend/app/services/thermometer/wind_valuation.py`
- `docs/working-notes/fund-holdings-probe-2026-09-30.md`（探针报告骨架）、`docs/working-notes/external-source-policy-2026-09-30.md`（负结论措辞）、`docs/working-notes/ark-model-availability-2026-09-28.md`（「可用」须实测纪律）
