import { computed, ref } from "vue";
import echarts from "@/plugins/echarts";
import { getSnapshots, type AssetSnapshotItem } from "@/api/summary";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import type { ScopeProps } from "@/composables/analysisScope/toScopeProps";
import { buildNetWorthOption } from "./netWorthChartOption";

/**
 * 资产净值走势（复盘页的**独占项**：welcome 让出、panorama 只取快照做环比
 * 同比，全站唯一）——取数 + 图表实例生命周期收口于此；**option 组装**在
 * `netWorthChartOption.ts`（纯函数，便于单独渲染验证）。
 *
 * 2026-10-25 自 IntelligentAnalysis.vue 拆出：该页接入页内导航（PageNav /
 * PageToc）后逼近 check_vue_size.mjs 的 400 行门禁，把这段与区块强内聚的
 * 逻辑挪进 composable 让页面净减少（#980 / #2323 的既定做法）。
 *
 * #2164：init / window resize / 卸载 dispose / 主题重绘 / keepAlive 恢复时
 * resize 统一交给 useEchartsLifecycle；`reuse: true` 保留「刷新复用实例」
 * 语义——否则每次刷新都重建实例，动画状态丢失且肉眼可见地闪一下。
 *
 * 2026-11-28（复盘页口径切换器）：可选 `getScope` 取账户级（#1181）/ 组合级（D135）
 * 序列，不传 = 家庭级（存量行为）。**用 getter 而不是值**：`props.ledgerId` 在
 * setup 时可能还是 `undefined`，传值会在切档时读到快照时刻的旧参数。
 * 切档重取由调用方（`NetWorthTrendSection`）在 watch 里触发——这里只负责
 * 「按当前口径取一次」，不持有口径状态。
 */
export function useNetWorthTrend(getScope?: () => ScopeProps) {
  const chartRef = ref<HTMLElement | null>(null);
  const series = ref<Array<{ date: string; net: number }>>([]);
  /** 首次/切档取数中：区块据此区分「还没回来」与「确实没有快照」（后者才报空态） */
  const loading = ref(false);
  const latestSnapshot = ref<AssetSnapshotItem | null>(null);

  /** 区间变化：首末两个快照之间涨了多少（绝对额 + 百分比），区块头的胶囊用 */
  const rangeChange = computed(() => {
    const list = series.value;
    if (list.length < 2) return null;
    const first = list[0];
    const last = list[list.length - 1];
    const abs = last.net - first.net;
    // 起点为 0 时百分比无意义（除零），只报绝对额
    const pct = first.net === 0 ? null : (abs / first.net) * 100;
    return { from: first.date, to: last.date, abs, pct };
  });

  const paint = (chart: echarts.ECharts) => {
    chart.setOption(buildNetWorthOption(series.value));
  };

  const { render: renderChart } = useEchartsLifecycle(
    [
      {
        ref: chartRef,
        build: el => {
          const chart = echarts.init(el);
          paint(chart);
          return chart;
        },
        update: paint
      }
    ],
    { keepAlive: true, reuse: true, autoRenderOnMount: false }
  );

  const load = async () => {
    const { ledgerId, portfolioId } = getScope?.() ?? {};
    loading.value = true;
    try {
      const res = await getSnapshots(
        ledgerId == null && portfolioId == null
          ? undefined
          : { ledger_id: ledgerId, portfolio_id: portfolioId }
      );
      const list = res?.data ?? [];
      series.value = list.map(i => ({
        date: i.snapshot_date,
        net: i.net_worth
      }));
      latestSnapshot.value = list.length ? list[list.length - 1] : null;
    } catch {
      series.value = [];
      latestSnapshot.value = null;
    } finally {
      loading.value = false;
    }
  };

  return {
    chartRef,
    series,
    loading,
    latestSnapshot,
    rangeChange,
    load,
    renderChart
  };
}
