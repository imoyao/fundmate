import { ref } from "vue";
import echarts from "@/plugins/echarts";
import { getSnapshots, type AssetSnapshotItem } from "@/api/summary";
import { getCssVar, getCssVarWithAlpha } from "@/composables/echarts/theme";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { formatAmount } from "@/utils/currency";

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

  /**
   * 纵轴金额刻度：≥1 万折算成「万」，否则原样千分位。
   * 净资产是 6~7 位数，若逐个写 `¥1,234,567` 会把轴宽吃掉 90px，
   * 绘图区被压成一条缝——图「画得不好」的大半原因在这里。
   */
  const axisMoney = (value: number) => {
    if (Math.abs(value) >= 10000) {
      const wan = (value / 10000).toFixed(1).replace(/\.0$/, "");
      return `¥${wan}万`;
    }
    return `¥${formatAmount(value, 0)}`;
  };

  /** tooltip 保留完整金额（轴上是概览，悬停要精确到元） */
  const tooltipMoney = (value: number | string) =>
    `¥${formatAmount(Number(value), 0)}`;

  const paint = (chart: echarts.ECharts) => {
    // 轴 / 分割线颜色随主题走，不写死（design.md「Data Visualization」红线）。
    // text-tertiary-ink 是**文字级**灰（4.5:1），text-tertiary 是图形级，别看名字选。
    const axisColor = getCssVar("--text-tertiary-ink", "#716a60");
    const splitColor = getCssVar("--border-subtle", "rgba(229, 221, 212, 0.5)");

    chart.setOption({
      tooltip: {
        trigger: "axis",
        valueFormatter: tooltipMoney,
        axisPointer: { type: "line" }
      },
      // containLabel 让「¥100万」这类长刻度自己撑开左边距，不再靠手调数字
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: series.value.map(d => d.date),
        axisLine: { lineStyle: { color: splitColor } },
        axisTick: { show: false },
        // hideOverlap：宽度不够时自动抽稀，避免日期标签叠字
        axisLabel: { fontSize: 10, color: axisColor, hideOverlap: true }
      },
      yAxis: {
        type: "value",
        // scale：不从 0 起算。净值曲线长期在高位窄幅波动，硬从 0 起会把
        // 真实波动压成一条直线（原图正是如此）。
        scale: true,
        splitNumber: 4,
        axisLine: { show: false },
        axisLabel: { fontSize: 10, color: axisColor, formatter: axisMoney },
        splitLine: { lineStyle: { color: splitColor } }
      },
      series: [
        {
          name: "净资产",
          type: "line",
          smooth: true,
          data: series.value.map(d => d.net),
          // 点少时给圆点（否则单点/两点的线画不出来），点密时隐去避免糊成一条带
          showSymbol: series.value.length <= 14,
          symbol: "circle",
          symbolSize: 4,
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
          lineStyle: { width: 2 }
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
