/**
 * 探市页跨组件传递的行 / 行情最小契约（#2879 第六刀）。
 *
 * 榜单、单值指标、本地观察行来自三个不同接口，各自字段比消费方需要的多；
 * 这里只声明组件真正读到的字段，且不放开索引签名（拼错字段名仍会报错）。
 * el-table 插槽里的 `row` 由组件库定义，与本文件相互独立。
 */

/** 拥挤度 / 乖离率榜单条目 */
export interface RankItem {
  item_code?: string;
  item_name?: string;
  stale?: boolean;
  date?: string;
  data?: unknown;
}

/** 全部市场温度指标（单值） */
export interface MetricItem {
  name?: string;
  note?: string;
  source?: string;
  value?: number | string | null;
  label?: string;
  unit?: string;
  stale?: boolean;
}

/** 实时行情：探市页实际读到的三档价格 */
export interface QuoteLike {
  currentPrice?: number;
  changePct?: number;
  prevClose?: number;
}

/** 本地观察持仓行 */
export interface HoldingRow {
  symbol?: string;
  name?: string;
  type?: string;
  costPrice?: number | null;
  quantity?: number | null;
}

/** 观察列表表格 / 卡片展示行 */
export interface WatchlistRow extends HoldingRow {
  id?: string | number;
  quote?: QuoteLike | null;
  price?: number;
  changePct?: number;
  pnl?: number;
  positionPnl?: number;
  stale?: boolean;
}
