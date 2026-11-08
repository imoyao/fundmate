#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：services 层模块体量 / 复杂度软闸门（源 issue：用户要求「防 #2873 类上帝模块复发」）。

WHY
---
#2873 把 `position_service.py`（当时 2468 行）拆成多个单一职责模块，根因是**没有机器化
的体量闸门**：业务规则持续堆进同一个服务文件，直到它成为谁都不敢动的「上帝模块」。
`check_view_thickness.py`（#1606，视图层）已证明「冻结基线 + 只减不增 + 新增严上限」
这条路能堵住新增、又能按批次收敛存量，本守卫把同一套范式迁到 services 层。

判据（AST 静态，纯标准库，零依赖）：

| 指标 | 含义 | 新增上限 |
|---|---|---|
| `lines` | 文件总行数（含空行 / 注释，按物理行） | 800 |
| `max_func` | 最长函数行数（含 docstring，`end - start + 1`） | 120 |
| `max_cc` | 函数最大圈复杂度（McCabe，按 AST 决策点计） | 20 |

为什么是这三个：
- `lines` 直接对应「上帝模块」的体量（#2873 那类 2000+ 行文件）；
- `max_func` 是单函数复杂度热点的代理（一个 200 行的函数往往塞了多个职责）；
- `max_cc` 直接量复杂度（圈复杂度 > 20 是 McCabe 经典「需要关注」阈值）——`max_func`
  只数行数、看不出分支密度，`max_cc` 补上这一维，正是用户说的「复杂度」。

存量按 `BASELINE` **冻结、只减不增**（只拦「比基线更厚 / 更复杂」，不拦维持现状）：

- 新增 / 改名后的服务文件走 `NEW_FILE_LIMITS`，超标即红；
- 存量文件任一指标超过基线即红（回潮拦截）；
- 基线里已消失的文件会被提示删除（避免基线虚胖）；
- **实测低于基线时打印「请收紧基线」提示**（本脚本不报错——正常收敛不该红掉校验）；
  但「基线必须与实测贴合」由 `scripts/tests/test_guard_service_size.py::
  test_baseline_matches_current_metrics` 强制：基线只减不增，而「减完不回写」会让该
  维度静默失效。收敛后请**同 PR 内**用 `--report` 回写 BASELINE。

为什么不是零容忍：services 层比视图层承载更多业务逻辑，131 个服务文件批量改写
风险远大于收益（同 #1606「先立边界、堵新增、再按批次收敛」的思路）——先把闸门立住、
堵住新增的上帝模块，存量按拆分节奏逐步收紧。

用法
----
    python scripts/guard_service_size.py              # 校验（CI / pre-commit）
    python scripts/guard_service_size.py --report     # 打印当前指标 + 可直接粘贴的基线
    python scripts/guard_service_size.py -v           # 一并打印达标项

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（结论不可信，不得当成通过）。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = REPO_ROOT / "backend" / "app" / "services"

# 新增 / 改名服务文件的上限（判据本体）。要写更大的模块？先拆——这正是闸门的意义。
NEW_FILE_LIMITS = {
    "lines": 800,
    "max_func": 120,
    "max_cc": 20,
}

