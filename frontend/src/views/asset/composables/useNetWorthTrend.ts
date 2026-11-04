import { computed, ref } from "vue";
import echarts from "@/plugins/echarts";
import { getSnapshots, type AssetSnapshotItem } from "@/api/summary";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
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
 */
export function useNetWorthTrend() {
  const chartRef = ref<HTMLElement | null>(null);
  const series = ref<Array<{ date: string; net: number }>>([]);
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
    try {
      const res = await getSnapshots();
      const list = res?.data ?? [];
      series.value = list.map(i => ({
        date: i.snapshot_date,
        net: i.net_worth
      }));
      latestSnapshot.value = list.length ? list[list.length - 1] : null;
    } catch {
      series.value = [];
      latestSnapshot.value = null;
    }
  };

  return { chartRef, series, latestSnapshot, rangeChange, load, renderChart };
}
