// src/api/types.d.ts
/** 后端统一响应格式 */
export interface ApiResponse<T> {
  data: T;
  message: string;
}

/** 后端错误响应格式 */
export interface ApiError {
  error: {
    code: string;
    message: string;
  };
}

/** 持仓记录 */
export interface Position {
  id: number;
  symbol: string;
  name: string | null;
  market: string;
  type: string;
  account_name: string;
  quantity: number;
  avg_price: number;
  currency: string;
  current_price: number;
  trade_date: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  type_label?: string;
  market_label?: string;
  allocation_label?: string;
  /** 所属账户 ID：后端 PositionOut 会输出（group_by 路径必含），分页路径可能缺失 */
  ledger_id?: number | null;
  /** 配置目标：后端 PositionOut 可能输出，前端不保证 */
  allocation?: string | null;
  /** 首次确认日期：group_by 路径必含，分页路径可能缺失 */
  confirm_date?: string | null;
  /**
   * 市值 / 盈亏：由后端 `services/position_presenter.enrich_position_dict` 现算产出
   * （#1174 已收口到唯一市值口径 `position_valuation.market_value_cents`），**非落库列**。
   * 标为可选，是因为取不到时按 0 处理，不谎报必有。
   *
   * 2026-10-10 复核更正：原注释称「enrich_position_dict 目前不产出这两个字段（已知 bug，
   * 见 Inventory 表格 :262/:270）」——**该说法不成立**。该函数 L38-45 明确产出两者，
   * 后端 `tests/domains/test_positions.py:948` 亦有断言。原注释指向的 Inventory 表格
   * 那条路径是否另有问题，不在 #2005 范围，未复核。
   */
  market_value?: number;
  pnl?: number;
  /**
   * 当日盈亏（#2007）= `(现价 − 上一确认价) × 数量`，单位**元**（与 `pnl` 同）。
   * `null` = 没有基准价（后端 `prev_close` 为空）→ 展示层降级「—」，
   * **不得当 0 用**：0 会被读成「今天一分没涨没跌」，而真相是没数据。
   * 由 `services/position_presenter.enrich_position_dict` 现算产出，非落库列。
   */
  day_pnl?: number | null;
  /**
   * 当日盈亏率（#2007）：单位与后端既有 `pnl_rate` **逐字一致 —— 百分数**
   * （10 表示 10%），所以这里不再 ×100。`null` = 没有基准价。
   */
  day_pnl_rate?: number | null;
  /** 上一确认价（元）；`null` = 未取到（#2007）。当日盈亏的基准 */
  prev_close?: number | null;
  /** `current_price` 对应的交易日（`YYYY-MM-DD`）；`null` = 未知（#2007） */
  price_date?: string | null;
  /**
   * 持仓天数：后端 `PositionOut.holding_days` 的派生字段（#862）。
   * 此前前端类型漏声明，导致详情页「我的持仓」拿不到、也就一直没展示（#2005 补）。
   */
  holding_days?: number | null;
}

/** 持仓分页列表请求参数（对齐后端 list_positions） */
export interface PositionListParams {
  page?: number;
  per_page?: number;
  /**
   * 按产品代码过滤（#1966）：详情页「我的持仓」区块取数用，后端下推到 SQL。
   * 同时匹配展示形态与归一身份键，故 `SZ000001` 与 `000001.SZ` 视为同一只产品。
   */
  symbol?: string;
  /** 市场消歧：同码跨市场时与 symbol 组合使用 */
  market?: string;
  /** 按关联账户ID精确过滤；传字符串 'null' 表示仅查未归档持仓（对齐后端 views.py） */
  ledger_id?: string | number;
}

/** 持仓分页响应（对齐后端分页信封：{ data, total, page, per_page, message }） */
export interface PositionListResponse {
  data: Position[];
  total: number;
  page: number;
  per_page: number;
  message: string;
}

/** group_by=account 响应（对齐后端 { data: {账户名: [position_dict]}, message }） */
export interface PositionGroupedResponse {
  data: Record<string, Position[]>;
  message: string;
}

/** 持仓关联交易明细（后端 /<id>/transactions/ 返回项） */
export interface PositionTransaction {
  id: number;
  trade_date: string | null;
  txn_type: string;
  quantity: number;
  price: number;
  amount: number;
  notes: string | null;
}

/** 交易规则校验结果（后端 /validate/ 返回 { valid, message }） */
export interface TradeValidationResult {
  valid: boolean;
  message: string;
}

