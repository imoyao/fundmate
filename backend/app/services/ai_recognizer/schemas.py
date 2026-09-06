# -*- coding: utf-8 -*-
"""AI 识别域候选行数据契约（单一事实来源）。

识别器产出 + catalog.enrich 反查后的候选行结构；对外（API）统一转 dict 传输，
前端 ocr.ts 的 OcrImportItem / OcrTxnRow / OcrHoldingRow 对应消费。

设计（ai-recognizer-architecture-2026-08-13.md §3）：AI 识别域只产出候选行（dict），
不碰业务表；提交由各业务域负责（自选 → watchlist 域；交易 → importer 管线；
持仓 → importer.preview_holding_records）。本模块仅作类型契约，运行期仍是 dict，
不引入任何抽象层（P5 决策：不做顶层统一抽象，共享收敛到预览/入库管线）。

三个场景识别器各自实现 BaseRecognizer，其 validate/extract/regex_extract 返回对应
TypedDict 列表；enrich 阶段（catalog.enrich）再回填 symbol/type/market/venue 等反查字段。
新增场景只需在 recognizers/ 加一个识别器并据此约定返回键集，无需改动本契约以外的代码。
"""

from typing import List, Optional, TypedDict


class WatchlistCandidateDict(TypedDict, total=False):
    """自选场景候选行（代码 + 名称 + 反查后的类型信息）。"""

    code: str  # 6 位数字代码（必填）
    name: str  # 名称（可空）
    symbol: str  # 标准化代码（场内如 SH600519；场外基金为裸代码）
    type: str  # stock / etf / bond / fund
    market: str  # CN_A / CN_B ...
    venue: str  # EXCHANGE / OTC


class TransactionCandidateDict(TypedDict, total=False):
    """交易场景候选行（比自选多买卖/日期/金额/份额等字段）。

    所有金额/份额/净值为「元 / 份」原始单位（与 importer 解析结果一致），
    入库时由 importer 管线统一换算（Money），本域不做精度换算。
    """

    code: str
    name: str
    business_type: str  # 内部编码：buy / sell / dividend_cash / dividend_reinvest
    trade_date: str  # 申请日 YYYY-MM-DD（截图通常只有该字段）
    confirm_date: str  # 确认日 YYYY-MM-DD（可空，缺省入账用申请日）
    amount: Optional[float]  # 金额（元）
    shares: Optional[float]  # 份额/股数（份/股）
    nav: Optional[float]  # 净值/单价（元）
    fee: float  # 手续费（元）
    symbol: str
    type: str
    market: str
    venue: str
    warnings: List[str]  # 校验失败信息（预览表格展示用）


class HoldingCandidateDict(TypedDict, total=False):
    """持仓场景候选行（仅产出「持仓」，绝不产出交易流水，见 #1018）。

    提交阶段由 ImportOrchestrator.preview_holding_records / commit_holdings 落库，
    不经由 process_buy_or_deposit 交易管线。
    """

    code: str
    symbol: str  # 标准化代码（场内如 SH600519；场外基金为裸代码）
    asset_type: str  # 资产类型（fund / etf / stock ...），落库用
    name: str
    shares: float  # 份额/股数
    avg_cost: float  # 单位成本价（元）
    market_value: float  # 当前市值（元）
    snapshot_date: str  # 快照日期 YYYY-MM-DD（可空）
    type: str  # 反查所得（catalog.enrich 回填）
    market: str
    venue: str
