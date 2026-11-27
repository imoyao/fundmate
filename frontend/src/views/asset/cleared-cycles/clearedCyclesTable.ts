/**
 * 清仓周期表的客户端排序 / 分页（纯函数，2026-11-27）。
 *
 * ## 为什么在客户端
 *
 * 接口一次返回全量周期（实测 334 行），而「汇总 / 胜率 / 盈亏比 / Top5 排行」
 * 全部吃这份全量。服务端分页会让明细与汇总不同口径（第 2 页的和 ≠ 卡片上的数），
 * 所以分页只做「看到哪几行」，排序只做「按哪一列排」——两者都不改变任何汇总。
 *
 * ## 三条规则（与 `views/asset/watchlist/clientSort.ts` 同源）
 *
 * 1. **缺值恒末尾**，与升 / 降序无关：`--` 不该因为降序跑到第一行，
 *    那看起来像「涨 / 跌到极端」；
 * 2. **稳定**：同值时按原始下标，避免重排时同值行来回跳；
 * 3. **数值按数值比、文本按 `zh-CN` 比**：不把 `"102.50"` 当字符串排
 *    （那会把 102.5 排到 99.9 前面）。
 */

import type { ClearedCycle } from "@/api/summary";

/**
 * 可排序列 —— 表头的 `prop` 必须在其中，漏登记的表头点了不会有反应。
 *
 * `last_sell_date` 不在表头（首买日 / 末卖日已按 2026-11-27 拍板移出表格，只留
 * 「持有天数」），仍保留在联合类型里：`DEFAULT_SORT_KEY` 用它表达「与后端出参同序」
 * （末卖日降序），这是清掉排序后的回退序，不是某一列。
 */
export type ClearedSortKey =
  | "name"
  | "realized_pnl"
  | "pnl_pct"
  | "ledger_names"
  | "avg_holding_days"
  | "last_sell_date"
  | "post_clear_pct";

export type ClearedSortOrder = "asc" | "desc";

/** 表头点第三下（清空排序）时回到这个默认序：与后端出参同序，不引入第二套默认 */
export const DEFAULT_SORT_KEY: ClearedSortKey = "last_sell_date";
export const DEFAULT_SORT_ORDER: ClearedSortOrder = "desc";

/** 每页条数选项。标成 `number[]` 而不是 `as const` 元组：el-pagination 的
 *  `page-sizes` 要可变数组，只读元组会被 vue-tsc 拒（TS4104） */
export const PAGE_SIZES: number[] = [20, 50, 100];
export const DEFAULT_PAGE_SIZE = 20;

/** 取排序值：空串 / NaN / 缺失统一收敛成 null（交给「缺值恒末尾」处理） */
function sortValue(
  row: ClearedCycle,
  key: ClearedSortKey
): number | string | null {
  const raw = (row as unknown as Record<string, unknown>)[key];
  // 账户是多值（同一只产品可能在多个账户买入）：排序与展示同口径，只比首个账户名
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const text = value.trim();
    return text === "" ? null : text;
  }
  return null;
}

/** 排序（不改入参，返回新数组） */
export function sortCycles(
  rows: readonly ClearedCycle[],
  key: ClearedSortKey,
  order: ClearedSortOrder
): ClearedCycle[] {
  const dir = order === "desc" ? -1 : 1;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const av = sortValue(a.row, key);
      const bv = sortValue(b.row, key);
      // 缺值恒末尾（升序降序都一样），两边都缺则按原始顺序
      if (av === null && bv === null) return a.index - b.index;
      if (av === null) return 1;
      if (bv === null) return -1;
      const cmp =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv), "zh-CN");
      // 同值按原始下标，保证稳定
      return cmp === 0 ? a.index - b.index : cmp * dir;
    })
    .map(item => item.row);
}

/**
 * 切页。页码越界一律夹回有效区间（切时间范围后行数变少、停在旧页会看到空表），
 * 返回的 `current` 是**夹取后**的页码，供调用方回写。
 */
export function paginate<T>(
  rows: readonly T[],
  page: number,
  size: number
): { rows: T[]; total: number; pages: number; current: number } {
  const total = rows.length;
  const perPage = size > 0 ? size : DEFAULT_PAGE_SIZE;
  const pages = Math.max(1, Math.ceil(total / perPage));
  const raw = Number.isFinite(page) ? Math.trunc(page) : 1;
  const current = Math.min(Math.max(1, raw || 1), pages);
  const start = (current - 1) * perPage;
  return { rows: rows.slice(start, start + perPage), total, pages, current };
}
