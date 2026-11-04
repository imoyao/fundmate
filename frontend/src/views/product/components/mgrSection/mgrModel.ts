import type { ManagerProfileResult } from "@/api/products";

/**
 * 「基金经理」区块的展示判定（#980 拆分，纯函数）。
 *
 * 原先这些判断写在 computed 里：改一个字段名、或把「≥ 0 算涨」写成「> 0」，
 * 都不会有任何测试报警。抽出来才能钉住。
 */

/**
 * 最佳回报的涨跌色 class。
 *
 * **必须由前端按符号决定**：转换层刻意不返回颜色（服务层给颜色会导致色板分裂成
 * 两套），涨跌语义属于 design.md 的视觉层。涨红跌绿用 --color-rise / --color-fall。
 *
 * `0` 归为涨（不涨不跌在视觉上不涂绿）——与全站 RiseFallText 的 0 处理一致。
 */
export function bestReturnClass(v: number | null | undefined): string {
  if (v == null) return "";
  return v >= 0 ? "is-rise" : "is-fall";
}

/** 从业年限副文案：点明口径，避免把「日历跨度」误读成「累计在任年数」 */
export function tenureCaption(
  tenure: { basis?: string } | null | undefined
): string | undefined {
  if (!tenure) return undefined;
  return tenure.basis === "em_days_derived"
    ? "自首次任职起算"
    : "按任职起始日推算";
}

/**
 * 风格标签 key 后缀 → 三档视觉档位（#2044）。
 *
 * 档位是**强度阶梯不是评价**（集中度高≠坏、中性≠好），故只用墨色/填充权重递进，
 * 不用红绿——那是涨跌语义专用（见 design.md「Badge / Tag」）。size 维度的
 * small/balanced/large 映射到同一阶梯；未知后缀落 mid（中性默认，前向兼容）。
 */
export function styleTierClass(key: string): string {
  const suffix = key.split("_").pop() ?? "";
  if (suffix === "low" || suffix === "small") return "is-low";
  if (suffix === "high" || suffix === "large") return "is-high";
  return "is-mid";
}

/**
 * 档案是否有可展示的任期类数据（决定是否还要给「尚未同步」说明）。
 *
 * 全空时不解释一句，用户会把「整块空白」读成加载失败。
 */
export function hasTenureData(
  p: ManagerProfileResult | null | undefined
): boolean {
  if (!p) return false;
  return (
    p.appointment_date != null ||
    p.tenure_display != null ||
    p.sum_scale != null ||
    (p.funds ?? []).some(f => f.start_date != null)
  );
}

/** 任职基金是否被 fund_limit 截断（后端上限 20，实测最多 42 只） */
export function fundsTruncated(
  p: ManagerProfileResult | null | undefined
): boolean {
  return !!p && p.fund_count > (p.funds ?? []).length;
}

/**
 * 任期跨度文案：`2020-03-01` → `2020-03 ~ 至今`。
 *
 * 空起始日不渲染（调用方按 `undefined` 跳过），不显示「— ~ —」。
 * 精度到月：经理任期以月为粒度阅读，带上日反而是噪声。
 */
export function tenureSpan(
  startDate: string | null | undefined,
  endDate: string | null | undefined
): string | undefined {
  if (!startDate) return undefined;
  const start = startDate.slice(0, 7);
  const end = endDate ? endDate.slice(0, 7) : "至今";
  return `${start} ~ ${end}`;
}
