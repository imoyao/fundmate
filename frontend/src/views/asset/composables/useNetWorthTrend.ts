import { ref } from "vue";
import echarts from "@/plugins/echarts";
import { getSnapshots, type AssetSnapshotItem } from "@/api/summary";
import { getCssVar, getCssVarWithAlpha } from "@/composables/echarts/theme";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";

/**
 * 资产净值走势（复盘页的**独占项**：welcome 让出、panorama 只取快照做环比
 * 同比，全站唯一）——取数 + 绘图 + 图表实例生命周期收口于此。
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

  const paint = (chart: echarts.ECharts) => {
    chart.setOption({
      tooltip: { trigger: "axis" },
      grid: { right: "4%", bottom: "8%", containLabel: true, left: "4%" },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: series.value.map(d => d.date),
        axisLabel: { fontSize: 10 }
      },
      yAxis: {
        type: "value",
        axisLabel: { fontSize: 10, formatter: "¥{value}" }
      },
      series: [
        {
          name: "净资产",
          type: "line",
          smooth: true,
          data: series.value.map(d => d.net),
          // 面积渐变按折线主色 --brand-700 派生透明度（#2156：原硬编码
          // rgba(255,107,0,…) 与 --brand-700(#e34f38) 不是同色，暗色更明显）。
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              {
                offset: 0,
                color: getCssVarWithAlpha("--brand-700", 0.3, "#e34f38")
              },
              {
                offset: 1,
                color: getCssVarWithAlpha("--brand-700", 0.05, "#e34f38")
              }
            ])
          },
          // 主色走语义变量（--brand-700），避免硬编码 hex（design.md 红线）
          itemStyle: { color: getCssVar("--brand-700", "#e34f38") },
          lineStyle: { width: 2 },
          symbol: "circle",
          symbolSize: 4
        }
      ]
    });
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

  return { chartRef, series, latestSnapshot, load, renderChart };
}
