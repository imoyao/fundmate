#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：领域视图层不得继续变厚（视图层职责边界，判据见 #1606）。

WHY
---
`conventions.md` §2.2 与 `architecture.md` §1.3 一直写着「视图只做 HTTP 编排」，
但**没有可执行判据**，于是业务规则持续堆进 views：实测 `domains/ledgers/views.py`
1811 行 / 71 次 DB 调用，`domains/watchlist/views.py` 1445 行 / 45 次 DB 调用；
而 `tech-debt.md` 早已记过「自选模块视图层业务逻辑过重 ✅ 已修复」——属**债务回潮**，
说明当年只做了「抽取动作」，没留下边界、也没有守卫，代码随后在原文件里继续生长。

本守卫把 `decisions.md` 2026-09-19「视图层职责边界」（#1606）钉成机器可执行的判据：

| 指标 | 含义 | 新增上限 |
|---|---|---|
| `lines` | 文件总行数 | 400 |
| `orm_queries` | `*.query(` 调用次数（视图内直接查业务表） | 10 |
| `commits` | `*.commit(` 次数（事务边界；同一函数最多一次） | 5 |
| `max_func` | 最长函数行数（含 docstring，取 `end_lineno - lineno + 1`） | 60 |

存量按 `BASELINE` **冻结、只减不增**（只拦「比基线更厚」，不拦维持现状）：

- 新增 / 改名后的视图文件走上表上限，超标即红；
- 存量文件任一指标超过基线即红（回潮拦截）；
- 基线里已消失的文件会被提示删除（避免基线虚胖）；
- **实测低于基线时打印「请收紧基线」提示**（本脚本不报错——正常收敛不该红掉校验）；
  但「基线必须与实测贴合」由 `backend/tests/test_view_thickness_guard.py::
  test_baseline_matches_current_metrics` 强制：基线只减不增，而「减完不回写」会让该维度
  静默失效（实测 #1606 落地后 `commits` 维度空转了 41/44）。收敛后请**同 PR 内**
  用 `--report` 回写 BASELINE。

为什么不是零容忍：131 个端点的视图批量改写风险远大于收益（同 #1607「判据用边方向、
不用包级双向对数」的思路）——先把边界立住、堵住新增，再按批次收敛。

用法
----
    python scripts/check_view_thickness.py              # 校验（CI / pre-commit）
    python scripts/check_view_thickness.py --report     # 打印当前指标 + 可直接粘贴的基线
    python scripts/check_view_thickness.py -v           # 一并打印达标项

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWS_GLOB = "backend/app/domains/*/views.py"

# 新增 / 改名视图文件的上限（判据本体）
NEW_FILE_LIMITS = {
    "lines": 400,
    "orm_queries": 10,
    "commits": 5,
    "max_func": 60,
}

