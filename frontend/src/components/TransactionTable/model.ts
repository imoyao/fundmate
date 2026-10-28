/**
 * 交易流水表的**行结构与展示口径**（#2712）。
 *
 * 从 `index.vue` 拆出（`scripts/check_vue_size.mjs` 的 400 行门禁）：数据结构、
 * 日期口径、排序键、类型着色都属于「口径」，与 el-table 骨架无关；抽成纯 TS 还能被
 * 单测直接覆盖，不必挂载组件。
 */
import { formatDate } from "@/utils/date";

/**
 * 交易行（三端容器的最大公约数）。容器负责把各自接口返回映射到本结构：
 * - 详情页 / 资产流水页 `TransactionRecord`：字段同名，可直接传；
 * - 账本 Tab `LedgerTxnRow` / 持仓抽屉行：`txn_type` → `type`。
 */
export interface TransactionRow {
  id: number;
  /** 交易类型：buy/sell/dividend/dividend_reinvest/deposit/withdraw/split */
  type: string;
  trade_date?: string | null;
  confirm_date?: string | null;
  price?: number | null;
  quantity?: number | null;
  amount?: number | null;
  fee?: number | null;
  asset_type?: string | null;
  position_name?: string;
  symbol?: string;
  account_name?: string;
  /** 账户 ID：非空时账户名可点击跳转账户详情（/asset/ledgers/:id）；
      空 = 未归档（如探市录入），保持纯文本——那里没有落点，链过去是坏的 */
  ledger_id?: number | null;
  /** 关联持仓 id；`null` = 持仓已删（行仍保留），资产列据此打「已删除」标记 */
  position_id?: number | null;
  /** 交易状态（success / failed / cancelled / pending）：资产流水页的状态列 */
  status?: string | null;
  /** 备注：资产流水页的备注列 */
  notes?: string | null;
}

/**
 * 日期口径：交易日优先、确认日兜底，**一律格式化成 `YYYY-MM-DD`**。
 *
 * 为什么不能直接印接口值（#2712）：`Transaction.trade_date` 是 DateTime，账本 / 持仓
 * 两个出口曾经 `.isoformat()`，屏幕上就出现 `2026-06-03T00:00:00`；而资产流水页那份
 * 接口早就 `strftime` 过，同一批流水在两张表里长得不一样。后端已统一（`iso_date_only`），
 * 这里再兜一层——格式化是展示层的事，不能指望每个出口都记得。
 */
export function formatTradeDate(row: TransactionRow): string {
  return formatDate(row.trade_date || row.confirm_date || "");
}

/**
 * 客户端排序口径：与后端 `COALESCE(trade_date, confirm_date) DESC, id DESC` 对齐。
 *
 * el-table 默认拿列的 `prop`（`trade_date`）原始值比较，**只有确认日的行**会被当成空值
 * 沉到末尾，与后端列表顺序相反；用户点开账本 Tab 翻页时看到的就是「顺序对不上」。
 * `sort-method` 收到整行，所以这里比较「有效交易日」，与展示列同一口径。
 * 值都是 `YYYY-MM-DD`，字典序即时间序，不必转 Date。
 */
export function compareTradeDate(a: TransactionRow, b: TransactionRow): number {
  const left = a.trade_date || a.confirm_date || "";
  const right = b.trade_date || b.confirm_date || "";
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

/** 类型着色：买入/存入 = 涨红，卖出/取出 = 跌绿，分红等中性 = info */
export function typeClass(type: string): string {
  if (type === "buy" || type === "deposit") return "txn-type--rise";
  if (type === "sell" || type === "withdraw") return "txn-type--fall";
  return "txn-type--info";
}
