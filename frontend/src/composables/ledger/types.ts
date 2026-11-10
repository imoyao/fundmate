/**
 * 账户详情域的行 / 概览类型（#2931，D87）。
 *
 * ## 为什么单独一个文件
 *
 * #2922（D85）把 `useLedgerDetail` 拆成「父文件 + `ledger/` 两个子域」后，这些类型仍住在
 * 父文件里，两个子域只能 `import type { ... } from "@/composables/useLedgerDetail"` **反向**
 * 引用——运行时被擦除、不构成循环，但依赖方向是反的：子域依赖父文件，父文件就无法在不牵动
 * 子域的前提下调整形状；视图组件也被迫从「一个 composable 的实现文件」里取纯类型。
 *
 * 搬到本文件后：两个子域与视图组件直接引用这里，父文件只保留
 * `export type { ... }` 兼容转发（对外 import 路径不变）。
 *
 * 判据见 `composables/__tests__/composableOwnership.spec.ts` 的 T1 组：
 * 三个类型只许在本文件声明；`composables/ledger/*.ts` 不许再出现
 * `from "@/composables/useLedgerDetail"`。
 */

/** 账户概览（GET /api/ledgers/{id}/summary/） */
export interface LedgerSummaryData {
  ledger_id?: number;
  ledger_name?: string;
  ledger_type?: string;
  portfolio_name?: string | null;
  total_market_value?: number;
  position_pnl?: number;
  position_count?: number;
  cash_balance?: number | null;
  /** 类现金合计（#1137）：货基 + 逆回购 + 账户现金，口径同 XIRR EXCLUDED_ASSET_TYPES */
  cash_like_amount?: number;
  /** 中高风险投资资产 = 总市值 - **持仓内**类现金（#1137） */
  investment_amount?: number;
  /**
   * **持仓内**类现金（货基/逆回购持仓市值），是 `total_market_value` 的子集。
   *
   * ⚠️ 它与 `cash_like_amount` 不同：后者还含「账外类现金」（孤儿货基/逆回购流水净额
   * + 账户现金），那部分不建持仓、不在总市值内。环形图必须用本字段做「现金类资产」片，
   * 否则两片之和 ≠ 左侧总资产，且「投资资产」会被算成负数
   * （真机：账户 id=12 曾显示「投资资产 -63.2% / 现金类资产 163.2%」）。
   */
  cash_like_in_positions_amount?: number;
  /** 类现金明细：货基市值 */
  money_fund_amount?: number;
  /** 类现金明细：账户现金 */
  cash_amount?: number;
  /**
   * 账外类现金逐产品明细（#2155）：孤儿货基/逆回购流水按产品归组。
   *
   * ⚠️ 只给汇总数不构成解释——用户问「这笔钱是什么、为什么不在持仓里」时
   * 需要能逐产品看到（真机账户 id=12 账外孤儿净额 476,951 元）。
   */
  cash_like_breakdown?: CashLikeBreakdownRow[];
  /**
   * 账外孤儿流水**本金净额**（不建持仓、不进总市值）。
   * 真机形态：账户「同花顺——银河」此项 476,951 元，而持仓市值仅 296,042 元。
   */
  orphan_amount?: number;
  /**
   * 账外孤儿流水里的渠道**收益桶**（#863 D1）。同样不建持仓，但已计入家庭总资产。
   * 它**不在** `cash_like_amount` 的加总里，单列是为了说清「账外对总资产的贡献」。
   */
  orphan_income_amount?: number;
  /** 账户现金（`Asset.major_category='cash'`），账外项之一 */
  account_cash_amount?: number;
  linked_liability?: number;
  type_distribution?: Record<string, number>;
  /**
   * 累计盈亏三段（2026-11-10）：`total = 已实现 + 持仓浮盈 − 买入费`。
   * **仅投资类账户（stock / fund / e_account）下发**；bank / property 缺这三个字段，
   * 缺失即「没有这个口径」，不渲染，不得 `?? 0` 兜底。
   */
  realized_pnl?: number;
  buy_fee?: number;
  total_pnl?: number;
}

/** 账外类现金逐产品明细行（`cash_like_breakdown` 元素，#2155） */
export interface CashLikeBreakdownRow {
  name: string;
  symbol?: string | null;
  asset_type?: string | null;
  asset_type_label?: string;
  /** 本金净额（元）：buy/deposit − sell/withdraw，不含收益行 */
  net_amount: number;
  /** 渠道收益（元）：is_income=True 的发放行 */
  income_amount: number;
  /** 本金 + 收益，本行合计 */
  total_amount: number;
  txn_count: number;
}

/** 持仓行（GET /api/ledgers/{id}/positions/ 分页 items） */
export interface LedgerHoldingRow {
  id: number;
  symbol?: string;
  name?: string | null;
  asset_type?: string;
  type_label?: string;
  market_value?: number;
  pnl?: number;
  pnl_rate?: number;
  avg_price?: number;
  /** 持有时长（天），基于本轮建仓确认日 confirm_date；清仓后重买重置；无确认日时为 null（#862） */
  holding_days?: number | null;
  current_price?: number;
  /** 价格时点（#2140）：基金=实际采用的最新净值日；其他=快照回写日；缺失为 null */
  price_date?: string | null;
  /**
   * 当日确认口径是否已定型（#2210）：true = 估值副行应隐藏；null / 缺省 = 不隐藏。
   * **状态 = 后端字段契约**，前端禁止按日期自行推断。
   */
  settled_today?: boolean | null;
  allocation?: string | null;
  allocation_label?: string;
  quantity?: number;
  account_name?: string;
  /**
   * 所属组合（D20 持仓级组合）：后端 `GET /api/ledgers/<id>/positions/` 输出。
   *
   * - 具体数字 = 显式指派到该组合；
   * - `null` = 未指派，归到**本账户默认组合**（本页的「随账户」）；
   * - `undefined` = 响应里没有该字段 → 未知，**不得当 `null` 渲染成「随账户」**。
   */
  portfolio_id?: number | null;
}
