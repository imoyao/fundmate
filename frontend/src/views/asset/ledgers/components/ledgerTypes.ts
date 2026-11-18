/**
 * 账户页卡片 / 分组 / 费率配置的共享最小契约（#2879 第七刀）。
 *
 * `overview.groups` 的聚合行、后端 `LedgerItem`、列表里的虚拟行（如 `orphan`）
 * 形状并不一致；这里只声明组件模板与 composable 真正读到的字段，字段全部可选
 * 且不放开索引签名——拼错字段名仍会报错，父页面传更具体的类型也能直接赋值。
 */

/** 账户（含 orphan 虚拟行，故 id 允许字符串） */
export interface LedgerLike {
  id?: number | string;
  name?: string;
  ledger_type?: string;
  channel_category?: string;
  owner_member_id?: number | string | null;
  owner_member_name?: string;
  is_active?: boolean;
  total_market_value?: number | null;
  cash_balance?: number | null;
  position_count?: number;
  pnl?: number | null;
  linked_liability?: number;
  display_order?: number | null;
  total?: number | null;
  stale_count?: number;
  /**
   * 累计盈亏（2026-11-10）：仅投资类账户下发，`undefined` = 该账户没有这个口径。
   * 卡片据此决定「整项不渲染」，不要用 `?? 0` 兜底成 0 元。
   */
  realized_pnl?: number | null;
  buy_fee?: number | null;
  total_pnl?: number | null;
}

/** overview.groups 的分组行 */
export interface OverviewGroupLike {
  type?: string;
  label?: string;
  count?: number;
  total?: number | null;
  ledgers?: LedgerLike[];
}

/** 费率配置：证券 / 基金平台两套结构，字段全部可选 */
export interface FeeConfigLike {
  commission?: { rate?: number; min?: number };
  stamp_duty?: { rate?: number; scope?: string };
  transfer_fee?: { rate?: number; scope?: string };
  subscription_discount?: number;
}
