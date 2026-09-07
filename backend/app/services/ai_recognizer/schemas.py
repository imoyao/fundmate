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

类型约束与运行期（重要）：
- 三个 TypedDict 均为 `total=True`，但**各类的必填键集合不同，以各类 docstring 为准**：
  自选场景仅 `code` / `name` 必填；交易场景另含 `business_type` / `trade_date` /
  `confirm_date`（识别器始终产出，`confirm_date` 值可空）；其余字段一律以 `NotRequired`
  标记（enrich 回填的 symbol/type/market/venue，以及 LLM 可能缺省的金额/份额等）。
  `total=True` 保留对必填键的静态约束，避免 `dict["code"]` 缺键。
- TypedDict 仅作静态类型检查，运行期仍是 dict，不强制字段存在与类型；真正运行时校验
  落点在 `base.py` 模板方法 `recognize_text` / `recognize_image`：其调用链
  `extract → validate → enrich` 中，`validate`（各识别器）对数值/日期做防御式 `.get()`
  + 类型转换兜底，enrich 再回填反查字段。下游（recognizers.validate / catalog.enrich /
  importer 预览与入库管线）一律用 `.get()` 容缺省读取，不依赖 TypedDict 运行期强制。
- `TransactionCandidateDict.fee` 由 dataclass 默认 0.0 改为 `NotRequired[float]`（可能缺省），
  语义为「缺省即 0.0」，下游读取需容缺省（`it.get('fee') or 0`）。
- `HoldingCandidateDict.avg_cost` 落库映射 `Position.avg_price`（DB 列）/ enrich 字段
  `holding_cost_price`：保留 `avg_cost` 命名贴合 LLM 输出与预览表格，术语映射在此标注，
  避免识别结果落库时术语漂移。
"""

from typing import List, NotRequired, Optional, TypedDict


class WatchlistCandidateDict(TypedDict, total=True):
    """自选场景候选行（代码 + 名称 + 反查后的类型信息）。

    仅 `code` 为必填键（`name` 始终产出但值可空）；`symbol/type/market/venue`
    由 catalog.enrich 回填空缺，故标 `NotRequired`。TypedDict 仅静态约束，
    运行期仍是 dict，下游一律用 `.get()` 容缺省读取（见模块 docstring）。
    """

    code: str  # 6 位数字代码（必填）
    name: Optional[str]  # 名称（可空：缺省为 '' 或 None）
    symbol: NotRequired[Optional[str]]  # 标准化代码（场内如 SH600519；场外基金为裸代码）
    type: NotRequired[Optional[str]]  # stock / etf / bond / fund
    market: NotRequired[Optional[str]]  # CN_A / CN_B ...
    venue: NotRequired[Optional[str]]  # EXCHANGE / OTC


class TransactionCandidateDict(TypedDict, total=True):
    """交易场景候选行（比自选多买卖/日期/金额/份额等字段）。

    所有金额/份额/净值为「元 / 份」原始单位（与 importer 解析结果一致），
    入库时由 importer 管线统一换算（Money），本域不做精度换算。

    必填键：`code`、`name`、`business_type`、`trade_date`、`confirm_date`
    （识别器始终产出；`confirm_date` 值可空，缺省入账用申请日）。
    `amount/shares/nav/fee` LLM 可能缺省 → `NotRequired`；`fee` 缺省 0.0，
    下游读取需容缺省。`symbol/type/market/venue` 由 catalog.enrich 回填 →
    `NotRequired`。`warnings` 仅 LLM 层产生 → `NotRequired`。
    """

    code: str
    name: Optional[str]
    business_type: str  # 内部编码：buy / sell / dividend_cash / dividend_reinvest
    trade_date: str  # 申请日 YYYY-MM-DD（截图通常只有该字段）
    confirm_date: Optional[str]  # 确认日 YYYY-MM-DD（可空，缺省入账用申请日）
    amount: NotRequired[Optional[float]]  # 金额（元）
    shares: NotRequired[Optional[float]]  # 份额/股数（份/股）
    nav: NotRequired[Optional[float]]  # 净值/单价（元）
    fee: NotRequired[float]  # 手续费（元，缺省 0.0；下游读取需容缺省）
    symbol: NotRequired[Optional[str]]
    type: NotRequired[Optional[str]]
    market: NotRequired[Optional[str]]
    venue: NotRequired[Optional[str]]
    warnings: NotRequired[List[str]]  # 校验失败信息（预览表格展示用）


class HoldingCandidateDict(TypedDict, total=True):
    """持仓场景候选行（仅产出「持仓」，绝不产出交易流水，见 #1018）。

    提交阶段由 ImportOrchestrator.preview_holding_records / commit_holdings 落库，
    不经由 process_buy_or_deposit 交易管线。

    必填键：`code`、`name`（始终产出）。`avg_cost` 落库时映射为
    `Position.avg_price`（DB 列）/ enrich 字段 `holding_cost_price`，本契约保留
    `avg_cost` 命名以贴合 LLM 输出与预览表格；`symbol/asset_type/type/market/venue`
    由 enrich 回填或可能缺失 → `NotRequired`。
    """

    code: str
    name: Optional[str]
    symbol: NotRequired[Optional[str]]  # 标准化代码（场内如 SH600519；场外基金为裸代码）
    asset_type: NotRequired[str]  # 资产类型（fund / etf / stock ...），落库用
    shares: NotRequired[float]  # 份额/股数
    avg_cost: NotRequired[float]  # 单位成本价（元）；落库映射 Position.avg_price
    market_value: NotRequired[float]  # 当前市值（元）
    snapshot_date: NotRequired[Optional[str]]  # 快照日期 YYYY-MM-DD（可空）
    type: NotRequired[Optional[str]]  # 反查所得（catalog.enrich 回填）
    market: NotRequired[Optional[str]]
    venue: NotRequired[Optional[str]]
