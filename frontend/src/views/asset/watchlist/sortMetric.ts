/**
 * 复合列「排序口径」唯一入口（2026-10-30 二次优化，用户反馈）。
 *
 * ## 为什么抽成独立模块
 *
 * 自选表里有**三个复合列**，都是「主行金额 + 副行比例」两行数：
 *
 * | 列 | 主行（amount） | 副行（ratio） |
 * |---|---|---|
 * | 当日盈亏 `day_pnl` | 当日盈亏（元） | 当日涨跌幅（%） |
 * | 持仓市值 `position_market_value` | 持仓市值（元） | 占投资类总市值（%） |
 * | 持仓收益 `holding_pnl` | 持仓收益（元） | 持仓收益率（%） |
 *
 * 两行是**两个不同的量**：同样涨 1%，一万仓与百万仓的当日盈亏差两个数量级；
 * 同样赚 1 万，五万本金是 +20%、一百万本金是 +1%。所以两行必须能**各排各的**。
 *
 * 口径的「有哪些取值 / 怎么从两行里取一个数 / 旧值怎么迁移」只应有一处定义——
 * 表头（`components/CompositeSortHeader.vue`）、数据层（`useWatchlistData` 的记忆）、
 * 排序分发（`useWatchlistTable`）三处都从这里取，否则三处各写一遍迟早算出两套语义
 * （#980 拆分以来的一贯做法，同 `dayPnl.ts` / `clientSort.ts`）。
 *
 * ## 为什么不叫 DayPnlMetric 了
 *
 * 2026-10-30 首版只有「当日盈亏」一列可切口径，类型因此叫 `DayPnlMetric` 且取值是
 * `amount` / `pct`。这次统一到三列后：`pct` 只是「涨跌幅」这一列的说法（另有占比、
 * 收益率），故取值改成语义中性的 `amount` / `ratio`，旧值 `pct` 在读盘时迁移。
 */

/** 排序口径：`amount` = 按主行金额，`ratio` = 按副行比例（% 语义，列与列叫法不同） */
export type SortMetric = "amount" | "ratio";

/** 复合列的两行数（renderer 与排序共用同一结构） */
export interface SortValue {
  /** 主行：金额；null = 算不出 */
  value: number | null;
  /** 副行：比例 / 百分比；null = 算不出 */
  ratio: number | null;
}

/** 缺省口径 = 金额：与列主行一致，也是用户看自选表的默认诉求（谁赚得多） */
export const DEFAULT_SORT_METRIC: SortMetric = "amount";

/**
 * 按口径取列里的可比数（金额 / 比例）；**只用于排序，不参与渲染**。
 *
 * 缺值原样透传 `null`（交给 `sortRowsForClient` / 后端垫底），**不当 0**：
 * 把「没有数据」当 0 会让这行看起来像「跌到 0 / 收益 0」，比空白更贵。
 */
export function pickSortMetric(
  result: SortValue,
  metric: SortMetric
): number | null {
  return metric === "amount" ? result.value : result.ratio;
}

/** 另一个口径（表头徽标点击时切换的下一档） */
export function otherSortMetric(metric: SortMetric): SortMetric {
  return metric === "amount" ? "ratio" : "amount";
}

/**
 * 归一化读盘值；无法识别返回 `null`（调用方回落 `DEFAULT_SORT_METRIC`）。
 *
 * `pct` 是 2026-10-30 首版的旧值（只服务「当日盈亏」列），迁移为 `ratio`——
 * 否则老用户存过「按涨幅排序」，升级后会静默回落成「按金额」。
 */
export function normalizeSortMetric(raw: unknown): SortMetric | null {
  if (raw === "amount" || raw === "ratio") return raw;
  if (raw === "pct") return "ratio";
  return null;
}

/**
 * 表头徽标符号：金额用 `¥`、比例用 `%`。
 *
 * 为什么不用「金额 / 涨幅」四个字：`当日盈亏` 列宽只有 104px（默认列预算 1040 已用满
 * 1036，见 `columnDefs.ts` 铁律 1），列名 56px + 徽标 + 排序三角 18px + 内边距 8px 之后
 * 只够一个字符。`¥` / `%` 各自对应列的上下两行，语义直白且不随列改文案。
 */
export function sortMetricSymbol(metric: SortMetric): string {
  return metric === "amount" ? "¥" : "%";
}
