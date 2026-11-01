/**
 * 交易流水的展示口径与请求体（#980 拆分时抽出）。
 *
 * 全是纯函数，但四处容易静默出错：
 * - 月汇总的正负号（卖出/分红/存入算流入，其余算流出）；
 * - 自定义时间范围用 `toISOString()` 取日期——它是 UTC，跨零点会差一天；
 * - 「默认展开最近两个月」数的是**有记录的**月，不是日历月（否则空窗期会一片折叠）；
 * - 月归属用「交易日优先、确认日兜底」，与表格列同一口径。
 */
import type { TransactionRecord } from "@/api/transactions";
import { txnStatusLabel, txnStatusTag } from "@/utils/transactionStatus";

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

/**
 * 一级筛选：交易类型（分段控制器）。
 *
 * 为什么升成一级分段而不是继续当第 4 个下拉：类型是筛流水时唯一**高频且互斥**的维度
 * （「我只看卖出」），下拉要点两下才看到选项；资产 / 状态 / 时间都是低频条件，
 * 留在二级下拉里。分层的判据是使用频率，不是信息多寡。
 */
export const TXN_TYPE_OPTIONS: { label: string; value: string }[] = [
  { label: "全部", value: "" },
  { label: "买入", value: "buy" },
  { label: "卖出", value: "sell" },
  { label: "分红", value: "dividend" },
  { label: "存入", value: "deposit" },
  { label: "取出", value: "withdraw" }
];

/** 月内合计（月头展示）：笔数 / 买入 / 卖出 / 净额 */
export interface MonthSummary {
  count: number;
  /** `Σ amount WHERE type='buy'`（成交额，不含手续费） */
  buy: number;
  /** `Σ amount WHERE type='sell'` */
  sell: number;
  /** `Σ signedAmount`：流入为正、流出为负 */
  net: number;
}

/** 一个月份的流水分组（月头 + 该月全部记录 + 月内合计） */
export interface MonthGroup {
  /** `YYYY-MM`；`""` = 交易日与确认日都缺失（沉底） */
  month: string;
  /** 展示文案（`2026 年 10 月` / `未标注日期`） */
  label: string;
  records: TransactionRecord[];
  summary: MonthSummary;
}

/** 一条流水所属月份：交易日优先、确认日兜底（与表格列同口径） */
export function monthOf(record: TransactionRecord): string {
  const day = record.trade_date || record.confirm_date || "";
  return day.slice(0, 7);
}

export function monthLabel(month: string): string {
  if (!month) return "未标注日期";
  const [year, mon] = month.split("-");
  return `${year} 年 ${Number(mon)} 月`;
}

/**
 * 筛选参数（不含分页）：列表与**汇总条**共用同一份映射。
 *
 * 为什么抽出来：汇总条必须跟随同一组筛选，否则「列表 3 条、汇总按全量算」——
 * 这种不一致不会报错，只会让用户拿汇总条去核列表时永远差一截。
 */
