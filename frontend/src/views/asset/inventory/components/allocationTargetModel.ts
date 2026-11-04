import type {
  AllocationData,
  AllocationTargetInput
} from "@/api/strategyEngine";

/**
 * 目标配比卡的派生口径（#980 拆分自 `AllocationTargetCard.vue`）。
 *
 * 只读态展示后端算好的事实（当前 / 目标 / 偏离 / 是否越线），编辑态把用户输入
 * 覆盖到「目标」一列；两种形态走同一个 `buildVisibleRows`，避免两套模板漂移。
 */

/** 编辑行：target 为 null 表示「这一行不设目标」，保存时会被剔除 */
export interface EditRow {
  symbol: string;
  name: string;
  target: number | null;
}

/** 表格一行（只读 / 编辑两态共用） */
export interface VisibleRow {
  symbol: string;
  name: string;
  weight_pct: number;
  target_pct: number | null;
  deviation_pct: number | null;
  breached: boolean;
  target: number | null;
}

/** 进入编辑态：把后端事实复制成本地可改的行 */
export function toEditRows(data: AllocationData | null): EditRow[] {
  return (data?.items ?? []).map(item => ({
    symbol: item.symbol,
    name: item.name || item.symbol,
    target: item.target_pct
  }));
}

/**
 * 每行展示所需：把编辑行的目标值合并回后端返回的事实行。
 *
 * 编辑态下「目标」以用户输入为准，但「当前 / 是否越线」仍用后端事实——
 * 越线是后端按已存目标算的，编辑中的 buffer 还没生效。
 */
export function buildVisibleRows(
  data: AllocationData | null,
  editing: boolean,
  rows: EditRow[]
): VisibleRow[] {
  const items = data?.items ?? [];
  if (!editing) {
    return items.map(item => ({
      symbol: item.symbol,
      name: item.name || item.symbol,
      weight_pct: item.weight_pct,
      target_pct: item.target_pct,
      deviation_pct: item.deviation_pct,
      breached: item.breached,
      target: item.target_pct
    }));
  }
  return rows.map(row => {
    const item = items.find(i => i.symbol === row.symbol);
    return {
      symbol: row.symbol,
      name: row.name,
      weight_pct: item?.weight_pct ?? 0,
      target_pct: row.target,
      deviation_pct:
        row.target === null ? null : (item?.weight_pct ?? 0) - row.target,
      breached: item?.breached ?? false,
      target: row.target
    };
  });
}

/** 编辑态顶部提示：目标总和（百分点，不强制 100） */
export function sumTargets(rows: EditRow[]): number {
  return rows.reduce((sum, row) => sum + (row.target ?? 0), 0);
}

/** 可添加的标的 = 当前持仓里还没出现在编辑行里的 */
export function buildAddableSymbols(
  data: AllocationData | null,
  rows: EditRow[]
): { symbol: string; name: string }[] {
  const taken = new Set(rows.map(row => row.symbol));
  return (data?.items ?? [])
    .filter(item => !taken.has(item.symbol))
    .map(item => ({ symbol: item.symbol, name: item.name || item.symbol }));
}

/**
 * 保存：只提交填了数字的那些行。
 *
 * 后端是**整体覆盖**语义——没提交就等于「这个标的没有目标」，
 * 所以留空的行不能带上 0（0% 是一个合法目标，会被当成真目标写进去）。
 */
export function buildSaveItems(rows: EditRow[]): AllocationTargetInput[] {
  return rows
    .filter(row => row.target !== null)
    .map(row => ({ symbol: row.symbol, target_weight: row.target as number }));
}

/**
 * 百分点展示：最多两位小数、去掉无意义的尾零。
 * 阈值「5」显示成「5」比「5.00」更像人话；占比 46.2 仍保留一位。
 */
export function formatPct(value: number | null | undefined): string {
  return String(Number((value ?? 0).toFixed(2)));
}

/** 偏离带正负号：正号要显式补出来，负数自带符号（且不得取绝对值） */
export function signedPct(value: number): string {
  return value > 0 ? `+${formatPct(value)}` : formatPct(value);
}
