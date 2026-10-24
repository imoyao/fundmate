/**
 * 批量修正面板的展示口径（#980 拆分时抽出）。
 *
 * 这些都是纯函数，但每一处都曾散在模板表达式里：
 * - `mismatchDiff` 的文案会出现在卡片正文，改一个标点就是 UI 变更；
 * - `modeLabel` 的三态与「table 模式」的引导文案绑定，漏一个 case 就会显示空标签；
 * - `repoRevertable` 决定【撤销】是否可点（只回退解析期自动置的「活钱」，手动设过的不动）。
 */
import { ALLOCATION_OPTIONS } from "@/constants";
import type { FixMode, FixSectionKey } from "../composables/batchFixLogic";

export const SECTION_LABELS: Record<FixSectionKey, string> = {
  error: "解析错误",
  missingCode: "代码未匹配",
  missingQtyPrice: "单价/数量缺失",
  mismatch: "数据不一致"
};

export const AUTO_FIELD_LABELS: Record<string, string> = {
  quantity: "数量",
  price: "价格"
};

/** 顶部形态标签文案；none / 未知一律空串（`v-if` 据此不渲染） */
export function modeLabelOf(mode: FixMode | string): string {
  switch (mode) {
    case "single":
      return "逐条修正模式";
    case "batch":
      return "分类批量修正模式";
    case "table":
      return "请到完整表格处理";
    default:
      return "";
  }
}

/** 逐条模式的标题作用域：`all` 是全量，其余取分区名 */
export function singleScopeLabelOf(scope: "all" | FixSectionKey): string {
  return scope === "all" ? "全部问题" : SECTION_LABELS[scope];
}

/**
 * mismatch 卡片的差额说明（#783 §5）。
 *
 * 刻意保留 `Number()` 的 NaN 行为：字段缺失时原文案会显示 `NaN`，
 * 改成「—」属于新的展示决策，应单独立项，不混在拆分里。
 */
export function mismatchDiffText(row: any): string {
  const qty = Number(row.quantity),
    prc = Number(row.price),
    amt = Number(row.amount);
  const calc = qty * prc;
  const diff = calc - amt;
  const sign = diff > 0 ? "+" : "";
  return `数量×价格 = ${calc.toFixed(2)}，当前金额 ${amt.toFixed(2)}，差额 ${sign}${diff.toFixed(2)}`;
}

/** 逐条卡片的表单草稿：按 `_rowKey` 懒建，点「应用」才写回行数据 */
export interface CardDraft {
  quantity: string;
  price: string;
  code: string;
}

/** 已填充字段的人话清单（`_autoFilled` 里存的是 quantity / price 这类键名） */ export function filledFieldsLabel(
  row: any
): string {
  return (row._autoFilled || [])
    .map((f: string) => AUTO_FIELD_LABELS[f] || f)
    .join("、");
}

/** 可程序化自动处理的条目：mismatch 金额重算 + 基金净值抓取 + 已推算确认 */
export function autoFixableCountOf(
  mismatchCount: number,
  calculatedCount: number,
  hasFundRecordsForNav: boolean,
  fundRecordsCount: number
): number {
  return (
    mismatchCount +
    calculatedCount +
    (hasFundRecordsForNav ? fundRecordsCount : 0)
  );
}

/** 逆回购分区【撤销】的可撤目标：解析期自动置的「活钱」，手动设置过的不动 */
export function repoRevertableOf(rows: any[]): any[] {
  return rows.filter(
    row => row.allocation === "liquid" && !row._allocationManual
  );
}

/** 配置目标的展示名；未知值原样回显（不吞掉，便于发现脏数据） */
export function allocationLabelOf(value: string): string {
  return ALLOCATION_OPTIONS.find(o => o.value === value)?.label || value;
}
