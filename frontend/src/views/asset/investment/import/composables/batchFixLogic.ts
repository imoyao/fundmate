/**
 * 批量修正的纯逻辑层（#1792）。
 *
 * 修正形态判定（#783 §4 阈值规则）与撤销快照都是**无 Vue 依赖**的纯函数，
 * 以便 vitest 单测直接覆盖（验收：≤10 / >10 阈值切换、撤销回滚语义）。
 */

/** 修正面板的四个分区（与摘要面板 fixBreakdown 的四桶同键） */
export type FixSectionKey =
  "error" | "missingCode" | "missingQtyPrice" | "mismatch";

/**
 * 修正形态（#783 §4）：
 * - none：没有问题行
 * - single：逐条修正（卡片式单条表单）
 * - batch：分类批量修正（四分区）
 * - table：面板内无可操作项，引导去完整表格手动处理 + 提供跳过（§4 第 4 条）
 */
export type FixMode = "none" | "single" | "batch" | "table";

/** §4 阈值：问题行 ≤ 10 条启用逐条修正 */
export const SINGLE_FIX_THRESHOLD = 10;

/**
 * 各分区是否支持分类批量操作。
 * 解析错误（error）结构性不可批量——面板内改不了行数据，只能逐条跳过或去完整表格处理。
 */
export const SECTION_BATCHABLE: Record<FixSectionKey, boolean> = {
  error: false,
  missingCode: true,
  missingQtyPrice: true,
  mismatch: true
};

export type SectionCounts = Record<FixSectionKey, number>;

/**
 * §4 修正模式自动判断（#1792 要做的事 4），按以下优先级：
 *
 * 1. 无问题行 → none；
 * 2. 全部问题行同属**一个可批量分区** → batch（§4 第 3 条：同类型且支持批量的固定走
 *    分类批量，即使 ≤ 10 条）；
 * 3. 问题行 > 10 → batch（§4 第 2 条）；此时若混有不可批量的解析错误，由批量面板内的
 *    提示条承接 §4 第 4 条（引导去完整表格 + 跳过）。纯错误行（无可批量分区）→ table；
 * 4. ≤ 10 且存在可批量分区 → single（§4 第 1 条：卡片式单条表单，混合类型也走卡片）；
 * 5. ≤ 10 且全部是解析错误 → table（卡片里只有「跳过」按钮没有修正意义，直接引导 + 跳过）。
 */
export function classifyFixMode(counts: SectionCounts): FixMode {
  const active = (Object.keys(counts) as FixSectionKey[]).filter(
    k => counts[k] > 0
  );
  if (active.length === 0) return "none";

  const hasBatchable = active.some(k => SECTION_BATCHABLE[k]);
  if (active.length === 1 && SECTION_BATCHABLE[active[0]]) return "batch";

  const total = active.reduce((sum, k) => sum + counts[k], 0);
  if (total > SINGLE_FIX_THRESHOLD) return hasBatchable ? "batch" : "table";
  return hasBatchable ? "single" : "table";
}

/**
 * 撤销快照覆盖的行字段（统一清单：多存无害，恢复语义一致）。
 * 覆盖各批量操作的写点：填码 / 自动填充数量价格 / 修正金额 / 净值推算 / 配置目标转换。
 */
export const UNDO_FIELDS = [
  "symbol",
  "name",
  "type",
  "quantity",
  "price",
  "amount",
  "allocation",
  "is_calculated",
  "_dataMissing",
  "_autoFilled"
] as const;

export interface RowSnapshot {
  key: string;
  before: Record<string, unknown>;
}

/** 撤销栈条目：字段快照 + 操作前的选择集（跳过类操作只动选择） */
export interface FixUndoEntry {
  scope: "code" | "fill" | "amount" | "repo" | "skip" | "batch";
  label: string;
  rows: RowSnapshot[];
  beforeSelection: string[];
}

/** 撤销栈上限（§5 只要求至少撤销一层；留栈便于连撤多步，封顶防内存膨胀） */
export const UNDO_STACK_LIMIT = 20;

/** 变更前给行字段拍照（默认走 UNDO_FIELDS 清单） */
export function snapshotRows(
  rows: any[],
  fields: readonly string[] = UNDO_FIELDS
): RowSnapshot[] {
  return rows.map(row => {
    const before: Record<string, unknown> = {};
    fields.forEach(f => {
      before[f] = row[f];
    });
    return { key: row._rowKey, before };
  });
}

/** 把快照写回数据（按 _rowKey 定位；行已被移除则跳过） */
export function restoreRows(data: any[], snapshots: RowSnapshot[]): void {
  const byKey = new Map<any, any>(data.map(row => [row._rowKey, row]));
  snapshots.forEach(snap => {
    const row = byKey.get(snap.key);
    if (!row) return;
    Object.entries(snap.before).forEach(([field, value]) => {
      row[field] = value;
    });
  });
}