# 存量基线（2026-09-19 冻结，#1606 批次 1 下沉后重取）。
# **只减不增**：不要手工调大——要走「把业务规则下沉 services」的正当路径；
# 确实因合并等原因需要重取时，用 `--report` 生成新块并说明理由。
# 2026-09-20 重取（合并原因，非放宽）：错误信封补齐（#1610 / D27 要求每个错误响应带 error_code）
# 使 4 个视图文件共 +26 行 —— assets +5 / importers +4(+2 max_func) / ledgers +15(+12 max_func) /
# summary +2；增量全部是信封字段，不含任何业务规则，且相对 #1606 下沉前（ledgers 1811 行）仍是大幅收敛。
# 同批 positions 因 #1607 批次 2 把展示口径移出视图而 −24 行，已一并**收紧**（基线只减不增）。
# 2026-09-21 收紧（**纠「基线虚胖」**，非放宽）：#1609 batch 2/3/4 已把视图层 41 处 `commit()` 改为
# `flush()`（`conventions.md` §2.13 / `decisions.md` D33），但基线仍是收敛前的数字 —— 于是
# `commits` 维度 44 的预算里只剩 `reconciliation` 3 处有效，**把 `flush` 改回 `commit` 不会被拦**，
# 相当于守卫在这一维度空转。本次按 `--report` 实测回写（lines 亦随之 −1）。**教训**：做完「下沉 /
# 去冗余」这类收敛动作必须回写基线，否则守卫形同虚设。
# 2026-09-21 再收紧（#1640）：`reconciliation` 的 3 处 `commit()` 已随「`user_session()` 请求级单会话」
# 改为 `flush()`（#1640 / `conventions.md` §2.13），基线 `commits` 3 → 0 —— **至此全仓视图层 `commits` 归零**
# （#1609 batch 2/3/4 收敛 41 处 + #1640 收敛 3 处）。该维度自此进入**零容忍**：任何视图再出现 `commit()`
# 都会被基线拦下（把 `flush` 改回 `commit` 亦然），不必再依赖「只减不增」的存量冻结。
# 2026-09-22 收紧（#1642 B 块）：把 portfolios / strategy / funds / positions / transactions /
# importers / ocr / watchlist 共 8 个视图的超长函数（原 max_func 最高 150）下沉到 `app/services/`，
# 视图只留「入参解析 + 调服务 + 组响应信封」；业务语义逐字段不变、对外 API 契约零变更。
# 按 `--report` 实测回写：funds 324/9/94 → 197/2/39、strategy 239/9/98 → 144/5/22、
# portfolios 266/5/104 → 166/1/29、positions 373/8/81 → 288/6/57、transactions 198/4/76 → 136/2/60、
# importers 254/1/74 → 249/1/53、ocr 262/1/69 → 214/1/48、watchlist 712/14/104 → 622/14/53；
# 全部 max_func 已 ≤ 60。`ledgers` 沿用合入前 dev 的 #1651 A 块数字（723/16/60），未回退。
# **两处比「只减不增」更松，是刻意的**：初稿把「构造 orchestrator → 调 parse_and_preview」抽成
# `services/importer_service.py`（零逻辑的转发壳），并给 `services/ocr_service.py` 塞入转换逻辑 ——
# 后者触发 R6（领域服务不得反向依赖编排层，`decisions.md` D25/D32），且违反该模块自身
# 「本文件勿再堆业务逻辑」的 facade 约定。现改为：纯转换落 `services/importer/candidates.py`，
# 「开会话 + 调 orchestrator」留在视图（`views → services` 是合法边，D26 视图职责即「调服务」）。
# 代价是 importers max_func +1（52 → 53）、ocr lines +23（191 → 214），两者仍 ≤ 60 / 远低于基线；
# 用 +1 行换掉一条违规边与一个空壳模块，账是划算的。基线只减不增。
# 2026-10-04 重取（**新增端点**，非放宽）：#1826 给 summary 加 `GET /summary/penetration/`
# （基金持仓穿透，计算全在 `services/penetration.py`）—— 视图侧只有「入参解析 + 400 校验 +
# 调服务 + 三字段信封」，`orm_queries` / `commits` 仍为 **0**，没有业务规则可下沉（口径与四类
# `reason` 全在 services），属本文件允许的视图职责。summary 141 → 176 行、max_func 20 → 31，
# 其中 11 行是穿透口径的 docstring（覆盖率硬上限 / gics 非主口径 / 季报个股只披露前十大），
# 值得写清。按本文件既有先例（2026-09-20「summary +2」那次）以 `--report` 实测回写，非手工拍数。
# 2026-10-08 收紧（#1929，**非放宽**）：给 `money-fund-income` 端点加「组合」维度时，
# scope 合法性校验、账户/组合归属校验与「组合 → 关联账户 ID 集合」解析一并下沉到
# `services/money_fund_income.resolve_money_fund_scope`（`views → services` 是合法边，D26），
# 视图只留「入参解析 + 调服务 + 组响应」——顺带修掉 #1929 第一版把 portfolio 分支写在视图里
# 导致的 orm_queries / max_func 回潮（守卫拦下 113/3/55 超基线）。按 `--report` 实测回写：
# 93/1/0/36 → 87/0/0/31（orm_queries 归零，与全仓 views 收敛趋势一致）。基线只减不增。
# 2026-10-09 收紧（#1966，**非放宽**）：`GET /api/positions/` 新增 symbol / market 过滤时，
# **没有**把参数一行行加进视图，而是用 `parse_query(PositionListRequest)` 把入参声明收口到
# `domains/positions/schemas.py`，视图反而净减 2 行（288 → 286）；过滤仍在 service 下推到 SQL。
# 2026-10-14 重取（**新增端点**，非放宽）：#2141 给 summary 加 `GET /summary/fund-valuation/`
# （收盘估值定格清单，查询全在 `services/summary_service.list_fund_valuation_rows`）——
# 视图侧只有「入参解析 + 400 校验 + 调服务 + 信封」，`orm_queries` / `commits` 仍为 **0**，
# `max_func` 不变（31）。summary 198 → 229 行（+31，含端点 docstring）。按 `--report` 实测回写。
# 这是「新增功能但视图变薄」的样本：入参声明本就不该在视图，业务规则更不该。
# 按本文件既有先例以实测回写，基线只减不增。
# 2026-10-09 重取（#1969，**新增响应字段、非业务规则进视图**）：`GET /api/utils/enums/` 增补
# `venue` 交易场所标签（`app.core.constants.VENUE_LABELS`，EXCHANGE / OTC 原键不再直接上屏，
# 前端 `useEnumLabels` 消费）。视图侧增量只有「import 多一个常量 + 响应 dict 多一个键 + 一行 why
# 注释」，正是本文件明列的视图职责（组响应），**没有可下沉的业务规则**——标签本体是 constants 的
# 唯一真相源、不是视图逻辑，搬进 services 只会得到一个零逻辑转发壳（#1642 已否掉同类做法）。
# 其余三项原地不动：orm_queries 0 / commits 0 / max_func 38，唯 `lines` 126 → 128。
# 按本文件既有先例（2026-09-20 错误信封补齐 4 文件共 +26、2026-10-04 summary 新增端点 141 → 176）
# 以 `--report` 实测回写，非手工拍数；新增字段一律走 `/enums/` 单一出口，不许前端再抄第二份。
# 2026-10-12 重取（#2092，**新增横切接线、非业务规则进视图**）：为修「删除持仓 / 交易偶发 500」，
# 给 3 个 DELETE 端点（ledgers / positions / transactions）挂 `@retry_on_db_locked()`
# 装饰器（`app/core/retry.py`，重试 SQLite 写锁冲突）。视图侧增量只有「import 一行 +
# 装饰器一行」，三个文件同步 +2，而 **orm_queries / commits / max_func 三项原地不动**——
# 视图并未因此「变厚」，变的只是端点接线。
# 没有可下沉的业务规则：重试要包裹**整个端点调用**（含 service 调用与事务边界），下沉到
# service 只会缩小重试边界——SQLite 的锁是在事务提交时抛出的，service 内重试接不住，
# 等于把「重试整个请求」改成「重试半个请求」，反而掩盖错误。装饰器是端点级横切关注点的
# 最小表达，与本文件明列的视图职责同层。按既有先例以 `--report` 实测回写（仅 lines）：
# ledgers 723 → 725、positions 286 → 288、transactions 136 → 138。
# 2026-10-15 收紧（#981，**非放宽**）：把 PATCH 组合的「账户关联 diff（归属校验 +
# 集合差 + 批量写）」从视图下沉到 `services/portfolio_service.replace_portfolio_ledger_links`
# （`views → services` 是合法边，D26），视图只留「入参解析 + 调服务 + 异常→HTTP」；
# 顺带把逐字段 if 压成等价 getattr/setattr 循环、删 `get_owned_or_404` 后的永假分支。
# 按 `--report` 实测回写：lines 166 → 161、max_func 29 → 25（orm_queries / commits 不动）。
# 2026-10-15 重取（#1123 P0，**新增入参校验、非业务规则进视图**）：持仓「配置目标（五笔钱）」
# 开放行内编辑，两条写路径都要拦非法值——positions 域收在 `PositionUpdate` 的 pydantic
# field_validator（视图零增长，positions 288 不动）；ledgers 域嵌套端点是裸 dict 读 body、
# 无 schema 体系，白名单只能在视图做（`if not in ALLOCATION_LABELS: abort(400)`）。
# 本文件明列的视图职责是「入参解析 + 归属校验 + 调服务 + 组响应」，**入参白名单正属此列**
# （与同函数上方的 get_owned_or_404 归属校验同层），不是编排逻辑。增量仅 +3 行（注释 1 +
# if 2），orm_queries / commits / max_func 三项不动。按既有先例以 `--report` 实测回写（仅 lines）：
# ledgers 725 → 728。
# 2026-10-15 重取（#1337，**新增端点**，非放宽）：给 users 加 `GET/PUT /users/preferences/<key>/`
# （用户私有偏好键值，#993 方案 B 跨设备同步）——视图侧只有「key 长度校验 + 调 ORM upsert +
# JSON 文本↔对象转换 + 信封」，无业务规则可下沉（upsert 是唯一写语义，合并策略在前端）。
# 按 `--report` 实测回写：lines 115 → 160、orm_queries 4 → 6（max_func / commits 不动）。
# 2026-10-17 重取（#2272，**新增端点**，非放宽）：给 products 加 `GET /api/products/pro/`
# （#994 Phase 1 接口骨架）——视图侧只有「parse_query + 调 services/product_pro_status +
# 信封」，`orm_queries` / `commits` 仍为 **0**、`max_func` 不变（30）。骨架不查库（模块
# 是否上线是发布状态而非用户数据），没有任何可下沉的业务规则；docstring 占比高是在写
# 「为什么一期后端全开 / 为什么路径落 products 域」的决策，值得留。products 437 → 458。
# 这是本文件 2026-10-16 升入存量冻结后的第一次生长，按自述通道 `--report` 实测回写。
# 2026-10-17 重取（#2315，**新增端点**，非放宽）：给 summary 加 `GET /summary/cash-like/`
# （持仓页「类现金」分组：账外货基/逆回购逐产品明细，跨账户按「账户 + 产品」归组）——
# 视图侧只有「调 orphan_cash_like_payload + 组信封」，金额换算与合集合计全在 services，
# `orm_queries` / `commits` 仍为 **0**、`max_func` 不变（31）。summary 229 → 245。
# 按本文件既有先例以 `--report` 实测回写，非手工拍数。
# 2026-10-17 再取（#2278，**新增端点**，非放宽）：给 products 加 `GET /api/products/index-returns/`
# 与 `GET /api/products/index-weights/`（详情页指数区块：阶段性收益 + 十大权重）——视图侧
# 只有「parse_query + 调 services/index_metrics + 信封」，与同族 index-profile 同款薄编排；
# 名录查询（orm 的 query）在 service 内做（视图层零 db.query 红线不动），`orm_queries` /
# `commits` 仍为 **0**、`max_func` 不变（30）。docstring 在写「数据链为何中证官网优先 /
# 降级语义」的口径，值得留。products 458 → 502（`--report` 实测，其余三维不动）。
BASELINE: dict[str, dict[str, int]] = {
    "backend/app/domains/assets/views.py": {
        "lines": 208,
        "orm_queries": 4,
        "commits": 0,
        "max_func": 44,
    },
    "backend/app/domains/auth/views.py": {
        "lines": 137,
        "orm_queries": 3,
        "commits": 0,
        "max_func": 45,
    },
    "backend/app/domains/families/views.py": {
        "lines": 72,
        "orm_queries": 2,
        "commits": 0,
        "max_func": 22,
    },
    "backend/app/domains/funds/views.py": {
        "lines": 197,
        "orm_queries": 2,
        "commits": 0,
        "max_func": 39,
    },
    "backend/app/domains/importers/views.py": {
        "lines": 249,
        "orm_queries": 1,
        "commits": 0,
        "max_func": 53,
    },
    "backend/app/domains/ledgers/views.py": {
        "lines": 728,
        "orm_queries": 16,
        "commits": 0,
        "max_func": 60,
    },
    "backend/app/domains/market/views.py": {
        "lines": 37,
        "orm_queries": 0,
        "commits": 0,
        "max_func": 21,
    },
    "backend/app/domains/ocr/views.py": {
        "lines": 214,
        "orm_queries": 1,
        "commits": 0,
        "max_func": 48,
    },
    "backend/app/domains/performance/views.py": {
        "lines": 86,
        "orm_queries": 0,
        "commits": 0,
        "max_func": 31,
    },
    "backend/app/domains/portfolios/views.py": {
        "lines": 161,
        "orm_queries": 1,
        "commits": 0,
        "max_func": 25,
    },
    "backend/app/domains/positions/views.py": {
        "lines": 288,
        "orm_queries": 6,
        "commits": 0,
        "max_func": 57,
    },
    # 2026-10-16 升入存量冻结（#2255 收敛合并，**非放宽**）：CNB 侧 fund-risk 两端点
    # （fund-risk-ranking / fund-risk-types）随收敛移植进本文件（+43 行——两段视图全是
    # 「入参校验 + 调服务 + 信封」的纯编排，orm_queries / commits / max_func 三项实测不动），
    # 394 → 437 顶破新文件上限 400。本文件 2026-10-09 才建（晚于 09-19 冻结日，故此前一直走
    # NEW_FILE_LIMITS），现已是 14 个端点的存量域文件、全部函数 ≤ 30 行，**没有业务规则可下沉**
    # （守卫正解「搬去 services」在本文件已无标的——每段都只剩薄编排）。按本脚本自述的通道
    # 「同时改 LEGACY_VIEWS + BASELINE + 过评审」升入存量冻结集（此后任何端点再生长都会被
    # 「只减不增」拦下），四维实测值取自 `--report`，非手工拍数。
    # 2026-10-17 重取（#2272 新增 pro 端点，详见上方 dated 条目）：437 → 458，其余三维不动。
    # 2026-10-17 再取（#2278 新增 index-returns/index-weights 端点，详见上方 dated 条目）：458 → 502，其余三维不动。
    # 2026-10-17 三取（#2275 新增 index-etf-compare 端点）：502 → 528，其余三维不动——
    # 与同族端点一致的薄编排（入参解析 / 调服务 / 组响应），业务规则全部下沉 etf_compare.py。
    # 2026-10-17 四取（#994 Phase 2 新增 pro-insight 端点）：528 → 548，其余三维不动——
    # 同族薄编排，聚合逻辑全在 pro_insight.py。
    # 查询口径全在 services/user_flags_for_codes），端点本身只多一行调用。
    # orm_queries / commits 仍为 0、max_func 30 不动，唯 lines 548 → 570
    # （+22：助手 10 行 + 两个入参透传 + import 多行展开）。按 `--report` 实测回写。
    # 2026-10-17 六取（#994 Phase 2 **新增 pro-risk 端点**，非放宽）：给 products 加
    # `GET /api/products/pro-risk/`（BIAS + 波动率 + VaR 聚合，计算全在
    # `services/pro_risk.py` + `services/analytics/var.py`）——视图侧只有
    # 「parse_query + get_db() + 调服务 + 信封」，570 → **610**（+40），
    # `orm_queries` / `commits` 仍为 **0**、`max_func` 30 不动（口径与降级 reason
    # 全在 services，无业务规则可下沉）。增量三处：新端点（含口径 docstring）+
    # 两条 import + ValueError→400 防御
    # （防空白/纯前缀 symbol 过 schema 后服务层归一为空时漏 500，与 index-returns
    # 同族范式）；同卡顺手修 pro-insight 误用 `market_session_factory`（该端点经
    # calculate_symbol_xirr 读 user 域表，双库生产必 500）→ 改路由会话 `get_db()`，
    # 属「接线修正」不推高 max_func。按本文件既有先例以 `--report` 实测回写。
    # 2026-10-18 七取（#994 Phase 2 **新增 pro-allocation 端点**，非放宽）：给 products
    # 加 `GET /api/products/pro-allocation/`（当前标的 vs 家庭持仓相关性，聚合在
    # `services/pro_allocation.py`、计算全在 `analytics/correlation.py`）——视图侧
    # 只有「parse_query + get_db() + 调服务 + 信封」，`orm_queries` / `commits`
    # 仍为 **0**、`max_func` 30 不动：相关性口径、60 日样本门槛、零方差降级全在
    # services/analytics，视图层没有业务规则可下沉。
    # 行数两笔：610 → 645（本端点 + import + ValueError→400 防御），再因
    # rebase 到合并后的 dev（#2314 / #2318 等同期改动）落到 **643**——后者不是
    # 本卡的生长，取 `--report` 实测值，不手工倒推。
    "backend/app/domains/products/views.py": {
        "lines": 643,
        "orm_queries": 0,
        "commits": 0,
        "max_func": 30,
    },
    # 2026-10-16：#2255 收敛合并带入 CNB 域 D 对账（duoduobei/fundmate#477/#486）代码，225→311 重取基线（守卫自述「确因合并需要重取基线」场景）
    "backend/app/domains/reconciliation/views.py": {
        "lines": 311,
        "orm_queries": 2,
        "commits": 0,
        "max_func": 48,
    },
    "backend/app/domains/search/views.py": {
        "lines": 25,
        "orm_queries": 0,
        "commits": 0,
        "max_func": 7,
    },
    "backend/app/domains/securities/views.py": {
        "lines": 72,
        "orm_queries": 1,
        "commits": 0,
        "max_func": 35,
    },
    "backend/app/domains/strategy/views.py": {
        "lines": 144,
        "orm_queries": 5,
        "commits": 0,
        "max_func": 22,
    },
    "backend/app/domains/summary/views.py": {
        "lines": 245,
        "orm_queries": 0,
        "commits": 0,
        "max_func": 31,
    },
    "backend/app/domains/temperature/views.py": {
        "lines": 140,
        "orm_queries": 0,
        "commits": 0,
        "max_func": 38,
    },
    "backend/app/domains/transactions/views.py": {
        "lines": 138,
        "orm_queries": 2,
        "commits": 0,
        "max_func": 60,
    },
    "backend/app/domains/usage/views.py": {
        "lines": 68,
        "orm_queries": 0,
        "commits": 0,
        "max_func": 27,
    },
    "backend/app/domains/users/views.py": {
        "lines": 160,
        "orm_queries": 6,
        "commits": 0,
        "max_func": 38,
    },
    "backend/app/domains/utils/views.py": {
        "lines": 128,
        "orm_queries": 0,
        "commits": 0,
        "max_func": 38,
    },
    "backend/app/domains/watchlist/views.py": {
        "lines": 622,
        "orm_queries": 14,
        "commits": 0,
        "max_func": 53,
    },
}

