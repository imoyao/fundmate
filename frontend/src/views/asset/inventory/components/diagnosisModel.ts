import type {
  BehaviorData,
  BehaviorProfile,
  EngineStrategyMeta,
  SignalAction
} from "@/api/strategyEngine";

/**
 * 策略诊断卡的翻译与格式化口径（#980 拆分自 `StrategyDiagnosisCard.vue`）。
 *
 * 合规红线：后端 `contracts.py` 与 `allocation.py` 明确禁止「建议买入 / 建议卖出」措辞。
 * `ACTION_LABELS` 只把 action 翻成**区间状态词**（规则落在哪里），不带任何祈使语气；
 * 未收录的 action 原样退回，不猜、不编。
 */

/** action → 中性状态词。描述「规则落在哪个区间」，不带任何祈使语气 */
export const ACTION_LABELS: Record<SignalAction, string> = {
  buy: "买入区间",
  hold: "持有区间",
  reduce: "减仓区间",
  sell: "离场区间",
  watch: "观望"
};

export function actionLabel(action: SignalAction): string {
  return ACTION_LABELS[action] || action;
}

/** 有元信息就显示策略名（人话），否则原样退回 code——不猜、不编 */
export function strategyName(
  strategies: EngineStrategyMeta[] | undefined,
  code: string
): string {
  return strategies?.find(s => s.code === code)?.name || code;
}

/** 按 symbol 建索引，供逐标的渲染时 O(1) 取画像 */
export function buildProfileMap(
  behavior: BehaviorData | null
): Record<string, BehaviorProfile> {
  const map: Record<string, BehaviorProfile> = {};
  for (const profile of behavior?.profiles ?? []) {
    map[profile.symbol] = profile;
  }
  return map;
}

/** 最多两位小数、去掉尾零 */
export function round(value: number): number {
  return Number(value.toFixed(2));
}

/** 可为 null 的指标：null = 数据不足，显示「—」而不是 0 */
export function formatNullable(
  value: number | null | undefined,
  unit: string
): string {
  return value === null || value === undefined ? "—" : `${round(value)}${unit}`;
}

/**
 * 机会成本（元）：**带符号**。
 * 正 = 提前卖出少赚的；负 = 提前卖出反而躲过下跌——负数必须原样显示。
 */
export function formatSignedMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${round(value)} 元`;
}
