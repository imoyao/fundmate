/**
 * 行业恐贪展示口径（#2479 · 探市「行业情绪」档）。
 *
 * 纯函数模块（组件逻辑抽离，供 vitest 直测——项目既有范式，见
 * productPositionMetrics / pbroeChartMetrics）。
 *
 * 口径纪律：
 * - 五档阈值与原站一致（0-20/20-40/40-60/60-80/80-100），色族映射到全站
 *   温度令牌 --temp-low/mid/high（三档色族 + -ink/-bg 变体，见 colors.css）：
 *   恐惧侧=low（绿，机会区）、中性=mid、贪婪侧=high（红，谨慎区）。
 *   不自造色值（design.md 红线：颜色一律走语义 token）。
 * - metric（PH/TF）是上游原文后缀、语义未实证：徽标只透出原文，不解读。
 * - value 为 null（理论不存在，job 层已过滤）防御性排到最后。
 */

import type { IndustryEmotionItem } from "@/api/market";

export interface EmotionLevel {
  /** 档位键（测试/埋点用） */
  key: "extreme-fear" | "fear" | "neutral" | "greed" | "extreme-greed";
  /** 档位文案（与原站五档一致） */
  label: string;
  /** 前景文字色令牌（-ink 族，白底对比度达标） */
  inkVar: string;
  /** 背景/边框色令牌（-bg 族） */
  bgVar: string;
}

const LEVELS: Record<EmotionLevel["key"], EmotionLevel> = {
  "extreme-fear": {
    key: "extreme-fear",
    label: "极度恐惧",
    inkVar: "--temp-low-ink",
    bgVar: "--temp-low-bg"
  },
  fear: {
    key: "fear",
    label: "恐惧",
    inkVar: "--temp-low-ink",
    bgVar: "--temp-low-bg"
  },
  neutral: {
    key: "neutral",
    label: "中性",
    inkVar: "--temp-mid-ink",
    bgVar: "--temp-mid-bg"
  },
  greed: {
    key: "greed",
    label: "贪婪",
    inkVar: "--temp-high-ink",
    bgVar: "--temp-high-bg"
  },
  "extreme-greed": {
    key: "extreme-greed",
    label: "极度贪婪",
    inkVar: "--temp-high-ink",
    bgVar: "--temp-high-bg"
  }
};

/** 恐贪值 → 五档（阈值与原站一致：20/40/60/80 分界） */
export function emotionLevel(value: number | null): EmotionLevel {
  if (value == null || Number.isNaN(value)) return LEVELS.neutral;
  if (value < 20) return LEVELS["extreme-fear"];
  if (value < 40) return LEVELS.fear;
  if (value < 60) return LEVELS.neutral;
  if (value < 80) return LEVELS.greed;
  return LEVELS["extreme-greed"];
}

/** 展示排序：value 降序，null/NaN 防御性排最后 */
export function sortedEmotionItems(
  items: IndustryEmotionItem[]
): IndustryEmotionItem[] {
  return [...items].sort((a, b) => {
    const av = a.value;
    const bv = b.value;
    if (av == null) return 1;
    if (bv == null) return -1;
    return bv - av;
  });
}

/** 历史累积提示：不足 2 天不显示（「1 天」没有信息量） */
export function historyText(days: number): string {
  return days >= 2 ? `已累积 ${days} 天历史` : "";
}

/** 恐贪值展示：整数不带小数（34），小数保留两位去尾零（99.85） */
export function formatEmotionValue(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}