export function buildFilterParams(
  filters: TransactionFilters
): Record<string, any> {
  const params: any = {};
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

/** 列表请求参数：空筛选项一律不下发（后端把空串当「筛空」，与「不筛」不同） */
export function buildTransactionParams(
  filters: TransactionFilters,
  page: number,
  pageSize: number
): Record<string, any> {
  return { page, per_page: pageSize, ...buildFilterParams(filters) };
}

const TIME_RANGE_LABELS: Record<string, string> = {
  "1m": "近一个月",
  "3m": "近三个月",
  "6m": "近半年",
  "1y": "近一年"
};

/**
 * 汇总条的时间范围文案（「近一年 · 买入 …」里那个「近一年」）。
 *
 * 为什么必须显示：同一个「买入 ¥86,320」在「全部时间」和「近一个月」下是两个完全
 * 不同的判断，不写范围时读者会默认它等于全部历史。symbol 预筛也要带上——从产品详情页
 * 进来时汇总只覆盖那一个产品，不标出来的话看起来像全家庭数据。
 */
export function summaryRangeLabel(filters: TransactionFilters): string {
  const parts: string[] = [];
  if (filters.symbol) parts.push(filters.symbol);
  if (filters.timeRange === "custom") {
    parts.push(
      filters.customDate
        ? `${formatLocalDate(filters.customDate[0])} 至 ${formatLocalDate(
            filters.customDate[1]
          )}`
        : "自定义时段"
    );
  } else {
    parts.push(TIME_RANGE_LABELS[filters.timeRange] ?? "全部时间");
  }
  return parts.join(" · ");
}

/** 本地日期（`YYYY-MM-DD`）：`toISOString()` 是 UTC，东八区会差一天 */
function formatLocalDate(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

/**
 * 按**月**分组（设计 §五：桌面上一天只有一两笔，按日分组就是一屏空折叠头）。
 *
 * 日期口径与表格列一致：**交易日优先、确认日兜底**。只认 `trade_date` 时，只有确认日的
 * 行会落进 `undefined` 这个 key（时间线里出现一个没名字的分组），而同一批流水在表格里
 * 显示的是确认日——同一页两套口径。
 *
 * 排不出日期的行进 `""` 桶（「未标注日期」），且**排在最后**：它没有时间位置，
 * 混在月份之间会让「最近的流水」看起来乱序。
 */
export function groupByMonth(list: TransactionRecord[]): MonthGroup[] {
  const buckets = new Map<string, TransactionRecord[]>();
  list.forEach(item => {
    const month = monthOf(item);
    const bucket = buckets.get(month);
    if (bucket) bucket.push(item);
    else buckets.set(month, [item]);
  });

  const groups: MonthGroup[] = [];
  buckets.forEach((records, month) => {
    groups.push({
      month,
      label: monthLabel(month),
      records,
      summary: monthSummaryOf(records)
    });
  });

  // `""`（未标注日期）沉底；其余保持插入顺序（后端已按有效交易日倒序返回）
  return groups.sort((a, b) => {
    if (a.month === b.month) return 0;
    if (!a.month) return 1;
    if (!b.month) return -1;
    return 0;
  });
}

/** 月内合计：笔数 / 买入 / 卖出 / 净额 */
export function monthSummaryOf(records: TransactionRecord[]): MonthSummary {
  let buy = 0;
  let sell = 0;
  let net = 0;
  records.forEach(txn => {
    const amount = Number(txn.amount) || 0;
    if (txn.type === "buy") buy += amount;
    else if (txn.type === "sell") sell += amount;
    net += signedAmount(txn);
  });
  return { count: records.length, buy, sell, net };
}

/**
 * 默认展开的月份：最近 `count` 个**有记录的**月。
 *
 * 为什么按「有记录的月」数而不是「日历上最近两个月」：用户三个月没交易时，
 * 后者会一个都不展开，页面看起来像空的——而列表明明有数据。
 */
export function recentMonthsOf(groups: MonthGroup[], count = 2): string[] {
  return groups
    .filter(group => Boolean(group.month))
    .slice(0, count)
    .map(group => group.month);
}

/**
 * 展开态决策：决定「加载更多」（追加）还是「重置筛选」（整替换）后，哪几个月该展开。
 *
 * 这是 v1.3 修的一个**感知 bug**：原实现在 `watch(transactions)` 里无脑
 * `recentMonthsOf` 重算，于是「加载更多」也会把你**手动展开**的旧月份重新折叠——
 * 用户滑到底触发加载，抬头发现刚才展开的那个月没了，自然以为「数据没更新」。
 *
 * 规则：
 * - 首次进入（prevOpen 为空）或**重置**（换筛选 / 清筛选）→ 回到「最近两月」默认；
 * - **追加**（加载更多）→ 保留用户当前的展开 / 折叠状态，不碰它。
 *
 * `isReset` 由组件用「首条 id 是否变化 / 长度是否变短」判定，这里只消费结论。
 */
export function resolveOpenMonths(
  prevOpen: string[],
  groups: MonthGroup[],
  isReset: boolean
): string[] {
  if (isReset || prevOpen.length === 0) {
    return recentMonthsOf(groups, 2);
  }
  return prevOpen;
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

/**
 * 状态标签 / 配色：真源已上收到 `@/utils/transactionStatus`（#2712）——共享表格组件
 * `components/TransactionTable` 也要显示状态列，不能反过来 import 页面 model。
 * 这里保留同名导出，页面与既有单测不必改 import。
 */
export const statusLabel = txnStatusLabel;

export function statusTag(status: string): TagType {
  return txnStatusTag(status);
}
