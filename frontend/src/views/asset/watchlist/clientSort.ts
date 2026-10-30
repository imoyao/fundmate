/**
 * 自选表格「整组客户端排序」纯函数（2026-10-30）。
 *
 * ## 为什么要改到客户端排整组
 *
 * 后端自选接口的 `current_price` / `change_pct` **不是今天的数**：`compute_latest_quote`
 * 取 `price_history` 最近一根收盘价（job 每天 17:30 跑），盘中库里就是**上一交易日收盘**。
 * 于是：
 *
 * - 后端 `change_pct` = **昨天的涨跌幅**，`(current_price - prev_close) * qty` = **昨天的**
 *   当日盈亏（两个值都来自同一根 T-1 收盘价，等于把昨天的数当今天）；
 * - 前端列里显示的却是实时价算出来的**今天的**值（`useRealtimeQuotes` 浏览器直连腾讯/天天）。
 *
 * 「按今天的涨幅排序」因此**不可能靠后端 `sort_by` 实现**——那会按昨天的数排，序与列里
 * 的数字毫无关系。旧实现对这两列退化成「只排当前页」（#1333），于是第 2 页重新从头上开始，
 * 用户看到的就是「点了排序但顺序很乱」。
 *
 * 现口径：**这两列（以及同样吃实时价的最新价）一律在客户端对全量结果排**，再本地切页。
 * 全量结果来自 `allItems`（`fields=lite`，已含 prev_close / holding_quantity，见
 * `useWatchlistData.fetchAllItems`），实时行情也覆盖全量 symbol（`getHoldings` 读 allItems）。
 *
 * ## 与后端排序对齐的三条规则
 *
 * 1. **置顶恒前置**：后端 `apply_user_sort` 是「先按指标排，再按 is_pinned 稳定二分」，
 *    这里同序做，否则同一张表在「按金额排」与「按持有数量排」下置顶行会跳位置。
 * 2. **缺值（null / NaN）恒排末尾**，与升/降序无关——缺数据不该被当成 0 混进队首
 *    （那看起来像「涨/跌到极端」）。
 * 3. **稳定排序**：同值时按原始下标，避免每次重算（实时 tick 30s 一次）时同值行乱跳。
 */

/** 升/降序（与后端 `sort_order` 同词，避免又一套 asc/descending 词汇） */
export type ClientSortOrder = "asc" | "desc";

export interface ClientSortOptions<T> {
  order: ClientSortOrder;
  /** 排序取值；返回 null 表示该行缺数据（恒排末尾） */
  valueOf: (row: T) => number | null;
}

/**
 * 按 `valueOf` 整组排序：置顶前置 → 指标序 → 缺值垫底。
 *
 * @param rows 全量行（**不是**当前页）；本函数不改输入，返回新数组
 */
export function sortRowsForClient<T extends { is_pinned?: boolean | null }>(
  rows: readonly T[],
  { order, valueOf }: ClientSortOptions<T>
): T[] {
  const dir = order === "desc" ? -1 : 1;
  const known: { value: number; row: T; index: number }[] = [];
  const unknown: T[] = [];

  rows.forEach((row, index) => {
    const value = valueOf(row);
    if (typeof value === "number" && Number.isFinite(value)) {
      known.push({ value, row, index });
    } else {
      unknown.push(row);
    }
  });

  known.sort((a, b) =>
    a.value === b.value ? a.index - b.index : (a.value - b.value) * dir
  );

  // 与后端同一口径：置顶行恒在最前（稳定二分，不改变组内相对顺序）
  const pinned = known.filter(item => item.row.is_pinned);
  const rest = known.filter(item => !item.row.is_pinned);
  return [...pinned, ...rest].map(item => item.row).concat(unknown);
}
