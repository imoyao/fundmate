# 账外孤儿类现金流水对账核实记录（2026-11-10）

> 关联：[#3031](https://github.com/imoyao/fundmate/issues/3031) / `docs/design/allocation-governance.md` §五
> 复现脚本：`scripts/reconcile_orphan_cash_flows.py`（**只读**，`mode=ro`，不改任何数据）
> 数据：本机 `backend/invest.db`，2026-11-10 实测；dev server `127.0.0.1:8848`

## 一、为什么要核实

`LedgerCashLikeCard.vue:81-87` 写着「本区块可能混有跨账本重复导入…请把本区块视为待核实」。
G2 要把「已核实类现金 → `liquid`」写进归置规则、G4 要把它计入五笔钱分母，
所以这 46.5 万到底是**错账**还是**可归置**，必须先有逐笔可复核的结论，不能凭一句 UI 文案。
本轮按用户要求「对账流水核实记录下来」，把结论与复现方式一并留档。

## 二、复现命令

```bash
# 直接调用服务层真相源（推荐，口径同源）
PYTHONPATH=backend python scripts/reconcile_orphan_cash_flows.py \
  --db backend/invest.db \
  --csv /tmp/orphan-cash-flows.csv --json /tmp/orphan-cash-flows.json

# 或只在本仓根目录跑聚合结论（不落盘）
python scripts/reconcile_orphan_cash_flows.py --db backend/invest.db
```

脚本优先 `from app.services.summary_service import orphan_flow_delta`；
app 包不可用时退到脚本内镜像并**在 stderr 显式告警**，绝不静默冒充同源。
本机实测该 import 因 `No module named 'dotenv'` 失败（`summary_service` 会连带拉起 flask/sqlalchemy），
所以另加一道 **AST 常量同源校验**：静态解析 `summary_service.py` 顶层的 5 组
`_ORPHAN_FLOW_*` 常量与脚本内常量逐项比对，漂移或缺失就直接退出码 1、拒绝出结论。
零依赖，不 import 也能把「同源」钉死。

镜像口径是否等价，还有一道**数值自校验**：脚本算出的合计 465,178.56 与
`/api/summary/cash-like/` 的 `total_amount` 逐分一致；若口径漂移，这个数必然对不上。

交叉验证（对账中心真实出口）：

```bash
curl -s http://127.0.0.1:8848/api/reconciliation/ghost-duplicates/   # → data.groups = []
curl -s http://127.0.0.1:8848/api/summary/cash-like/                  # → data.total_amount
```

## 三、实测结果

对象：`position_id IS NULL AND asset_type IN ('money_fund','reverse_repo')`，共 **222 笔**。

### 3.1 净额口径复现（与 `/api/summary/cash-like/` 对齐）

| 项 | 分 | 元 |
|:---|---:|---:|
| 本金净额 | 46,509,682 | 465,096.82 |
| 收益桶（`dividend_cash` 等） | 8,174 | 81.74 |
| **合计** | **46,517,856** | **465,178.56** |

与 `/api/summary/cash-like/` 的 `total_amount=465178.56` **完全一致**，说明口径复现无误。

按账本拆分：

| ledger_id | 本金净额（元） | 收益（元） |
|---:|---:|---:|
| 12 | 464,705.93 | 81.74 |
| 20 | 390.89 | 0.00 |

方向判据来自 `summary_service.py:276-307` `orphan_flow_delta`：buy/deposit 正、sell/withdraw 负、
`dividend`/`dividend_cash` 进收益桶正、`dividend_tax` 进收益桶负、`split`/`unknown` 不进桶。
222 笔**没有**不进桶的行。

### 3.2 跨账本重复：**0 组**（重要修正）

| 判据 | 结果 |
|:---|:---|
| `/api/reconciliation/ghost-duplicates/` | `data.groups = []`（0 组） |
| 按 `scan_cross_ledger_duplicates` 指纹在 222 笔内复算 | 0 组 |
| `import_hash` 重复 | 1 组 / 3 行，**同账本**；跨账本 0 组 |
| `status` 分布 | 222 笔全 `success` |
| `confirm_date` 缺失 | 0 |

`scan_cross_ledger_duplicates`（`summary_service.py:1365-1424`）扫的是
`family_id + ledger_id 非空 + status='success'` 的**全部**交易流水，
指纹为 `(confirm_date, symbol_identity, txn_type, amount)`。
本批 222 笔全部满足扫描条件，所以 **0 组是「扫过且无重复」，不是「被过滤掉没扫到」**。

⇒ **结论**：`LedgerCashLikeCard.vue` 那句「可能混有跨账本重复导入」是历史保守文案，
在本机数据上**不成立**。我上一轮把它当成风险依据，据此收紧 G2/G4，理由需要更换（见 §四）。

按脚本的项目指纹（`confirm_date + symbol + txn_type + amount`）复算，同账本成对行
**3 组 / 7 行**。初筛阶段曾用更宽松的 `(symbol, trade_date, abs(amount))`（忽略方向与类型）
得到 11 组 / 24 行——两者判据不同、数字不可混用，**本节以项目指纹为准**。
例如 id `1658/1659`（同日 100,061.00 元 buy/sell）是当日申赎对冲，
属正常交易形态，不构成跨账本重复证据。

### 3.3 真正的问题：来源不可追溯

| 字段 | 缺失 / 异常 |
|:---|:---|
| `trade_date` | **162 行为空**（另有 7 行带 `00:00:00.000000` 时间后缀，格式混杂） |
| `symbol` | **158 行为空** |
| `source` | **222 行全为 NULL** |
| `import_hash` | 7 行为空 |
| `entry_status` | 158 行 NULL、53 行 `pending_cash`、11 行 `orphan` |

这 162 行几乎全在 ledger 12，流水**毛毛额**合计 ¥1,353,022.49（buy/sell 大量对冲后净额才是 46.47 万）。
它们有 `confirm_date` 但无 `trade_date` / `symbol` / `source`，
说明是早期导入只落了确认日，**无法逐笔下钻对账、无法反查来源文件**。

`entry_status` 三态混杂也印证了 `summary_service.py:261-262` 的注释：
历史导入器早期数据 `entry_status` 不统一，所以净额口径刻意用 `position_id IS NULL` 而非 `entry_status`。

## 四、结论与对方案的影响

1. **「疑似错账」这一条排除**：跨账本重复 0 组，且净额与 cash-like 端点逐分对齐，
   46.5 万不是重复导入导致的虚增。
2. **约束仍然存在，但理由换成「可追溯性不足」**：162 行来源不可追溯，
   在「能逐笔下钻」之前把它们洗成确定的「活钱」，等于把不可审计的数据变成确定数据。
   因此 G2 仍不自动把类现金判为 `liquid`，G4 仍不把它计入分母，治理期间「活钱」保持空态提示。
3. **待用户确认的新决策**：
   - (a) 先补元数据治理（回填 `trade_date` / `symbol` / `source` / `import_hash`），再放行 G4；
   - (b) 接受「带待核实标签」直接入桶，卡片显示「账外·待核实」并提供下钻入口；
   - (c) 本轮只做资产行与持仓归置，类现金留到对账后另开卡。
   本轮按「核实记录下来」执行，**不擅自放行、不改任何真实数据**。
4. `LedgerCashLikeCard.vue:81-87` 的文案建议在 G5 一并修正（把「可能混有跨账本重复导入」
   改为「来源元数据待补，暂不参与配置分布」），避免文案与实测结论长期打架。

## 五、留档清单

| 产物 | 位置 | 是否提交 |
|:---|:---|:---|
| 核实结论（本文） | `docs/working-notes/cash-like-orphan-flows-2026-11-10.md` | 是 |
| 可复现只读脚本 | `scripts/reconcile_orphan_cash_flows.py` | 是 |
| 逐笔明细 CSV（222 行） | 脚本 `--csv` 产物，本机临时目录 | **否**：含个人财务流水，不进公开仓库；需要时重跑脚本生成 |
| 聚合结论 JSON | 脚本 `--json` 产物，本机临时目录 | 否 |

> 设计取舍：把「记录」做成**脚本 + 结论文档**，而不是把 222 行明细静态提交。
> 这样既能随时复核，又不把逐笔金额写进公开仓库；脚本每次都从真库现读，不会出现明细过期。
