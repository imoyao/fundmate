/**
 * 交易流水表的**行结构与展示口径**（#2712）。
 *
 * 从 `index.vue` 拆出（`scripts/check_vue_size.mjs` 的 400 行门禁）：数据结构、
 * 日期口径、排序键、类型着色都属于「口径」，与 el-table 骨架无关；抽成纯 TS 还能被
 * 单测直接覆盖，不必挂载组件。
 */
import type { TransactionDetail } from "@/api/transactions";
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
  /** 关联持仓 id；`null` = 无关联持仓（资金流水或历史孤儿流水） */
  position_id?: number | null;
  /**
   * 持仓状态（后端下发，`held` / `cleared` / `account`）。
   *
   * ⚠️ **不要退回「按 `position_id === null` 推断」**：那条判据在 #2343「清仓不删行」
   * 之后已经失效——已清仓的持仓行保留（`ownership_status='cleared'`），流水
   * `position_id` 依然有值，按 null 判会让「已清仓」胶囊几乎永不出现。
   * 判据的单一真相源在后端（`txn_name_resolver.resolve_transaction_position_states`）。
   */
  position_state?: string | null;
  /** 交易状态（success / failed / cancelled / pending）：资产流水页的状态列 */
  status?: string | null;
  /** 备注：资产流水页的备注列 */
  notes?: string | null;
}

/**
 * 持仓状态四态（含「字段缺失」）。
 *
 * 第四态 `unknown` 存在的理由与 #2786 的 `in_portfolio` 一样：**缺失不等于某个值**。
 * 旧缓存 / 未升级接口的行没有 `position_state`，此时既不能说「还持有」也不能说
 * 「已清仓」——按 `position_id` 猜出来的 `cleared` 在 #2343 之后几乎全是假阴性，
 * 猜 `held` 又会把历史孤儿流水说成「持仓还在」。只加一枚安静胶囊，宁可不显示。
 */
export type PositionState = "held" | "cleared" | "account" | "unknown";

const POSITION_STATES: readonly PositionState[] = [
  "held",
  "cleared",
  "account"
];

/** 持仓状态：读后端下发值；缺失 → `unknown`（不猜，见 `PositionState` 注释） */
export function positionStateOf(row: TransactionRow): PositionState {
  const raw = row.position_state;
  if (!raw) return "unknown";
  return POSITION_STATES.includes(raw as PositionState)
    ? (raw as PositionState)
    : "unknown";
}

/** 内部标识（`__CASH__` / `_CASH_` 等）：写进库里当占位，不该出现在界面上 */
export function isInternalSymbol(symbol?: string | null): boolean {
  return typeof symbol === "string" && symbol.startsWith("_");
}

/**
 * 资产代码位要不要显示、显示什么。
 *
 * 返回 `null` = 这一行没有可展示的代码，**代码位整段不渲染**（而不是印 `# --`）：
 * - 内部标识（`__CASH__` 等占位码）：写进库里是为了对齐字段，不该出现在界面上；
 * - 资金流水（存入 / 取出）：本来就没有代码，`# --` 只是把空缺画出来。
 *
 * 资金流水另由 `isAccountLevel` 给出「资金流水」这枚弱化文字，语义不靠代码位承担。
 */
export function assetCodeText(row: TransactionRow): string | null {
  if (isInternalSymbol(row.symbol)) return null;
  if (positionStateOf(row) === "account") return null;
  const code = (row.symbol ?? "").trim();
  return code || null;
}

/** 账户级流水（存入 / 取出）：没有持仓，名称旁标「资金流水」而不是「已清仓」 */
export function isAccountLevel(row: TransactionRow): boolean {
  return positionStateOf(row) === "account";
}

/** 状态列的视觉声量（设计 §三：成功是常态，常态不染色） */
export type StatusTone = "silent" | "danger" | "warning" | "outline";

/**
 * 状态 → 声量。**默认静默**，只有异常态才着色。
 *
 * 为什么不是直接复用 el-tag 的语义色：`success` 默认给绿底标签，一屏 20 行就是 20 枚
 * 绿色徽章，注意力会被从金额上拽走。这里把「常态」压到纯文字，异常态才配底色。
 */
export function statusTone(status?: string | null): StatusTone {
  if (status === "failed") return "danger";
  if (status === "pending") return "warning";
  if (status === "cancelled") return "outline";
  return "silent";
}

/** 已清仓胶囊的悬浮说明：胶囊只说「它清仓了」，为什么保留要在这里讲清 */
export const CLEARED_BADGE_TITLE = "持仓已清仓或被合并，流水与金额保留";

/**
 * 展开详情的三态（容器持有）。
 *
 * 三态分开的理由：`data === null` 既可能是「还没取」，也可能是「取失败了」——
 * 合成一个 `detail | null` 会让面板在失败时永远显示「正在读取」，用户以为卡住了。
 */
export interface TransactionDetailState {
  loading: boolean;
  data: TransactionDetail | null;
  /** 取失败的原因（已转成界面可读的一句话）；成功为 `null` */
  error: string | null;
}

/** 类型着色：买入/存入 = 涨红，卖出/取出 = 跌绿，分红等中性 = info */
export function typeClass(type: string): string {
  if (type === "buy" || type === "deposit") return "txn-type--rise";
  if (type === "sell" || type === "withdraw") return "txn-type--fall";
  return "txn-type--info";
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
