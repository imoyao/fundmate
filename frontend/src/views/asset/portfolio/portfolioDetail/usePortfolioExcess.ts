import { computed, reactive, ref, watch, type Ref } from "vue";
import { getBenchmarkExcess } from "@/api/summary";
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
  excessValueText,
  type ExcessState
} from "./portfolioDetailModel";

/**
 * 区间收益 vs 基准（#2134）。
 *
 * 组合详情页顶部四张指标卡里，「基准指数」与「超额收益」两张的口径都来自
 * `GET /api/summary/benchmark-excess/`，失败时**整卡降级「--」**，
 * 不让超额计算失败打断详情页主体。
 *
 * ## 周期为什么不写死（#3107）
 *
 * 这里曾经写死「近 90 天」。现在周期由 `range` 持有，并与下方「超额走势」共用
 * 同一个值（父页 `v-model:range` 双向绑定）——曲线末点必须 ≡ 卡片单值，
 * 两者各选一段区间就会立刻对不上。档位 → 起止日的换算在 `utils/chartRange.ts`，
 * 本文件不重复定义任何天数。
 *
 * ## 为什么取数也在这里（#3112）
 *
 * 卡片与曲线用的是同一端点、同一组参数。此前两边各自 `getBenchmarkExcess()`：
 * 切一次档后端把同一个聚合算两遍（真库组合 1 近5年 3.06s + 5.80s），
 * 且两次返回的时刻不同，中途会短暂出现「卡片已是新档、曲线还是旧档」。
 * 现在只在这里取一次，结果以 `ExcessState` 一并交给曲线组件。
 *
 * 取数放在 composable 而非页面里：这段是「一次请求 + 五段文案/配色派生」，
 * 与页面其它状态没有交集，留在页面里只会把 script 撑长（#980）。
 */
export function usePortfolioExcess(
  portfolioId: Ref<number>,
  portfolio: Ref<PortfolioDetail | null>
) {
  /** 一次取数的结果：卡片读它的派生值，曲线组件读原样数据（见上方注释） */
  const excessState = reactive<ExcessState>({
    data: null,
    loading: false,
    error: ""
  });
  /** 默认近3月：与改造前的「近 90 天」视觉连续，老用户不会以为口径变了 */
  const range = ref<ChartRangeKey>("3m");
  const rangeLabel = computed(() => chartRangeLabel(range.value));

  async function fetchExcess() {
    excessState.loading = true;
    excessState.error = "";
    try {
      const res = await getBenchmarkExcess({
        ...chartRangeParams(range.value),
        portfolio_id: portfolioId.value
      });
      excessState.data = res.data;
    } catch (e) {
      // 拿不到就整卡降级「--」：详情页主体不因超额计算失败而打断
      const err = e as { response?: { data?: { message?: string } } };
      excessState.data = null;
      excessState.error = err?.response?.data?.message || "超额走势加载失败";
    } finally {
      excessState.loading = false;
    }
  }

  /** 基准名：优先后端归一后的宽基名；未加载 / 未识别时回落用户所设原文 */
  const benchmarkLabel = computed(() =>
    benchmarkLabelOf(excessState.data, portfolio.value?.benchmark)
  );

  const benchmarkCaption = computed(() =>
    benchmarkCaptionOf(excessState.data, rangeLabel.value)
  );

  /** MetricCard 空值显示「--」：toFixed 前判 null，绝不上 0 占位 */
  const excessValue = computed(() => excessValueText(excessState.data));

  const excessColor = computed(() => excessColorOf(excessState.data));

  const excessCaption = computed(() =>
    excessCaptionOf(excessState.data, rangeLabel.value)
  );

  // 切档即重取：父页把同一个 range 也喂给「超额走势」，两处口径因此不可能分叉
  watch(range, fetchExcess);
  // 换组合（路由参数变）也要重取：卡片与曲线共用这一份，不能只刷其中一边
  watch(portfolioId, fetchExcess);

  return {
    excessState,
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
