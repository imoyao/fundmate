// src/views/welcome/composables/mentalAccounts.ts
/**
 * 首页「心理账户」卡的取数与展示派生（纯函数，node 环境可测）。
 *
 * ## 为什么要有这个模块
 *
 * 这张卡此前是 `store/modules/overview.ts` 里写死的四条假数据
 * （`¥120,000 / ¥300,000 / ¥520,000 / ¥45,000`），标签也是另起的一套
 * 「活钱 / 保命钱 / 长久钱 / 赌钱」。它不是空态，是**四个编造的数字**——
 * 用户会当成自己的钱读，这比「暂无数据」更坏（#3031 背景、#3115 D4）。
 *
 * 现在唯一数据源是 `/api/summary/distributions/` 的 `allocation_scope`：
 * - `buckets` 是**全五档（含 0 值）**，空档必须显示——「保命钱为 0」是财务信号，
 *   静默不显示等于替用户藏了一件事；
 * - `label` 一律取自后端，前端**不做 key → 中文**的翻译（`conventions.md` §2.9）。
 *
 * ## 口径纪律
 *
 * - 占比分母是 `allocation_scope.denominator`（持仓 + 非负债成员资产行），
 *   **不是** `total_assets`——房产 / 应收 / 负债都不在这五笔钱里。
 * - 未纳入项（房产、应收）单独展示，不许静默丢弃：那是「少算 220 万」的入口。
 */

import type { AllocationBucket, DistributionsData } from "@/api/summary";
import { ALLOCATION_COLOR_VARS } from "@/constants";

/** 心理账户展示条目（金额格式化交给模板中的 MoneyDisplay 组件） */
export type MentalAccountItem = {
  key: string;
  /** 档位中文名，**来自后端** `buckets[].label` */
  name: string;
  amount: number;
  /** 占分母的百分比（1 位小数）；分母 ≤ 0 时为 0 */
  percent: number;
  /** 展示文案：≥1% 取整、<1% 留 1 位、非零但不足 0.1% 显示「＜0.1%」 */
  percentText: string;
  /** CSS 变量（`--sankey-*`），从 `constants.ALLOCATION_COLOR_VARS` 取 */
  color: string;
  /** 空档：金额为 0，卡面弱化显示但**不隐藏** */
  empty: boolean;
};

/** 卡面需要的全部派生值 */
export type MentalAccountView = {
  items: MentalAccountItem[];
  /** 分母（只算可投资资产端） */
  denominator: number;
  /** 未纳入项（房产 / 应收…），卡面显式可见 */
  excluded: Array<{ name: string; value: number }>;
  excludedTotal: number;
  liabilitiesTotal: number;
  /** 「活钱」档为 0 时的一条可操作提示；否则 null */
  liquidHint: string | null;
};

const round1 = (n: number): number => Math.round(n * 10) / 10;

/**
 * 占比文案。`0.17%` 这种绝不能显示成 `0%`——金额明明白白摆着，百分比写 0 就是自相矛盾；
 * 但 `0.04%` 四舍五入到 1 位也是 0，故退到「＜0.1%」。
 */
export function percentTextOf(amount: number, denominator: number): string {
  if (amount <= 0 || denominator <= 0) return "0%";
  const pct = (amount / denominator) * 100;
  if (pct >= 1) return `${Math.round(pct)}%`;
  if (pct >= 0.1) return `${round1(pct)}%`;
  return "＜0.1%";
}

/** 金额格式化（卡面脚注用，与 MoneyDisplay 的千分位风格一致，不带小数） */
function yuanText(n: number): string {
  return `¥${Math.round(n).toLocaleString("zh-CN")}`;
}

/**
 * 从分布响应派生卡面数据。`dist` 为 null（未加载 / 失败）时返回 null，
 * 由组件区分「加载中」与「真的没有数据」两种形态。
 */
export function buildMentalAccountView(
  dist: DistributionsData | null
): MentalAccountView | null {
  if (!dist) return null;
  const scope = dist.allocation_scope;
  const denominator = scope?.denominator ?? 0;

  // 主路径：后端给的是全五档。退化路径（老响应缺 buckets）只列非零桶，
  // 颜色与提示都降级——宁可少显示，也不要前端自己补 key → 中文的映射表。
  const buckets: AllocationBucket[] =
    scope?.buckets && scope.buckets.length
      ? scope.buckets
      : (dist.allocation_distribution ?? []).map(d => ({
          key: d.name,
          label: d.name,
          value: d.value
        }));

  const items: MentalAccountItem[] = buckets.map(b => {
    const amount = Number(b.value) || 0;
    return {
      key: b.key,
      name: b.label,
      amount,
      percent: denominator > 0 ? round1((amount / denominator) * 100) : 0,
      percentText: percentTextOf(amount, denominator),
      color: ALLOCATION_COLOR_VARS[b.key] ?? "var(--text-primary)",
      empty: amount <= 0
    };
  });

  const excluded = (scope?.excluded ?? []).filter(row => (row.value ?? 0) > 0);
  const excludedTotal = scope?.excluded_total ?? 0;
  const liabilitiesTotal = scope?.liabilities_total ?? 0;

  // 提示只在「活钱档确实是 0」时出现；档位名取自后端，不硬编码「活钱」二字。
  const liquid = items.find(item => item.key === "liquid");
  const liquidHint =
    liquid && liquid.empty && denominator > 0
      ? `${liquid.name}为 0：账户现金还没有录入，在账户详情录一笔余额后才会出现在这里`
      : null;

  return {
    items,
    denominator,
    excluded,
    excludedTotal,
    liabilitiesTotal,
    liquidHint
  };
}

/** 脚注：分母 / 未纳入 / 负债，三段都只在有值时才出现在文案里 */
export function scopeFootnote(view: MentalAccountView): string {
  const parts = [`分母 ${yuanText(view.denominator)}`];
  if (view.excluded.length) {
    const rows = view.excluded
      .map(row => `${row.name} ${yuanText(row.value)}`)
      .join(" / ");
    parts.push(`未纳入 ${rows}`);
  } else if (view.excludedTotal > 0) {
    parts.push(`未纳入 ${yuanText(view.excludedTotal)}`);
  }
  if (view.liabilitiesTotal > 0) {
    parts.push(`负债 ${yuanText(view.liabilitiesTotal)}（不计入）`);
  }
  return parts.join(" · ");
}