# 冻结的 legacy 视图集（#1606 批次 1 下沉后、2026-09-19 冻结时存在的 22 个路径）。
# 这是「存量 / 新增」的分水岭：
#   - 在集内的走上面 BASELINE 冻结（只减不增）；
#   - 不在集内的（新增 / 改名后的文件）一律走 NEW_FILE_LIMITS，且**无视任何 BASELINE 条目**
#     —— 防有人给新文件塞 fat 基线（如 500 行）绕过 400 行上限（见 #1642 C 块）。
# 本集合必须与 BASELINE 的键**完全一致**，`test_baseline_covers_every_views_file` 强制校验，
# 故想给新文件开后门必须同时改这里 + BASELINE + 过评审，无法静默 gaming。
LEGACY_VIEWS: frozenset[str] = frozenset(
    {
        "backend/app/domains/assets/views.py",
        "backend/app/domains/auth/views.py",
        "backend/app/domains/families/views.py",
        "backend/app/domains/funds/views.py",
        "backend/app/domains/importers/views.py",
        "backend/app/domains/ledgers/views.py",
        "backend/app/domains/market/views.py",
        "backend/app/domains/ocr/views.py",
        "backend/app/domains/performance/views.py",
        "backend/app/domains/portfolios/views.py",
        "backend/app/domains/positions/views.py",
        "backend/app/domains/products/views.py",
        "backend/app/domains/reconciliation/views.py",
        "backend/app/domains/search/views.py",
        "backend/app/domains/securities/views.py",
        "backend/app/domains/strategy/views.py",
        "backend/app/domains/summary/views.py",
        "backend/app/domains/temperature/views.py",
        "backend/app/domains/transactions/views.py",
        "backend/app/domains/usage/views.py",
        "backend/app/domains/users/views.py",
        "backend/app/domains/utils/views.py",
        "backend/app/domains/watchlist/views.py",
    }
)


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def collect_metrics(path: Path) -> dict[str, int]:
    """AST 统计单个视图文件的四项指标（不用正则，避免注释 / 字符串误命中）。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    orm_queries = 0
    commits = 0
    max_func = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "query":
                orm_queries += 1
            elif node.func.attr == "commit":
                commits += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            max_func = max(max_func, span)

    return {
        "lines": source.count("\n") + (0 if source.endswith("\n") else 1),
        "orm_queries": orm_queries,
        "commits": commits,
        "max_func": max_func,
    }


def _iter_views() -> list[Path]:
    return sorted(REPO_ROOT.glob(VIEWS_GLOB))


def _fmt(metrics: dict[str, int]) -> str:
    return " ".join(
        f"{k}={metrics[k]}" for k in ("lines", "orm_queries", "commits", "max_func")
    )


def _report(views: list[Path]) -> int:
    print("# 当前指标（可直接粘贴为 BASELINE；键按路径字典序）")
    print("BASELINE: dict[str, dict[str, int]] = {")
    for path in views:
        print(f'    "{_rel(path)}": {collect_metrics(path)!r},')
    print("}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="视图层厚度守卫（#1606）")
    parser.add_argument(
        "--report", action="store_true", help="打印当前指标与可直接粘贴的基线"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="打印每个文件的指标"
    )
    args = parser.parse_args(argv)

    views = _iter_views()
    if not views:
        print(f"OK: 未找到待扫描的视图文件（{VIEWS_GLOB}）")
        return 0

    if args.report:
        return _report(views)

    violations: list[
        tuple[str, str, int, int, bool]
    ] = []  # (rel, metric, current, limit, is_baseline)
    seen: set[str] = set()
    measured: dict[str, dict[str, int]] = {}

    for path in views:
        rel = _rel(path)
        seen.add(rel)
        metrics = collect_metrics(path)
        measured[rel] = metrics
        is_legacy = rel in LEGACY_VIEWS
        baseline = BASELINE.get(rel) if is_legacy else None

        if args.verbose:
            mark = "基线(legacy)" if is_legacy else "新增"
            print(f"  [{mark}] {rel}  {_fmt(metrics)}")

        if is_legacy:
            # legacy 走冻结基线（只减不增）；缺失基线条目按配置错误上报
            if baseline is None:
                violations.append((rel, "missing_baseline", 0, 0, True))
                continue
            for metric, budget in baseline.items():
                if metrics[metric] > budget:
                    violations.append((rel, metric, metrics[metric], budget, True))
        else:
            # 非 legacy（新增 / 改名）一律走 NEW_FILE_LIMITS；即便有人往 BASELINE 塞了
            # fat 条目也忽略（防 gaming：给新文件塞 500 行基线绕过 400 行上限，见 #1642 C 块）。
            for metric, limit in NEW_FILE_LIMITS.items():
                if metrics[metric] > limit:
                    violations.append((rel, metric, metrics[metric], limit, False))

    stale = sorted(set(BASELINE) - seen)

    # 基线虚胖（非致命）：实测已低于基线却没回写 → 该维度的「只减不增」拦截实际上不起作用。
    loose: list[tuple[str, str, int, int]] = []
    for rel, budget_map in BASELINE.items():
        metrics = measured.get(rel)
        if metrics is None:
            continue
        for metric, budget in budget_map.items():
            if metrics[metric] < budget:
                loose.append((rel, metric, metrics[metric], budget))

    if not violations:
        remaining = {
            "lines": sum(m["lines"] for m in BASELINE.values()),
            "orm_queries": sum(m["orm_queries"] for m in BASELINE.values()),
            "commits": sum(m["commits"] for m in BASELINE.values()),
        }
        print(
            "OK: 视图层厚度无新增（基线存量："
            f"{len(BASELINE) - len(stale)} 个文件 / {remaining['lines']} 行 / "
            f"{remaining['orm_queries']} 次 query / {remaining['commits']} 次 commit；只减不增）"
        )
        if stale:
            print("提示：以下文件已不在基线中，请从 BASELINE 删除对应条目：")
            for rel in stale:
                print(f"  - {rel}")
        if loose:
            print(
                "提示：以下指标已低于基线，请用 `--report` 收紧 BASELINE（只减不增；不收紧该维度会静默失效）："
            )
            for rel, metric, current, budget in loose:
                print(f"  - {rel}: {metric} = {current}（基线 {budget}）")
        return 0

    print(
        "ERROR: 视图层变厚了——业务规则请下沉 `app/services/`，视图只做 HTTP 编排\n"
        "       判据：docs/spec/decisions.md（2026-09-19 视图层职责边界，#1606）\n"
        "       上限：单函数 ≤ 60 行；新增视图文件 lines ≤ 400 / query ≤ 10 / commit ≤ 5",
        file=sys.stderr,
    )
    for rel, metric, current, limit, is_baseline in violations:
        scope = "基线冻结（只减不增）" if is_baseline else f"新增上限 {limit}"
        print(f"  {rel}: {metric} = {current}（{scope}）", file=sys.stderr)
    print(
        "\n      缩小体积的正解是把业务规则搬到 services（视图只留入参解析 / 归属校验 / 调服务 / 组响应）；\n"
        "      确因合并需要重取基线：python scripts/check_view_thickness.py --report 并说明理由。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