/** 创建持仓请求体 */
export interface PositionCreate {
  symbol: string;
  name?: string;
  market: string;
  type: string;
  /** 交易场所 EXCHANGE/OTC（#1662）：缺省时后端按 type 推断（见 constants/market.ts） */
  venue?: string;
  account_name?: string;
  ledger_id?: number | null;
  quantity: number;
  avg_price: number;
  currency?: string;
  trade_date: string;
  fee?: number;
  confirm_date?: string;
  notes?: string;
  op_type?: string;
  source?: string;
  /**
   * 幂等键：手动记账时由前端按「提交意图」生成并落到 import_hash。
   * 服务端 UNIQUE(ledger_id, import_hash) 据此拦截网络超时重发导致的重复写入；
   * 两个不同的提交意图（如同一天同一基金同金额买了两笔）天然拥有不同键，互不误杀。
   */
  import_hash?: string;
}

/** 更新持仓请求体 (PATCH，所有字段可选) */
export interface PositionUpdate {
  name?: string;
  account_name?: string;
  ledger_id?: number | null;
  quantity?: number;
  avg_price?: number;
  current_price?: number;
  currency?: string;
  trade_date?: string;
  notes?: string;
}

/** 仪表盘聚合数据 */
export interface SummaryData {
  total_assets_cny: number;
  total_pnl_cny: number;
  total_liabilities_cny: number;
  net_assets_cny: number;
  market_distribution: Record<string, number>;
}

/** 删除/解绑类端点的通用响应（data 为 null 或空对象，调用方通常只关心 message） */
export interface DeleteResponse {
  data: null | Record<string, never>;
  message: string;
}

// ── 自选资产实体（#965 P1「类型集中」）──
// 从 `api/watchlist.ts` 迁入：这些实体被 31 个模块跨文件复用，与请求函数混放会让
// 读代码时分不清「这是接口返回的数据形状」还是「这是请求的入参」。

export interface WatchlistItem {
  /** 自选记录 id；持仓分组返回的虚拟行（真实持仓聚合）无自选记录，恒为 null，前端据此禁用行操作 */
  id: number | null;
  symbol: string;
  market: string;
  asset_type: string;
  venue: string;
  status: string; // HOLDING / WATCHING
  favorite: boolean;
  favorite_at: string | null;
  /** 下次复盘提醒日期（未竟之蹊卡片底部复盘提醒，用户可设） */
  next_review_date?: string | null;
  is_pinned: boolean;
  pinned_at: string | null;
  add_reason: string | null;
  notes: string | null;
  /** 笔记摘要（仅 favorites 接口下发，后端截断 80 字） */
  notes_summary?: string | null;
  created_at?: string;
  updated_at?: string;
  display_name: string;
  group_ids: number[];
  /** 所属分组名称列表（后端 enrich，#1332 所属分组列与排序用） */
  group_names?: string[];
  tag_ids: number[];
  current_price?: number;
  change_pct?: number;
  /**
   * 最新价 / 涨跌幅的数据日期（YYYY-MM-DD，后端 enrich，#1104）。
   * 有值 = 该价格来自「最近交易日收盘价 / 确认净值」；null = 无行情、回退持仓快照。
   */
  price_as_of?: string | null;
  position_market_value?: number;
  /** 真实持仓统计（后端 enrich，positions 表汇总；区别于迁移透传的 cost_price/quantity） */
  holding_quantity?: number | null; // 真实持仓数量（份/股）
  holding_cost_price?: number | null; // 加权成本均价（元）
  holding_pnl?: number | null; // 持仓收益（元）
  holding_pnl_percent?: number | null; // 持仓收益率（%）
  price_at_added?: number | null; // 添加自选日最近交易日收盘价（元）
  type_label?: string; // 资产类型中文标签（后端动态字段）
  /** 投顾组合补充信息（后端 enrich，仅 AdvisorPortfolio 命中时有值；普通标的恒 null）。
   *  供产品列渲染分层信息行「平台 · 主理人 · 策略」，避免与代码/类型/标签挤一行 */
  advisor_platform?: string | null; // QIEMAN/DANJUAN/TIANTIAN/YINGMI
  advisor_host?: string | null; // 主理人
  advisor_strategy_type?: string | null; // 策略类型（均衡/进取/稳健）
  advisor_org_name?: string | null; // 主理人所属机构/平台方
  // ── 且慢组合补充指标与策展元数据（#1468）──
  // 指标部分来自 GetStrategyDetails 实时抓取，策展部分来自后端 advisor_catalog 注册表。
  // 仅 asset_type=portfolio 且 AdvisorPortfolio 命中时有值，其余恒 null。
  return_1d?: number | null; // 近1日收益(%)
  return_1q?: number | null; // 近1季度收益(%)
  return_6m?: number | null; // 近半年收益(%)
  volatility?: number | null; // 年化波动率(%)
  sharpe_ratio?: number | null; // 夏普比率
  advisor_allocation?: string | null; // 配置目标 key（liquid/stable/longterm/...）
  advisor_allocation_label?: string | null; // 配置目标中文标签（活钱/稳健底仓/长期增值/...）
  advisor_product_type?: string | null; // 产品类型（货币/货币+/纯债/固收+/平衡/权益(偏股)）
  advisor_strategy_summary?: string | null; // 策略简介（短）
  advisor_nav?: number | null; // 组合最新净值
  advisor_nav_date?: string | null; // 净值日期（YYYY-MM-DD）
  advisor_source_url?: string | null; // 组合官方页面链接
  manager_company?: string | null; // 基金经理所属基金公司（仅 asset_type=manager 有值）
  // ── 可转债条款（#1285 消费侧 / #1393）──
  // 仅 asset_type=bond 且后端 convertible_bond_terms 命中时有值，其余 null。
  // 数据源：集思录强赎（bond_cb_redeem_jsl）+ 东财基本信息（bond_zh_cov），免 cookie。
  bond_convert_price?: number | null; // 转股价（元）
  bond_convert_value?: number | null; // 转股价值（元）
  bond_premium_rate?: number | null; // 转股溢价率（%）
  bond_force_redeem_price?: number | null; // 强赎触发价（元）
  bond_redeem_count?: number | null; // 强赎天计数（已达）
  bond_redeem_required?: number | null; // 强赎触发所需天数
  bond_redeem_status?: string | null; // 强赎状态
  bond_rating?: string | null; // 信用评级
  bond_maturity_date?: string | null; // 到期日（前端据此算剩余年限）
  bond_remain_size?: number | null; // 剩余规模（亿元）
  bond_issue_size?: number | null; // 发行规模（亿元）
  bond_stock_name?: string | null; // 正股名称
  // ── 指数估值（#1285 消费侧「指数」品类 / #1394）──
  // 仅 asset_type=index 且后端 index_valuations 命中时有值；来源中证官方（免 cookie）。
  index_pe?: number | null; // 市盈率（官方列「市盈率1」）
  index_pe_2?: number | null; // 市盈率2（官方列名，口径以官方为准）
  index_dividend_yield?: number | null; // 股息率(%)（官方列「股息率1」）
  index_valuation_date?: string | null; // 估值日期（口径透明：展示「截至 X」）
  // ── 基金最大回撤（#1285 消费侧「基金」品类 / 设计 §3.10）──
  // §3.10 要求「存口径元数据，不只存数字」，故口径项随值一并下发，由前端展示。
  fund_max_drawdown?: number | null; // 最大回撤(%)，负值
  fund_max_drawdown_basis?: string | null; // current_tenure|prev_tenure|fixed_3y|insufficient
  fund_max_drawdown_window?: string | null; // 窗口描述（如「近3年」）
  fund_max_drawdown_as_of?: string | null; // 序列最后净值日（「截至」）
  // ── 跨渠道关联（#1285 设计 §3.8）：数量角标 + 浮层明细 ──
  // link_type 两类：index_etf（指数↔场内 ETF）、etf_feeder（场内 ETF↔场外联接）。
  // 实测 akshare 无「跟踪标的」字段，关联靠名称匹配，落库口径覆盖率约 66.4%。
  link_count?: number | null;
  links?: { code: string; name: string | null; link_type: string | null }[];
}

