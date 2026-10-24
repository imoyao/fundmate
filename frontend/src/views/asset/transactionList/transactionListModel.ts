/**
 * 交易流水的展示口径与请求体（#980 拆分时抽出）。
 *
 * 全是纯函数，但三处容易静默出错：
 * - 日汇总的正负号（卖出/分红/存入算收入，其余算支出）；
 * - 自定义时间范围用 `toISOString()` 取日期——它是 UTC，跨零点会差一天；
 * - 「近 30 天默认展开」的判定把当天算不算在内。
 */
import type { TransactionRecord } from "@/api/transactions";

export type TagType = "primary" | "success" | "warning" | "info" | "danger";

export interface TransactionFilters {
  type: string;
  assetType: string;
  status: string;
  timeRange: string;
  customDate: [Date, Date] | null;
  /**
   * 产品代码筛选（#2160）。与其它筛选项不同，它**多半不是用户手输的**，
   * 而是产品详情页「查看全部流水」用 `?symbol=` 带过来的——所以它必须
   * 在筛选栏显式回显且可清除，否则用户看到「共 3 条」会以为全站只有 3 条流水。
   */
  symbol: string;
}

export function defaultFilters(): TransactionFilters {
  return {
    type: "",
    assetType: "",
    status: "",
    timeRange: "",
    customDate: null,
    symbol: ""
  };
}

export const TXN_VIEW_OPTIONS = [
  { label: "表格", value: "table" },
  { label: "时间线", value: "timeline" }
];

/** 列表请求参数：空筛选项一律不下发（后端把空串当「筛空」，与「不筛」不同） */
export function buildTransactionParams(
  filters: TransactionFilters,
  page: number,
  pageSize: number
): Record<string, any> {
  const params: any = { page, per_page: pageSize };
  if (filters.type) params.type = filters.type;
  if (filters.assetType) params.asset_type = filters.assetType;
  if (filters.status) params.status = filters.status;
  if (filters.timeRange) params.time_range = filters.timeRange;
  // #2160：symbol 预筛（后端经 symbol_scope 两步法匹配流水快照的真实写法）
  if (filters.symbol) params.symbol = filters.symbol;
  if (filters.customDate) {
    const [start, end] = filters.customDate;
    params.start_date = start.toISOString().slice(0, 10);
    params.end_date = end.toISOString().slice(0, 10);
  }
  return params;
}

/** 按交易日分组（Map 保持插入顺序，等价于原对象字面量的 key 顺序） */
export function groupByDate(
  list: TransactionRecord[]
): Record<string, TransactionRecord[]> {
  const group: Record<string, TransactionRecord[]> = {};
  list.forEach(item => {
    const date = item.trade_date;
    if (!group[date]) group[date] = [];
    group[date].push(item);
  });
  return group;
}

/** 每日收支汇总：卖出 / 分红 / 存入为流入，其余为流出 */
export function dayBalanceOf(
  groups: Record<string, TransactionRecord[]>
): Record<string, number> {
  const balance: Record<string, number> = {};
  Object.entries(groups).forEach(([date, list]) => {
    let sum = 0;
    list.forEach(txn => {
      const val = Number(txn.amount);
      if (
        txn.type === "sell" ||
        txn.type === "dividend" ||
        txn.type === "deposit"
      )
        sum += val;
      else sum -= val;
    });
    balance[date] = sum;
  });
  return balance;
}

/**
 * 判断日期是否在 30 天内（含第 30 天）。
 *
 * `now` 可注入是为了让「同一批日期用同一基准」——`recentDatesOf` 会把同一个 `now`
 * 传给每一条；因此这里先复制再减 30 天，不能改调用方传进来的 Date。
 */
export function isDateInLast30Days(dateStr: string, now: Date = new Date()) {
  const target = new Date(dateStr);
  const past = new Date(now.getTime());
  past.setDate(past.getDate() - 30);
  return target >= past;
}

/** 默认展开的分组：最近 30 天内的日期 */
export function recentDatesOf(
  groups: Record<string, TransactionRecord[]>,
  now: Date = new Date()
): string[] {
  return Object.keys(groups).filter(date => isDateInLast30Days(date, now));
}

export function timelineIcon(type: string): string {
  const map: Record<string, string> = {
    buy: "ep:arrow-down",
    sell: "ep:arrow-up",
    dividend: "ep:present",
    deposit: "ep:wallet",
    withdraw: "ep:money"
  };
  return map[type] || "ep:arrow-down";
}

export function timelineDotClass(type: string): string {
  const map: Record<string, string> = {
    buy: "dot-buy",
    sell: "dot-sell",
    dividend: "dot-dividend",
    deposit: "dot-deposit",
    withdraw: "dot-withdraw"
  };
  return map[type] || "dot-default";
}

/** 时间线里的「带符号金额」：流入为正、流出为负 */
export function signedAmount(txn: TransactionRecord): number {
  return txn.type === "sell" ||
    txn.type === "dividend" ||
    txn.type === "deposit"
    ? Number(txn.amount) || 0
    : -(Number(txn.amount) || 0);
}

export function typeTag(type: string): TagType {
  const map: Record<string, TagType> = {
    buy: "success",
    sell: "danger",
    dividend: "warning",
    deposit: "primary",
    withdraw: "info"
  };
  return map[type] || "primary";
}

export function statusTag(status: string): TagType {
  const map: Record<string, TagType> = {
    success: "success",
    failed: "danger",
    cancelled: "info",
    pending: "warning"
  };
  return map[status] || "primary";
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    success: "成功",
    failed: "失败",
    cancelled: "已撤单",
    pending: "可撤单"
  };
  return map[status] || status;
}
