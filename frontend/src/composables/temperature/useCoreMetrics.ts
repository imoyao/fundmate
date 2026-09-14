// frontend/src/composables/temperature/useCoreMetrics.ts
// 温度「核心指标」清单的**唯一真相源**。
//
// 【为什么抽出来】（2026-09-12 重构，见 #980）
// 方案 D 的「概览」与「深度」两档展示同一批核心指标（恐惧贪婪 / 股债性价比 /
// 可转债 / 成交额）。改造前两档各写了一遍「标题 + 取值 + 单位 + 等级」的映射：
//   · ExploreTemperatureDashboard.vue —— 直接写 <MetricCard title="恐惧贪婪" .../>
//   · ExploreDetailPanel.vue —— 在 local coreMetrics computed 里再 push 一遍
// 同一份映射写两遍 ⇒ 增删指标要改两处、漏改就两档不一致。
// 现收口到这里：指标只定义一次，档位差异只体现在「取哪个子集」。
import { computed } from "vue";
import { useTemperatureOverview } from "./useTemperatureOverview";

/** 指标标识：档位按 key 取子集 */
export type CoreMetricKey = "fear" | "self_calc" | "cb" | "volume";

export interface CoreMetric {
  key: CoreMetricKey;
  title: string;
  value: number | null;
  unit?: string;
  level: string;
}

/** 概览档只展示这两个锚点指标；更完整的清单留给深度档 */
export const OVERVIEW_METRIC_KEYS: CoreMetricKey[] = ["fear", "self_calc"];

export function useCoreMetrics() {
  const {
    fearData,
    selfCalcPercent,
    selfCalcLevel,
    cbTemperature,
    cbLabel,
    volumeData
  } = useTemperatureOverview();

  /**
   * 全部核心指标（数组顺序即展示顺序）。
   * 统一「总是返回、value 可为 null」：缺数据时显示「暂无数据」占位卡，
   * 而不是整卡消失造成布局跳动。
   */
  const coreMetrics = computed<CoreMetric[]>(() => [
    {
      key: "fear",
      title: "恐惧贪婪",
      value: fearData.value?.value ?? null,
      level: fearData.value?.label || "暂无数据"
    },
    {
      key: "self_calc",
      title: "股债性价比",
      value: selfCalcPercent.value,
      unit: "%",
      level: selfCalcLevel.value
    },
    {
      key: "cb",
      title: "可转债",
      value: cbTemperature.value,
      unit: "°",
      level: cbLabel.value || "暂无"
    },
    {
      key: "volume",
      title: "成交额",
      value: volumeData.value?.value ?? null,
      unit: "亿",
      level: volumeData.value?.label || "暂无"
    }
  ]);

  /** 概览档锚点指标（恐惧贪婪 + 股债性价比） */
  const overviewMetrics = computed(() =>
    coreMetrics.value.filter(m => OVERVIEW_METRIC_KEYS.includes(m.key))
  );

  return { coreMetrics, overviewMetrics };
}
