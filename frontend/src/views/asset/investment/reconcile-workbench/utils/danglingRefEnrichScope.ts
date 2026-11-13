/**
 * 「补全信息」弹窗对**一组**流水的静态缺口判断（对账工作台域 F，2026-11-13）。
 *
 * 为什么需要它：分组键是 `(ledger_id, symbol or '')`（后端
 * `dangling_ref_service.py:404-407`），组内 symbol 必然相同 ⇒ 对有代码的组，
 * 「标的代码」输入框永远补 0 条，用户填了也不生效，页面却照旧给一个空输入框
 * （owner 2026-11-12 截图：`SZ128021 → SZ128021`，统计行同时说「无需改动 7 条」）。
 *
 * 本文件只做两件纯事，都不问后端：
 * 1. 从组内流水算出「这组缺什么」——`DanglingRefTransaction` 每条都带
 *    symbol / trade_date，前端本就知道答案，不需要让用户对着空表单猜；
 * 2. 从预览的 changes 里挑出**真正会变**的行——后端把未变化的行也一并返回
 *    （`_plan_enrichment` 对每一条都给 before/after），前端无条件列出来就会被
 *    读成「7 条变更」。
 *
 * 判据不 import API 类型（与 `danglingRefRemediationGuard` 同一取舍）：只吃最小
 * 形状，单测在 node 环境独立跑，不拉 axios / 环境变量。
 */

/** 组内一条流水的最小形状：判断缺口只需要这两个字段 */
export interface EnrichTxnLike {
  symbol?: string | null;
  trade_date?: string | null;
}

export interface GroupNeeds {
  txnCount: number;
  /** 缺标的代码的条数（null / 空串 / 全空白都算缺） */
  needSymbol: number;
  /** 缺交易日期的条数（null / 空串都算缺） */
  needDate: number;
  /** 组内已有的标的代码（首个非空值，去首尾空白）；全组都没代码时为 null */
  symbol: string | null;
  /** 可补字段数为 0：此时不接受提交，也不该渲染输入框 */
  complete: boolean;
}

function isBlank(value: string | null | undefined): boolean {
  return !value || !value.trim();
}

/**
 * 算出一组流水还缺什么。
 *
 * 空数组视为「没有可判断的对象」，`complete` 恒为 false —— 空组由 guard 的
 * `txnCount === 0` 先挡住并说「该组没有可处理的交易」，不该在这里冒充
 * 「都已填写」。
 */
export function inspectGroupNeeds(txns: readonly EnrichTxnLike[]): GroupNeeds {
  let needSymbol = 0;
  let needDate = 0;
  let symbol: string | null = null;
  for (const txn of txns) {
    if (isBlank(txn.symbol)) {
      needSymbol += 1;
    } else if (symbol === null) {
      symbol = (txn.symbol as string).trim();
    }
    if (!txn.trade_date) needDate += 1;
  }
  return {
    txnCount: txns.length,
    needSymbol,
    needDate,
    symbol,
    complete: txns.length > 0 && needSymbol === 0 && needDate === 0
  };
}

/**
 * 这组流水的「下一步真正该做什么」。
 *
 * 为什么需要它：域 F 的不可回补组有两种完全不同的成因——
 * ① **缺标的代码**：能靠补字段解决；② **代码齐了、但没有同标的的现存持仓行**：
 * 补字段一点用都没有，真正要做的是「按流水重建持仓」。
 *
 * 此前界面把两种都翻成「补全信息」，于是 ② 的用户被送进一个「没有可补的字段」的
 * 死弹窗，弹窗让他「去补建持仓」，而唯一的入口在另一个卡片上（2026-11-13 owner 截图：
 * 两边来回踢皮球）。判据在这里收成一条，列表动作 / 分组卡 / 弹窗都读同一个结论。
 *
 * 四种状态，每一种在界面上都必须有出口：
 * - `reattach`：已有可挂回的现存持仓 → 回补关联
 * - `fill`：缺标的代码 → 补全信息
 * - `rebuild`：代码齐全但没有持仓行 → 按流水重建持仓
 * - `empty`：空组（后端不该给出，防御用）→ 不给动作
 */
export type DanglingNextStep = "reattach" | "fill" | "rebuild" | "empty";

export interface NextStepInput {
  /** 组内已有的标的代码（`inspectGroupNeeds().symbol`） */
  symbol: string | null;
  /** 后端判据：同账本存在同标的的现存持仓行（`DanglingRefGroup.fixable`） */
  fixable: boolean;
  txnCount: number;
}

export function danglingNextStep(input: NextStepInput): DanglingNextStep {
  if (input.txnCount === 0) return "empty";
  if (input.fixable) return "reattach";
  return isBlank(input.symbol) ? "fill" : "rebuild";
}

/** 预览 changes 一行的最小形状（对应 `DanglingRefEnrichPreview.changes`） */
export interface EnrichChangeLike {
  symbol_before?: string | null;
  symbol_after?: string | null;
  trade_date_before?: string | null;
  trade_date_after?: string | null;
}

function normalize(value: string | null | undefined): string {
  return (value ?? "").trim();
}

/**
 * 这一行是否真的会被写。null / 空串 / 纯空白一律等价 —— 后端「不填」时
 * after 原样回填 before，两者字符串相等；只在语义相同、写法不同时才需要归一化。
 */
export function changeActuallyWrites(row: EnrichChangeLike): boolean {
  return (
    normalize(row.symbol_before) !== normalize(row.symbol_after) ||
    normalize(row.trade_date_before) !== normalize(row.trade_date_after)
  );
}

/** 预览里只保留真正会变的行（保持后端顺序，不排序） */
export function pickChangedRows<T extends EnrichChangeLike>(
  rows: readonly T[]
): T[] {
  return rows.filter(changeActuallyWrites);
}
