import { computed, ref, type Ref } from "vue";
import { getBenchmarkExcess, type BenchmarkExcessResult } from "@/api/summary";
import type { PortfolioDetail } from "@/api/portfolio";
import { EXCESS_RANGE_DAYS, excessDateRange } from "@/utils/benchmarkExcess";
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
 * `GET /api/summary/benchmark-excess/`（近 90 天），失败时**整卡降级「--」**，
 * 不让超额计算失败打断详情页主体。
 *
 * 取数放在 composable 而非页面里：这段是「一次请求 + 五段文案/配色派生」，
 * 与页面其它状态没有交集，留在页面里只会把 script 撑长（#980）。
 */
export function usePortfolioExcess(
  portfolioId: Ref<number>,
  portfolio: Ref<PortfolioDetail | null>
) {
  const excess = ref<BenchmarkExcessResult | null>(null);
  const rangeLabel = `近 ${EXCESS_RANGE_DAYS} 天`;

  async function fetchExcess() {
    try {
      const res = await getBenchmarkExcess({
        ...excessDateRange(),
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
    benchmarkCaptionOf(excess.value, rangeLabel)
  );

  /** MetricCard 空值显示「--」：toFixed 前判 null，绝不上 0 占位 */
  const excessValue = computed(() => excessValueText(excess.value));

  const excessColor = computed(() => excessColorOf(excess.value));

  const excessCaption = computed(() =>
    excessCaptionOf(excess.value, rangeLabel)
  );

  return {
    excess,
    rangeLabel,
    fetchExcess,
    benchmarkLabel,
    benchmarkCaption,
    excessValue,
    excessColor,
    excessCaption
  };
}