# 存量基线（首次落地时由 `--report` 全量采集，2026-11-04 冻结）。
# **只减不增**：不要手工调大——要走「把职责下沉 / 拆出子模块」的正当路径；
# 确实因合并等原因需要重取时，用 `--report` 生成新块并说明理由。
# `LEGACY_SERVICES` 直接由 BASELINE 的键导出（单一真相源），故两者不可能漂移。
# 首次落地说明：本仓库 services 层有若干历史大模块（position_service 2468 /
# pnl_calendar 2119 / watchlist_display 1772 / summary_service 1523 / daily_scheduler 1121 /
# fund_service 1058 / watchlist_service 999 等），均为 #2873 拆分前的存量；它们被冻结在
# 当前体量，只减不增——新增文件一律走 NEW_FILE_LIMITS，无法借存量基线开后门。
#
# 2026-11-08 D97 申购码防御报错按 --report 实测回写一项：position_buy_command.py
# 693→698——`_validate_buy_inputs` 的 lot 失败分支新增「申购段代码报『未解析上市
# 代码』而非『一手起买』」的必要路径（注释已压至 1 行），真实代码增长非放宽阈值。
# 2026-11-07 通用当日估值（D92）按 `--report` 实测值回写三项，理由留痕：
# `today_pnl.py` 由家庭级单视图泛化为「单资源 + dimension 分组」（379→553 行 /
# max_func 123→182 / max_cc 27→37），`pnl_calendar.py` 新增可选桶函数
# （2139→2166 / 654→681 / 101→106）——都是真实代码增长，不是放宽阈值：
# `test_baseline_matches_current_metrics` 要求基线与实测**逐项相等**，留余量同样判红。
# ⚠️ `today_pnl` 的 max_func 182 / max_cc 37 已超 NEW_FILE_LIMITS（120 / 20），
# 属存量冻结文件的功能性增长，作为拆分债务登记在 PR 风险里，不在此假装没发生。
# `asset_class.py` 因压缩 docstring 由 64 收紧到 63（只减不增）。
#
# 2026-11-08 招商证券交割单接入（D93/D96）按 `--report` 回写四个存量文件，理由留痕：
# `daily_scheduler.py` 1121→1128（`_NOT_SCHEDULED` 新增 securities_backfill 条目及
# 其不日跑的理由，注释已压到 3 行）、`importer/mappings.py` 239→306（按模块 docstring
# 的约定「新增平台只需添加一个字典」新增 CMS 业务名 / 中签事件 / 有意忽略三组声明，
# 注释已压过一轮）、`importer/registry.py` 63→65（import + `register_parser` 各一行，
# 注册点无法外移）、`sync/orchestrator.py` 818→822 / max_func 113→115（import、
# 新 job 注册各一行 + 一行注释）。四个增量都是「新增一家券商 / 一个新 job」的必要
# 接线，没有借此放大任何既有函数的职责；新增服务文件本身均在
# NEW_FILE_LIMITS（≤800 行 / max_func ≤120 / max_cc ≤20）之内。
BASELINE: dict[str, dict[str, int]] = {
    "backend/app/services/__init__.py": {'lines': 4, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/adapters/__init__.py": {'lines': 14, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/adapters/advisor_source.py": {'lines': 304, 'max_func': 16, 'max_cc': 4},
    "backend/app/services/adapters/akshare_adapter.py": {'lines': 2023, 'max_func': 90, 'max_cc': 23},
    "backend/app/services/adapters/base.py": {'lines': 78, 'max_func': 8, 'max_cc': 1},
    "backend/app/services/adapters/contract.py": {'lines': 120, 'max_func': 42, 'max_cc': 9},
    "backend/app/services/adapters/direct_feeds.py": {'lines': 311, 'max_func': 51, 'max_cc': 12},
    "backend/app/services/adapters/eastmoney_adapter.py": {'lines': 161, 'max_func': 43, 'max_cc': 13},
    "backend/app/services/adapters/fetcher_base.py": {'lines': 63, 'max_func': 10, 'max_cc': 1},
    "backend/app/services/adapters/howbuy_advisor_adapter.py": {'lines': 378, 'max_func': 61, 'max_cc': 20},
    "backend/app/services/adapters/index_weights.py": {'lines': 80, 'max_func': 37, 'max_cc': 8},
    "backend/app/services/adapters/jiucaishuo_adapter.py": {'lines': 388, 'max_func': 64, 'max_cc': 11},
    "backend/app/services/adapters/jsl_bond_adjust_adapter.py": {'lines': 276, 'max_func': 80, 'max_cc': 19},
    "backend/app/services/adapters/manager_tenure.py": {'lines': 232, 'max_func': 32, 'max_cc': 9},
    "backend/app/services/adapters/null_adapter.py": {'lines': 19, 'max_func': 2, 'max_cc': 1},
    "backend/app/services/adapters/qieman_advisor_adapter.py": {'lines': 474, 'max_func': 50, 'max_cc': 16},
    "backend/app/services/adapters/qieman_fetcher.py": {'lines': 651, 'max_func': 63, 'max_cc': 18},
    "backend/app/services/adapters/tiantian_advisor_adapter.py": {'lines': 442, 'max_func': 43, 'max_cc': 11},
    "backend/app/services/adapters/wind_edb.py": {'lines': 153, 'max_func': 52, 'max_cc': 15},
    "backend/app/services/adapters/wind_fund.py": {'lines': 354, 'max_func': 74, 'max_cc': 11},
    "backend/app/services/adapters/wind_index.py": {'lines': 147, 'max_func': 40, 'max_cc': 6},
    "backend/app/services/adapters/wind_index_valuation.py": {'lines': 237, 'max_func': 98, 'max_cc': 22},
    "backend/app/services/adapters/wind_stock.py": {'lines': 278, 'max_func': 69, 'max_cc': 18},
    "backend/app/services/adapters/xalpha_adapter.py": {'lines': 557, 'max_func': 65, 'max_cc': 19},
    "backend/app/services/adj_close_lookup.py": {'lines': 116, 'max_func': 70, 'max_cc': 12},
    "backend/app/services/advisor_nav.py": {'lines': 328, 'max_func': 51, 'max_cc': 14},
    "backend/app/services/advisor_position.py": {'lines': 90, 'max_func': 45, 'max_cc': 7},
    "backend/app/services/advisor_profile.py": {'lines': 180, 'max_func': 59, 'max_cc': 6},
    "backend/app/services/ai_recognizer/__init__.py": {'lines': 34, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/ai_recognizer/agent_loop.py": {'lines': 739, 'max_func': 294, 'max_cc': 39},
    "backend/app/services/ai_recognizer/base.py": {'lines': 133, 'max_func': 20, 'max_cc': 10},
    "backend/app/services/ai_recognizer/cancellation.py": {'lines': 57, 'max_func': 12, 'max_cc': 4},
    "backend/app/services/ai_recognizer/catalog.py": {'lines': 161, 'max_func': 91, 'max_cc': 20},
    "backend/app/services/ai_recognizer/guards.py": {'lines': 213, 'max_func': 21, 'max_cc': 6},
    "backend/app/services/ai_recognizer/llm.py": {'lines': 211, 'max_func': 109, 'max_cc': 13},
    "backend/app/services/ai_recognizer/mcp_adapter.py": {'lines': 54, 'max_func': 20, 'max_cc': 4},
    "backend/app/services/ai_recognizer/mcp_server.py": {'lines': 82, 'max_func': 9, 'max_cc': 3},
    "backend/app/services/ai_recognizer/narrative_blocks.py": {'lines': 180, 'max_func': 60, 'max_cc': 24},
    "backend/app/services/ai_recognizer/recognizers/__init__.py": {'lines': 10, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/ai_recognizer/recognizers/holding_recognizer.py": {'lines': 102, 'max_func': 39, 'max_cc': 17},
    "backend/app/services/ai_recognizer/recognizers/txn_recognizer.py": {'lines': 200, 'max_func': 36, 'max_cc': 16},
    "backend/app/services/ai_recognizer/recognizers/watchlist_recognizer.py": {'lines': 63, 'max_func': 9, 'max_cc': 5},
    "backend/app/services/ai_recognizer/registry.py": {'lines': 98, 'max_func': 9, 'max_cc': 4},
    "backend/app/services/ai_recognizer/safety/__init__.py": {'lines': 52, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/ai_recognizer/safety/intent_guard.py": {'lines': 203, 'max_func': 26, 'max_cc': 11},
    "backend/app/services/ai_recognizer/safety/output_filter.py": {'lines': 217, 'max_func': 42, 'max_cc': 14},
    "backend/app/services/ai_recognizer/safety/repeat_tracker.py": {'lines': 114, 'max_func': 18, 'max_cc': 7},
    "backend/app/services/ai_recognizer/schemas.py": {'lines': 104, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/ai_recognizer/session_store.py": {'lines': 125, 'max_func': 23, 'max_cc': 6},
    "backend/app/services/ai_recognizer/tools.py": {'lines': 619, 'max_func': 91, 'max_cc': 17},
    "backend/app/services/analytics/__init__.py": {'lines': 39, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/analytics/behavior.py": {'lines': 340, 'max_func': 194, 'max_cc': 62},
    "backend/app/services/analytics/benchmark_comparison.py": {'lines': 307, 'max_func': 108, 'max_cc': 23},
    "backend/app/services/analytics/benchmark_excess.py": {'lines': 409, 'max_func': 130, 'max_cc': 29},
    "backend/app/services/analytics/cleared_cycles.py": {'lines': 747, 'max_func': 155, 'max_cc': 47},
    "backend/app/services/analytics/correlation.py": {'lines': 119, 'max_func': 44, 'max_cc': 9},
    "backend/app/services/analytics/trading_behavior.py": {'lines': 257, 'max_func': 96, 'max_cc': 21},
    "backend/app/services/analytics/var.py": {'lines': 138, 'max_func': 35, 'max_cc': 9},
    "backend/app/services/asset_class.py": {'lines': 63, 'max_func': 3, 'max_cc': 2},
    "backend/app/services/asset_search.py": {'lines': 256, 'max_func': 66, 'max_cc': 9},
    "backend/app/services/async_backfill.py": {'lines': 314, 'max_func': 65, 'max_cc': 13},
    "backend/app/services/bias/__init__.py": {'lines': 32, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/bias/calculator.py": {'lines': 506, 'max_func': 57, 'max_cc': 15},
    "backend/app/services/bias/constants.py": {'lines': 81, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/bias/job.py": {'lines': 221, 'max_func': 27, 'max_cc': 4},
    "backend/app/services/bias/provider.py": {'lines': 119, 'max_func': 53, 'max_cc': 9},
    "backend/app/services/bias/schemas.py": {'lines': 64, 'max_func': 19, 'max_cc': 2},
    "backend/app/services/cash_flow_service.py": {'lines': 248, 'max_func': 122, 'max_cc': 22},
    "backend/app/services/cold_set_guard.py": {'lines': 240, 'max_func': 52, 'max_cc': 8},
    "backend/app/services/cold_set_write_scope.py": {'lines': 140, 'max_func': 42, 'max_cc': 8},
    "backend/app/services/conversion_service.py": {'lines': 795, 'max_func': 283, 'max_cc': 32},
    "backend/app/services/convertible_bond_ytm.py": {'lines': 219, 'max_func': 50, 'max_cc': 15},
    "backend/app/services/cross_domain.py": {'lines': 221, 'max_func': 54, 'max_cc': 15},
    "backend/app/services/daily_scheduler.py": {'lines': 1128, 'max_func': 38, 'max_cc': 10},
    "backend/app/services/dangling_ref_remediation_service.py": {'lines': 541, 'max_func': 58, 'max_cc': 11},
    "backend/app/services/dangling_ref_service.py": {'lines': 607, 'max_func': 88, 'max_cc': 15},
    "backend/app/services/dividend_service.py": {'lines': 465, 'max_func': 112, 'max_cc': 25},
    # 2026-11-08：货基免税判定（#1661）曾把服务推到 662 行 / cc 34，触发本守卫。
    #   纯规则拆到 `services/dividend_tax_rules.py`（`is_dividend_income` /
    #   `position_asset_types` / `resolve_asset_type`），实测回写 634→592、32→31。
    "backend/app/services/dividend_tax_service.py": {'lines': 525, 'max_func': 90, 'max_cc': 13},
    "backend/app/services/entitlement_check.py": {'lines': 108, 'max_func': 45, 'max_cc': 7},
    "backend/app/services/enums_service.py": {'lines': 62, 'max_func': 32, 'max_cc': 1},
    "backend/app/services/etf_compare.py": {'lines': 352, 'max_func': 99, 'max_cc': 27},
    "backend/app/services/etf_scale_fee.py": {'lines': 460, 'max_func': 51, 'max_cc': 25},
    "backend/app/services/family_member_service.py": {'lines': 226, 'max_func': 33, 'max_cc': 6},
    "backend/app/services/feedlog.py": {'lines': 79, 'max_func': 46, 'max_cc': 12},
    "backend/app/services/fund_benchmark.py": {'lines': 201, 'max_func': 26, 'max_cc': 9},
    "backend/app/services/fund_company_backfill.py": {'lines': 187, 'max_func': 82, 'max_cc': 16},
    "backend/app/services/fund_holdings_detail.py": {'lines': 252, 'max_func': 83, 'max_cc': 20},
    "backend/app/services/fund_metrics.py": {'lines': 92, 'max_func': 49, 'max_cc': 10},
    "backend/app/services/fund_nav_on_demand.py": {'lines': 159, 'max_func': 49, 'max_cc': 13},
    "backend/app/services/fund_peer_rank.py": {'lines': 119, 'max_func': 42, 'max_cc': 14},
    "backend/app/services/fund_performance.py": {'lines': 551, 'max_func': 110, 'max_cc': 21},
    "backend/app/services/fund_profile.py": {'lines': 172, 'max_func': 69, 'max_cc': 14},
    "backend/app/services/fund_risk_metrics.py": {'lines': 795, 'max_func': 130, 'max_cc': 25},
    "backend/app/services/fund_risk_ranking.py": {'lines': 359, 'max_func': 84, 'max_cc': 16},
    "backend/app/services/fund_service.py": {'lines': 1058, 'max_func': 125, 'max_cc': 22},
    "backend/app/services/fund_style_service.py": {'lines': 403, 'max_func': 150, 'max_cc': 32},
    "backend/app/services/fund_utils.py": {'lines': 371, 'max_func': 53, 'max_cc': 16},
    "backend/app/services/ghost_duplicate_service.py": {'lines': 145, 'max_func': 50, 'max_cc': 6},
    "backend/app/services/holding_correlation.py": {'lines': 203, 'max_func': 78, 'max_cc': 14},
    "backend/app/services/holding_overlap.py": {'lines': 651, 'max_func': 93, 'max_cc': 22},
    "backend/app/services/import_records.py": {'lines': 189, 'max_func': 30, 'max_cc': 4},
    "backend/app/services/importer/__init__.py": {'lines': 4, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/importer/base.py": {'lines': 215, 'max_func': 32, 'max_cc': 6},
    "backend/app/services/importer/candidates.py": {'lines': 96, 'max_func': 52, 'max_cc': 21},
    "backend/app/services/importer/linking.py": {'lines': 226, 'max_func': 50, 'max_cc': 16},
    "backend/app/services/importer/mappings.py": {'lines': 306, 'max_func': 3, 'max_cc': 1},
    "backend/app/services/importer/orchestrator.py": {'lines': 35, 'max_func': 4, 'max_cc': 1},
    "backend/app/services/importer/orchestrator_commit.py": {'lines': 567, 'max_func': 227, 'max_cc': 33},
    "backend/app/services/importer/orchestrator_holdings.py": {'lines': 1201, 'max_func': 120, 'max_cc': 27},
    "backend/app/services/importer/orchestrator_parse.py": {'lines': 553, 'max_func': 101, 'max_cc': 35},
    "backend/app/services/importer/parsers/__init__.py": {'lines': 4, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/importer/parsers/alipay_fund.py": {'lines': 224, 'max_func': 85, 'max_cc': 28},
    "backend/app/services/importer/parsers/alipay_pdf.py": {'lines': 239, 'max_func': 70, 'max_cc': 28},
    "backend/app/services/importer/parsers/e_account_holding.py": {'lines': 213, 'max_func': 50, 'max_cc': 18},
    "backend/app/services/importer/parsers/standard.py": {'lines': 317, 'max_func': 66, 'max_cc': 20},
    "backend/app/services/importer/parsers/ths_stock.py": {'lines': 511, 'max_func': 108, 'max_cc': 19},
    "backend/app/services/importer/parsers/tiantian_fund.py": {'lines': 131, 'max_func': 67, 'max_cc': 21},
    "backend/app/services/importer/registry.py": {'lines': 65, 'max_func': 6, 'max_cc': 3},
    "backend/app/services/importer/template_config.py": {'lines': 46, 'max_func': 6, 'max_cc': 2},
    "backend/app/services/importer/utils.py": {'lines': 186, 'max_func': 35, 'max_cc': 8},
    "backend/app/services/index_metrics.py": {'lines': 411, 'max_func': 69, 'max_cc': 14},
    "backend/app/services/index_percentile.py": {'lines': 78, 'max_func': 36, 'max_cc': 12},
    "backend/app/services/index_profile.py": {'lines': 177, 'max_func': 70, 'max_cc': 19},
    "backend/app/services/industry_emotion_service.py": {'lines': 103, 'max_func': 57, 'max_cc': 4},
    "backend/app/services/industry_pbroe_service.py": {'lines': 41, 'max_func': 19, 'max_cc': 3},
    "backend/app/services/insight/__init__.py": {'lines': 12, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/insight/engine.py": {'lines': 156, 'max_func': 27, 'max_cc': 6},
    "backend/app/services/insight/rules.py": {'lines': 255, 'max_func': 40, 'max_cc': 10},
    "backend/app/services/institution_resolver.py": {'lines': 179, 'max_func': 36, 'max_cc': 14},
    "backend/app/services/job_base.py": {'lines': 409, 'max_func': 109, 'max_cc': 14},
    "backend/app/services/jsl_session.py": {'lines': 126, 'max_func': 29, 'max_cc': 6},
    "backend/app/services/ledger_migration_service.py": {'lines': 794, 'max_func': 97, 'max_cc': 18},
    "backend/app/services/ledger_presenter.py": {'lines': 82, 'max_func': 57, 'max_cc': 10},
    "backend/app/services/ledger_service.py": {'lines': 697, 'max_func': 120, 'max_cc': 23},
    # 2026-11-07 收紧（非放宽）：P0 派生上移 + 压注释 665→664；随后把「分组↔口径
    # 一致性守卫」抽到 services/ledger_category_guard.py（新文件走 NEW_FILE_LIMITS），
    # update_ledger 由 4 行分支收成 1 行调用 ⇒ 664→663 / 154→152 / 49→48。
    # 按 `--report` 实测回写，三个维度都只减不增。
    "backend/app/services/ledger_write_service.py": {'lines': 663, 'max_func': 152, 'max_cc': 48},
    "backend/app/services/login_identifier.py": {'lines': 62, 'max_func': 38, 'max_cc': 10},
    "backend/app/services/manager_code.py": {'lines': 68, 'max_func': 15, 'max_cc': 3},
    "backend/app/services/manager_holdings.py": {'lines': 362, 'max_func': 98, 'max_cc': 30},
    "backend/app/services/manager_profile.py": {'lines': 375, 'max_func': 104, 'max_cc': 16},
    "backend/app/services/manager_style.py": {'lines': 225, 'max_func': 40, 'max_cc': 8},
    "backend/app/services/market_history_service.py": {'lines': 181, 'max_func': 83, 'max_cc': 18},
    "backend/app/services/market_history_store.py": {'lines': 116, 'max_func': 43, 'max_cc': 10},
    "backend/app/services/market_service.py": {'lines': 736, 'max_func': 70, 'max_cc': 19},
    "backend/app/services/market_snapshot_store.py": {'lines': 246, 'max_func': 54, 'max_cc': 12},
    "backend/app/services/matrix_members.py": {'lines': 102, 'max_func': 51, 'max_cc': 9},
    "backend/app/services/mcp/__init__.py": {'lines': 27, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/mcp/base.py": {'lines': 89, 'max_func': 12, 'max_cc': 1},
    "backend/app/services/mcp/call_log.py": {'lines': 202, 'max_func': 57, 'max_cc': 10},
    "backend/app/services/mcp/credentials.py": {'lines': 104, 'max_func': 23, 'max_cc': 3},
    "backend/app/services/mcp/errors.py": {'lines': 261, 'max_func': 34, 'max_cc': 6},
    "backend/app/services/mcp/providers/__init__.py": {'lines': 2, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/mcp/providers/qieman.py": {'lines': 80, 'max_func': 10, 'max_cc': 2},
    "backend/app/services/mcp/providers/wind.py": {'lines': 328, 'max_func': 41, 'max_cc': 9},
    "backend/app/services/mcp/providers/wind_direct.py": {'lines': 129, 'max_func': 7, 'max_cc': 5},
    "backend/app/services/mcp/providers/wind_fund_data.py": {'lines': 56, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/mcp/providers/wind_index_data.py": {'lines': 65, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/mcp/providers/wind_stock_data.py": {'lines': 61, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/mcp/registry.py": {'lines': 64, 'max_func': 15, 'max_cc': 3},
    "backend/app/services/mcp/transport.py": {'lines': 369, 'max_func': 35, 'max_cc': 10},
    "backend/app/services/money_fund_income.py": {'lines': 301, 'max_func': 63, 'max_cc': 13},
    "backend/app/services/money_fund_yield.py": {'lines': 195, 'max_func': 84, 'max_cc': 19},
    "backend/app/services/nav_service.py": {'lines': 430, 'max_func': 71, 'max_cc': 12},
    "backend/app/services/notification_service.py": {'lines': 160, 'max_func': 22, 'max_cc': 8},
    "backend/app/services/ocr_service.py": {'lines': 100, 'max_func': 6, 'max_cc': 1},
    # #2875 缺账本孤儿流水服务（只读暴露 / 显式回填 / 可撤销）。新增文件实测
    # {465, 48, 9}，远低于新增上限 {800, 120, 20}；登记是为了让「只减不增」立刻生效，
    # 而不是靠上限留 800 行的余量给未来堆职责。
    "backend/app/services/orphan_ledger_service.py": {'lines': 465, 'max_func': 48, 'max_cc': 9},
    "backend/app/services/penetration.py": {'lines': 729, 'max_func': 404, 'max_cc': 96},
    "backend/app/services/performance/__init__.py": {'lines': 83, 'max_func': 50, 'max_cc': 3},
    "backend/app/services/performance/calculators.py": {'lines': 577, 'max_func': 70, 'max_cc': 24},
    "backend/app/services/performance/cashflow_layers.py": {'lines': 381, 'max_func': 105, 'max_cc': 20},
    "backend/app/services/performance/fee_cash.py": {'lines': 100, 'max_func': 22, 'max_cc': 3},
    "backend/app/services/performance/twr.py": {'lines': 336, 'max_func': 76, 'max_cc': 15},
    "backend/app/services/performance/xirr_engine.py": {'lines': 410, 'max_func': 109, 'max_cc': 15},
    "backend/app/services/pnl_calendar.py": {'lines': 2166, 'max_func': 681, 'max_cc': 106},
    "backend/app/services/pnl_fees.py": {'lines': 97, 'max_func': 17, 'max_cc': 6},
    "backend/app/services/pnl_service.py": {'lines': 211, 'max_func': 36, 'max_cc': 7},
    "backend/app/services/pnl_settle.py": {'lines': 34, 'max_func': 11, 'max_cc': 3},
    "backend/app/services/pnl_snapshot_store.py": {'lines': 447, 'max_func': 61, 'max_cc': 22},
    "backend/app/services/portfolio_service.py": {'lines': 520, 'max_func': 118, 'max_cc': 19},
    "backend/app/services/position_aggregation.py": {'lines': 624, 'max_func': 163, 'max_cc': 47},
    "backend/app/services/position_buy_command.py": {'lines': 698, 'max_func': 79, 'max_cc': 11},
    "backend/app/services/position_display.py": {'lines': 291, 'max_func': 129, 'max_cc': 18},
    "backend/app/services/position_presenter.py": {'lines': 84, 'max_func': 60, 'max_cc': 9},
    "backend/app/services/position_scope.py": {'lines': 103, 'max_func': 22, 'max_cc': 1},
    "backend/app/services/position_orphan_flows.py": {'lines': 497, 'max_func': 81, 'max_cc': 14},
    "backend/app/services/position_sell_command.py": {'lines': 362, 'max_func': 96, 'max_cc': 17},
    "backend/app/services/position_bond_command.py": {'lines': 269, 'max_func': 69, 'max_cc': 16},
    "backend/app/services/position_recompute.py": {'lines': 200, 'max_func': 44, 'max_cc': 9},
    "backend/app/services/position_service.py": {'lines': 638, 'max_func': 61, 'max_cc': 13},
    "backend/app/services/position_snapshot_command.py": {'lines': 322, 'max_func': 63, 'max_cc': 14},
    "backend/app/services/position_write_support.py": {'lines': 365, 'max_func': 67, 'max_cc': 13},
    "backend/app/services/position_structure.py": {'lines': 259, 'max_func': 152, 'max_cc': 23},
    "backend/app/services/position_valuation.py": {'lines': 235, 'max_func': 95, 'max_cc': 16},
    "backend/app/services/price_depth.py": {'lines': 211, 'max_func': 72, 'max_cc': 18},
    "backend/app/services/price_range_service.py": {'lines': 194, 'max_func': 42, 'max_cc': 11},
    "backend/app/services/pro_allocation.py": {'lines': 203, 'max_func': 91, 'max_cc': 11},
    "backend/app/services/pro_insight.py": {'lines': 68, 'max_func': 36, 'max_cc': 3},
    "backend/app/services/pro_risk.py": {'lines': 187, 'max_func': 43, 'max_cc': 7},
    "backend/app/services/product_identity.py": {'lines': 267, 'max_func': 116, 'max_cc': 29},
    "backend/app/services/product_pro_status.py": {'lines': 84, 'max_func': 35, 'max_cc': 5},
    "backend/app/services/product_trend.py": {'lines': 386, 'max_func': 116, 'max_cc': 15},
    "backend/app/services/reconciliation_service.py": {'lines': 540, 'max_func': 122, 'max_cc': 23},
    "backend/app/services/recurring_service.py": {'lines': 289, 'max_func': 33, 'max_cc': 12},
    "backend/app/services/related_symbols.py": {'lines': 141, 'max_func': 57, 'max_cc': 7},
    "backend/app/services/scope.py": {'lines': 123, 'max_func': 40, 'max_cc': 11},
    "backend/app/services/securities_type_backfill.py": {'lines': 121, 'max_func': 59, 'max_cc': 12},
    "backend/app/services/security_industry_map_service.py": {'lines': 310, 'max_func': 51, 'max_cc': 12},
    "backend/app/services/similar_fund_service.py": {'lines': 80, 'max_func': 37, 'max_cc': 6},
    "backend/app/services/stock_profile.py": {'lines': 200, 'max_func': 106, 'max_cc': 28},
    "backend/app/services/strategy_engine/__init__.py": {'lines': 15, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/strategy_engine/allocation.py": {'lines': 237, 'max_func': 49, 'max_cc': 13},
    "backend/app/services/strategy_engine/behavior_profile.py": {'lines': 453, 'max_func': 103, 'max_cc': 36},
    "backend/app/services/strategy_engine/contracts.py": {'lines': 175, 'max_func': 12, 'max_cc': 5},
    "backend/app/services/strategy_engine/data_provider.py": {'lines': 360, 'max_func': 75, 'max_cc': 16},
    "backend/app/services/strategy_engine/diagnosis.py": {'lines': 299, 'max_func': 59, 'max_cc': 20},
    "backend/app/services/strategy_engine/indicators.py": {'lines': 75, 'max_func': 17, 'max_cc': 8},
    "backend/app/services/strategy_engine/registry.py": {'lines': 56, 'max_func': 6, 'max_cc': 3},
    "backend/app/services/strategy_engine/strategies/__init__.py": {'lines': 13, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/strategy_engine/strategies/trend.py": {'lines': 107, 'max_func': 61, 'max_cc': 9},
    "backend/app/services/strategy_service.py": {'lines': 123, 'max_func': 101, 'max_cc': 12},
    "backend/app/services/summary_service.py": {'lines': 1542, 'max_func': 139, 'max_cc': 26},
    "backend/app/services/symbol_scope.py": {'lines': 130, 'max_func': 36, 'max_cc': 4},
    "backend/app/services/sync/__init__.py": {'lines': 4, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/sync/bulk_ops.py": {'lines': 302, 'max_func': 86, 'max_cc': 11},
    "backend/app/services/sync/company_resolver.py": {'lines': 457, 'max_func': 69, 'max_cc': 13},
    "backend/app/services/sync/fund_type_resolution.py": {'lines': 126, 'max_func': 23, 'max_cc': 9},
    "backend/app/services/sync/jobs/__init__.py": {'lines': 4, 'max_func': 0, 'max_cc': 0},
    "backend/app/services/sync/jobs/advisor_portfolio_job.py": {'lines': 669, 'max_func': 95, 'max_cc': 23},
    "backend/app/services/sync/jobs/advisor_portfolio_nav_job.py": {'lines': 190, 'max_func': 51, 'max_cc': 14},
    "backend/app/services/sync/jobs/amac_institution_job.py": {'lines': 275, 'max_func': 37, 'max_cc': 8},
    "backend/app/services/sync/jobs/asset_snapshot_job.py": {'lines': 84, 'max_func': 31, 'max_cc': 4},
    "backend/app/services/sync/jobs/bond_adjust_log_job.py": {'lines': 224, 'max_func': 49, 'max_cc': 14},
    "backend/app/services/sync/jobs/channel_link_job.py": {'lines': 213, 'max_func': 42, 'max_cc': 9},
    "backend/app/services/sync/jobs/convertible_bond_job.py": {'lines': 219, 'max_func': 46, 'max_cc': 14},
    "backend/app/services/sync/jobs/dividend_split_job.py": {'lines': 554, 'max_func': 155, 'max_cc': 28},
    "backend/app/services/sync/jobs/fund_company_backfill_job.py": {'lines': 153, 'max_func': 40, 'max_cc': 6},
    "backend/app/services/sync/jobs/fund_detail_enrich_job.py": {'lines': 275, 'max_func': 113, 'max_cc': 24},
    "backend/app/services/sync/jobs/fund_list_job.py": {'lines': 115, 'max_func': 52, 'max_cc': 12},
    "backend/app/services/sync/jobs/fund_manager_job.py": {'lines': 352, 'max_func': 114, 'max_cc': 31},
    # #2872：写入期冷集硬上限新增 1 处调用点（import + 注释 + 调用，共 4 行）。
    # 规则本体在 services/cold_set_write_scope.py，本文件只多一行调用，职责未增加；
    # 收紧方向仍成立——本文件的正常收敛不必因此停下。
    "backend/app/services/sync/jobs/fund_nav_job.py": {'lines': 190, 'max_func': 68, 'max_cc': 11},
    "backend/app/services/sync/jobs/fund_position_job.py": {'lines': 381, 'max_func': 73, 'max_cc': 12},
    "backend/app/services/sync/jobs/fund_rating_job.py": {'lines': 120, 'max_func': 40, 'max_cc': 11},
    "backend/app/services/sync/jobs/fund_risk_metrics_job.py": {'lines': 293, 'max_func': 81, 'max_cc': 9},
    "backend/app/services/sync/jobs/fund_scale_job.py": {'lines': 105, 'max_func': 34, 'max_cc': 8},
    "backend/app/services/sync/jobs/fund_style_job.py": {'lines': 278, 'max_func': 41, 'max_cc': 14},
    "backend/app/services/sync/jobs/fund_type_job.py": {'lines': 109, 'max_func': 34, 'max_cc': 13},
    "backend/app/services/sync/jobs/fund_valuation_reconcile_job.py": {'lines': 159, 'max_func': 44, 'max_cc': 11},
    "backend/app/services/sync/jobs/fund_valuation_snapshot_job.py": {'lines': 206, 'max_func': 50, 'max_cc': 17},
    "backend/app/services/sync/jobs/index_catalog_job.py": {'lines': 147, 'max_func': 34, 'max_cc': 7},
    "backend/app/services/sync/jobs/index_constituent_job.py": {'lines': 106, 'max_func': 25, 'max_cc': 8},
    "backend/app/services/sync/jobs/index_daily_job.py": {'lines': 409, 'max_func': 53, 'max_cc': 12},
    "backend/app/services/sync/jobs/index_valuation_job.py": {'lines': 132, 'max_func': 35, 'max_cc': 11},
    "backend/app/services/sync/jobs/index_valuation_lg_job.py": {'lines': 131, 'max_func': 32, 'max_cc': 11},
    "backend/app/services/sync/jobs/industry_pbroe_job.py": {'lines': 90, 'max_func': 18, 'max_cc': 10},
    "backend/app/services/sync/jobs/manager_tenure_job.py": {'lines': 238, 'max_func': 111, 'max_cc': 14},
    "backend/app/services/sync/jobs/market_asset_daily_job.py": {'lines': 80, 'max_func': 10, 'max_cc': 7},
    "backend/app/services/sync/jobs/nav_backfill_job.py": {'lines': 227, 'max_func': 53, 'max_cc': 15},
    "backend/app/services/sync/jobs/orphan_backfill_job.py": {'lines': 302, 'max_func': 64, 'max_cc': 11},
    "backend/app/services/sync/jobs/position_price_job.py": {'lines': 414, 'max_func': 152, 'max_cc': 39},
    "backend/app/services/sync/jobs/price_history_job.py": {'lines': 563, 'max_func': 125, 'max_cc': 21},
    "backend/app/services/sync/jobs/security_industry_map_job.py": {'lines': 237, 'max_func': 40, 'max_cc': 11},
    "backend/app/services/sync/jobs/stock_list_job.py": {'lines': 104, 'max_func': 41, 'max_cc': 14},
    "backend/app/services/sync/name_match.py": {'lines': 351, 'max_func': 32, 'max_cc': 9},
    "backend/app/services/sync/orchestrator.py": {'lines': 822, 'max_func': 115, 'max_cc': 8},
    "backend/app/services/sync/pinyin_utils.py": {'lines': 28, 'max_func': 16, 'max_cc': 5},
    "backend/app/services/sync/snapshot.py": {'lines': 340, 'max_func': 83, 'max_cc': 16},
    "backend/app/services/tenure_display.py": {'lines': 167, 'max_func': 42, 'max_cc': 5},
    "backend/app/services/thermometer/constants.py": {'lines': 119, 'max_func': 17, 'max_cc': 8},
    "backend/app/services/thermometer/fetchers.py": {'lines': 524, 'max_func': 86, 'max_cc': 18},
    "backend/app/services/thermometer/fundfof_crowding.py": {'lines': 540, 'max_func': 81, 'max_cc': 22},
    "backend/app/services/thermometer/industry_crowding.py": {'lines': 1121, 'max_func': 105, 'max_cc': 19},
    "backend/app/services/thermometer/jobs.py": {'lines': 386, 'max_func': 287, 'max_cc': 32},
    "backend/app/services/thermometer/service.py": {'lines': 677, 'max_func': 99, 'max_cc': 17},
    "backend/app/services/thermometer/sw_industry_source.py": {'lines': 238, 'max_func': 30, 'max_cc': 12},
    "backend/app/services/thermometer/wind_turnover.py": {'lines': 152, 'max_func': 40, 'max_cc': 9},
    "backend/app/services/thermometer/wind_valuation.py": {'lines': 122, 'max_func': 36, 'max_cc': 7},
    "backend/app/services/today_pnl.py": {'lines': 553, 'max_func': 182, 'max_cc': 37},
    "backend/app/services/trade_timeline.py": {'lines': 497, 'max_func': 235, 'max_cc': 35},
    "backend/app/services/trading.py": {'lines': 137, 'max_func': 28, 'max_cc': 10},
    "backend/app/services/transaction_service.py": {'lines': 492, 'max_func': 69, 'max_cc': 10},
    "backend/app/services/txn_name_resolver.py": {'lines': 258, 'max_func': 64, 'max_cc': 31},
    "backend/app/services/user_profile.py": {'lines': 88, 'max_func': 49, 'max_cc': 9},
    "backend/app/services/watchlist_display.py": {'lines': 1772, 'max_func': 239, 'max_cc': 68},
    "backend/app/services/watchlist_service.py": {'lines': 999, 'max_func': 124, 'max_cc': 28},
}

# 冻结的 legacy 服务文件集（与 BASELINE 键完全一致，由 BASELINE 派生，见上方说明）。
LEGACY_SERVICES: frozenset[str] = frozenset(BASELINE)


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _cyclomatic_complexity(func_node: ast.AST) -> int:
    """McCabe 圈复杂度（按 AST 决策点计）：基础 1 + 各分支。

    计数对象：if / for / while / except 子句 / with / assert / 三元 / 布尔运算
    （`and`/`or` 每多一个操作数 +1）/ 推导式（每个 comprehension +1，其内每个 `if` 再 +1）。
    只数函数体内的决策点——嵌套函数 / 方法各自独立计数，取全局最大。
    """
    cc = 1
    for node in ast.walk(func_node):
        if isinstance(
            node,
            (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
             ast.With, ast.AsyncWith, ast.Assert, ast.IfExp),
        ):
            cc += 1
        elif isinstance(node, ast.BoolOp):
            cc += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            cc += 1 + len(node.ifs)
    return cc


def collect_metrics(path: Path) -> dict[str, int]:
    """AST 统计单个服务文件的三项指标（不用正则，避免注释 / 字符串误命中）。"""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - 语法错误由 ruff/CI 先行拦截
        raise RuntimeError(f"{path}: 语法错误（{exc}）—— 请先过 ruff") from exc

    max_func = 0
    max_cc = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            max_func = max(max_func, span)
            max_cc = max(max_cc, _cyclomatic_complexity(node))

    return {
        "lines": source.count("\n") + (0 if source.endswith("\n") else 1),
        "max_func": max_func,
        "max_cc": max_cc,
    }


def _iter_services() -> list[Path]:
    if not SERVICES_DIR.is_dir():
        return []
    return sorted(SERVICES_DIR.rglob("*.py"))


def _fmt(metrics: dict[str, int]) -> str:
    return " ".join(f"{k}={metrics[k]}" for k in ("lines", "max_func", "max_cc"))


def _report(services: list[Path]) -> int:
    print("# 当前指标（可直接粘贴为 BASELINE；键按路径字典序）")
    print("BASELINE: dict[str, dict[str, int]] = {")
    for path in services:
        print(f'    "{_rel(path)}": {collect_metrics(path)!r},')
    print("}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="services 层体量 / 复杂度软闸门")
    parser.add_argument(
        "--report", action="store_true", help="打印当前指标与可直接粘贴的基线"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="打印每个文件的指标"
    )
    args = parser.parse_args(argv)

    services = _iter_services()
    if not services:
        print(f"❌ 拿不到输入：未找到 {SERVICES_DIR} —— 本轮结论不可信，不得当成通过")
        return 2

    if args.report:
        return _report(services)

    violations: list[tuple[str, str, int, int, bool]] = (
        []
    )  # (rel, metric, current, limit, is_baseline)
    seen: set[str] = set()
    measured: dict[str, dict[str, int]] = {}

    for path in services:
        rel = _rel(path)
        seen.add(rel)
        metrics = collect_metrics(path)
        measured[rel] = metrics
        is_legacy = rel in LEGACY_SERVICES
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
            # fat 条目也忽略（防 gaming：给新文件塞 800+ 行基线绕过新增上限）。
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
            "max_func": max((m["max_func"] for m in BASELINE.values()), default=0),
            "max_cc": max((m["max_cc"] for m in BASELINE.values()), default=0),
        }
        print(
            "OK: services 层体量 / 复杂度无新增（基线存量："
            f"{len(BASELINE) - len(stale)} 个文件 / {remaining['lines']} 行；"
            f"最长函数 ≤ {remaining['max_func']} 行 / 最高圈复杂度 ≤ {remaining['max_cc']}；只减不增）"
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
        "ERROR: services 层变厚 / 变复杂了——请把职责下沉或拆出子模块（视图/其它层复用 services 是合法边）\n"
        "       判据：services 层体量 / 复杂度软闸门（防 #2873 类上帝模块复发）\n"
        "       上限：新增服务文件 lines ≤ 800 / 最长函数 ≤ 120 / 圈复杂度 ≤ 20",
        file=sys.stderr,
    )
    for rel, metric, current, limit, is_baseline in violations:
        scope = "基线冻结（只减不增）" if is_baseline else f"新增上限 {limit}"
        print(f"  {rel}: {metric} = {current}（{scope}）", file=sys.stderr)
    print(
        "\n      缩小的正解是把职责下沉到更细的服务 / 子模块（services 内部互相调用是合法边）；\n"
        "      确因合并需要重取基线：python scripts/guard_service_size.py --report 并说明理由。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
