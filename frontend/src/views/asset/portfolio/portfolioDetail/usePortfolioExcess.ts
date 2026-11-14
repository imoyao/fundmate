import { computed, ref, watch, type Ref } from "vue";
import { getBenchmarkExcess, type BenchmarkExcessResult } from "@/api/summary";
import type { PortfolioDetail } from "@/api/portfolio";
import {
  chartRangeLabel,
  chartRangeParams,
  type ChartRangeKey
} from "@/utils/chartRange";
import {
  benchmarkCaptionOf,
  benchmarkLabelOf,
  excessCaptionOf,
  excessColorOf,
  excessValueText
} from "./portfolioDetailModel";

/**
 * 区间收益 vs 基准（#2134）。
 *
 * 组合详情页顶部四张指标卡里，「基准指数」与「超额收益」两张的口径都来自
 * `GET /api/summary/benchmark-excess/`，失败时**整卡降级「--」**，
 * 不让超额计算失败打断详情页主体。
 *
 * ## 周期为什么不写死（#3109）
 *
 * 这里曾经写死「近 90 天」。现在周期由 `range` 持有，并与下方「超额走势」共用
 * 同一个值（父页 `v-model:range` 双向绑定）——曲线末点必须 ≡ 卡片单值，
 * 两者各选一段区间就会立刻对不上。档位 → 起止日的换算在 `utils/chartRange.ts`，
 * 本文件不重复定义任何天数。
 *
 * 取数放在 composable 而非页面里：这段是「一次请求 + 五段文案/配色派生」，
 * 与页面其它状态没有交集，留在页面里只会把 script 撑长（#980）。
 */
export function usePortfolioExcess(
  portfolioId: Ref<number>,
  portfolio: Ref<PortfolioDetail | null>
) {
  const excess = ref<BenchmarkExcessResult | null>(null);
  /** 默认近3月：与改造前的「近 90 天」视觉连续，老用户不会以为口径变了 */
  const range = ref<ChartRangeKey>("3m");
  const rangeLabel = computed(() => chartRangeLabel(range.value));

  async function fetchExcess() {
    try {
      const res = await getBenchmarkExcess({
        ...chartRangeParams(range.value),
        portfolio_id: portfolioId.value
      });
      excess.value = res.data;
    } catch {
      // 拿不到就整卡降级「--」：详情页主体不因超额计算失败而打断
      excess.value = null;
    }
  }

  /** 基准名：优先后端归一后的宽基名；未加载 / 未识别时回落用户所设原文 */
  const benchmarkLabel = computed(() =>
    benchmarkLabelOf(excess.value, portfolio.value?.benchmark)
  );

  const benchmarkCaption = computed(() =>
    benchmarkCaptionOf(excess.value, rangeLabel.value)
  );

  /** MetricCard 空值显示「--」：toFixed 前判 null，绝不上 0 占位 */
  const excessValue = computed(() => excessValueText(excess.value));

  const excessColor = computed(() => excessColorOf(excess.value));

  const excessCaption = computed(() =>
    excessCaptionOf(excess.value, rangeLabel.value)
  );

  // 切档即重取：父页把同一个 range 也喂给「超额走势」，两处口径因此不可能分叉
  watch(range, fetchExcess);

  return {
    excess,
    range,
    rangeLabel,
    fetchExcess,
    benchmarkLabel,
    benchmarkCaption,
    excessValue,
    excessColor,
    excessCaption
  };
}