/**
 * 首页自选摘要行（#1954）。
 *
 * 口径与 `WatchlistItem` 的对应字段严格一致（同源 enrich），差异只有一处：
 * 无持仓时 `position_market_value` 是 `0.0`（非 null），而持仓三项为 `null`。
 */
export interface HomeSummaryItem {
  id: number;
  symbol: string;
  display_name: string;
  is_pinned: boolean;
  current_price: number | null;
  change_pct: number | null;
  /** 最新价 / 涨跌幅的数据日期（#1954，与自选列表 price_as_of 同义） */
  price_as_of?: string | null;
  position_market_value: number;
  status: string;
  /** 资产类型（小写枚举），用于价格精度判定 */
  asset_type?: string | null;
  venue: string;
  /** 资产类型中文标签（后端下发，#1954；此前缺失导致产品列不显示类别） */
  type_label?: string | null;
  /** 真实持仓统计（后端 enrich，与自选列表同源）；无持仓时为 null */
  holding_quantity?: number | null;
  holding_cost_price?: number | null;
  holding_pnl?: number | null;
  holding_pnl_percent?: number | null;
}

// 分组相关
export interface WatchlistGroup {
  id?: number;
  key?: string; // 系统分组专用
  name?: string; // 自定义分组专用
  label?: string; // 系统分组专用
  color: string | null;
  sort_order?: number;
  is_system: boolean;
  is_visible?: boolean;
  entity_type?: string;
  count: number; // 新增：资产数量
}

/** 持仓缺口：有活跃持仓但未加入自选的标的列表（前端 banner 引导一键加入）。 */
export interface HoldingGap {
  symbol: string;
  name: string;
  asset_type: string | null;
}

// ---------- 标签相关 ----------
export interface WatchlistTag {
  id: number;
  name: string;
  color: string | null;
}
