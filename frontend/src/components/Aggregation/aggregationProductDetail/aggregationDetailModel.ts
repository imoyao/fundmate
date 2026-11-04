/**
 * 产品详情抽屉的纯函数层（#980 拆分自 AggregationProductDetail.vue）。
 *
 * 只放「输入什么、输出什么」的换算与文案，不碰响应式：
 * - 份额 / 金额单位换算（后端 quantity 为份×10000、金额为分）
 * - 净值与日期的展示口径
 * - 分摊预览算法（**必须与后端 value_allocation_service 同算法**，否则预览与落库不一致）
 * - 后端资金进出提示的文案拼装
 */

import type { AggregationSource } from "@/api/ledger";
import { formatPrice, PRICE_PLACEHOLDER } from "@/utils/pricePrecision";

/** 份额最小单位：1 份 = 10000（与 Position.quantity 一致） */
export const SHARE_UNIT = 10000;
/** 金额最小单位：1 元 = 100 分 */
export const CENT_UNIT = 100;

/** 份额最小单位 → 可读份额 */
export function shareFromRaw(quantity: number | null | undefined): number {
  return (quantity || 0) / SHARE_UNIT;
}

/** 分 → 元 */
export function yuanFromCents(cents: number | null | undefined): number {
  return (cents || 0) / CENT_UNIT;
}

/** 参考净值展示：走 `pricePrecision` 契约（基金口径 4 位），非有限值给 `--` */
export function navText(nav: number | null | undefined): string {
  // 不在这里另写 `toFixed(4)`——位数是数据，收口在 utils/pricePrecision.ts。
  // 契约的占位符是「—」，本抽屉历史上用「--」，映射回去以免改动观感。
  const text = formatPrice(nav, "fund");
  return text === PRICE_PLACEHOLDER ? "--" : text;
}

/** YYYY-MM-DD → MM-DD；非标准格式原样返回；空值 `--` */
export function fmtShortDate(d: string | null | undefined): string {
  if (!d) return "--";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[2]}-${m[3]}` : d;
}

/** 有来源持仓才允许改总价（后端按各来源既有市值占比分摊） */
export function canAllocate(sources: AggregationSource[]): boolean {
  return sources.length > 0;
}

/** 各账户既有市值合计（分），即分摊分母 */
export function sourceWeightCents(sources: AggregationSource[]): number {
  return sources.reduce((sum, s) => sum + (s.market_value_cents || 0), 0);
}

/** 分摊预览行 */
export interface AllocationPreviewRow {
  /** 行 key：ledger_id + 下标（同一账本可能因分红方式拆成多条） */
  key: string;
  /** 展示名：账本名 → 机构名 → 兜底 */
  name: string;
  /** 占比文案，如 `62.5%` */
  ratioText: string;
  /** 分摊金额（元） */
  allocatedYuan: number;
}

/** 单条来源的展示名：账本名优先，其次销售机构，都空则兜底 */
export function sourceDisplayName(src: AggregationSource): string {
  return src.ledger_name || src.institution_name || "未关联账户";
}

/**
 * 分摊预览。
 *
 * **与后端 value_allocation_service 同一算法**：按既有市值占比 → 整数分四舍五入
 * → 尾差归占比最大一笔（并列时取第一条）。因此预览值之和严格等于输入总价，
 * 与保存后的真实落库结果一致。
 *
 * 分母为 0（各账户市值全为 0）或输入非正数时返回空数组——此时不渲染预览，
 * 由保存处拦下并提示用户先录入市值。
 */
export function buildAllocationPreview(
  sources: AggregationSource[],
  inputTotal: number | null | undefined
): AllocationPreviewRow[] {
  const total = Number(inputTotal);
  const weight = sourceWeightCents(sources);
  if (!weight || !Number.isFinite(total) || total <= 0) return [];

  const totalCents = Math.round(total * CENT_UNIT);
  const weights = sources.map(s => s.market_value_cents || 0);
  const allocs = weights.map(w => Math.round((w * totalCents) / weight));

  const diff = totalCents - allocs.reduce((a, b) => a + b, 0);
  if (diff !== 0) {
    allocs[weights.indexOf(Math.max(...weights))] += diff;
  }

  return sources.map((s, i) => ({
    key: `${s.ledger_id}-${i}`,
    name: sourceDisplayName(s),
    ratioText: `${((allocs[i] / totalCents) * 100).toFixed(1)}%`,
    allocatedYuan: allocs[i] / CENT_UNIT
  }));
}

/** 预览合计（元），恒等于输入总价（尾差已归集） */
export function previewSumYuan(rows: AllocationPreviewRow[]): number {
  return rows.reduce((sum, r) => sum + r.allocatedYuan, 0);
}

/**
 * 资金进出提示（#1217）：上次录入市值之后若发生过资金进出，
 * 「按既有市值占比」这一分摊基数已不能反映实际持有，
 * 提示用户在下一个开盘日更新其他存量持仓的总价。
 *
 * 后端没给 `next_trading_day`（或未检测到资金进出）时不给提示。
 */
export function cashFlowHintOf(
  data:
    | { cash_flow_detected?: boolean; next_trading_day?: string | null }
    | null
    | undefined
): string | null {
  return data?.cash_flow_detected && data?.next_trading_day
    ? `本次分摊前该账户有资金进出记录，建议在下一个开盘日（${data.next_trading_day}）更新其他存量持仓的总价。`
    : null;
}

/**
 * 分渠道明细右上角的角标：优先分红方式，其次基金管理人。
 * 两者都空时不渲染（由调用方 `v-if="src.fund_manager"` 控制）。
 */
export function dividendOrManagerText(src: AggregationSource): string {
  return src.dividend_preference || src.fund_manager || "";
}
