<!--
  AssetAllocationDonut · 资产配置环形图（强制复用，见 docs/design/components.md）
  - 统一「环形 + 底部图例（分类名 + 占比）」的资产分布图，替代各页手写 pie option。
  - 基于 useEchartsLifecycle：自动 render / window resize / 卸载 dispose / keepAlive 重绘。
  - 颜色必须走 CSS 语义变量：colorMap 的值为变量名（如 "--asset-cat-stock"）；不传或缺失时
    用 --chart-01~08 循环取色（design.md「Data Visualization」红线：禁止硬编码 hex）。
-->
<template>
  <div ref="chartRef" class="allocation-donut" />
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import echarts from "@/plugins/echarts";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { getCssVar } from "@/composables/echarts/theme";

interface DonutDatum {
  name: string;
  value: number;
}

const props = withDefaults(
  defineProps<{
    /** 分布数据（name 分类名，value 数值） */
    data: DonutDatum[];
    /** 分类色映射：name -> CSS 变量名；不传或缺失用 --chart-01~08 循环 */
    colorMap?: Record<string, string>;
    /** 空态文案（中心显示），默认「暂无数据」 */
    emptyText?: string;
    /** 是否显示底部图例，默认 true */
    showLegend?: boolean;
    /**
     * 图例是否显示占比（`名称 xx.x%`），默认 true。
     * 分类名本身已含含义的调用方可传 false——占比在 tooltip 里也有。
     * 注：首页资产看板改为按**资产大类**出图（#1955，原按 market 分组恒为单扇区），
     * 大类只有 4 项、带占比不换行，故回到默认 true（原先传 false 是为 market 分组时的窄图例让位）。
     */
    showLegendPercent?: boolean;
    /**
     * 图例字号，默认 12。
     * 空间紧凑的容器（首页资产看板）传 10——图例条目多时 12 会换行。
     */
    legendFontSize?: number;
    /**
     * tooltip 数值格式化，默认按**金额**（`¥1,234`）。
     *
     * ⚠️ 这个组件此前只服务资产分布（值是元），tooltip 硬编码了 `¥`。
     * 基金行业配置卡（#2029 卡 C）传的是**占比%**，若沿用会在 tooltip 里
     * 显示「¥30.0（33.7%）」—— 给百分比加货币符号属于编造单位。
     * 故开放此 prop：传函数即接管，不传保持原样（现有 4 个调用方零改动）。
     */
    formatValue?: (value: number, pct: number) => string;
  }>(),
  {
    colorMap: () => ({}),
    emptyText: "暂无数据",
    showLegend: true,
    showLegendPercent: true,
    legendFontSize: 12,
    formatValue: undefined
  }
);

const chartRef = ref<HTMLElement | null>(null);

const CHART_PALETTE_VARS = [
  "--chart-01",
  "--chart-02",
  "--chart-03",
  "--chart-04",
  "--chart-05",
  "--chart-06",
  "--chart-07",
  "--chart-08"
];

function colorFor(name: string): string {
  const varName = props.colorMap[name];
  if (varName) return getCssVar(varName, "#8E8B82");
  const idx = props.data.findIndex(d => d.name === name);
  // findIndex 未命中返回 -1，而 `-1 % 8 === -1`（JS 取模不取绝对值），
  // 数组下标 -1 是undefined → 兜底分支吃进品牌红，让「未知分类」被画成红色，
  // 与真实的涨跌色语义撞车。未命中直接给中性灰，宁可朴素也不误用语义色。
  if (idx < 0) return getCssVar("--text-tertiary", "#8E8B82");
  return getCssVar(
    CHART_PALETTE_VARS[idx % CHART_PALETTE_VARS.length] ?? "--chart-01",
    "#8E8B82"
  );
}

function buildOption() {
  const total = props.data.reduce((s, d) => s + (d.value || 0), 0);
  // 空态判定：数组为空 **或** 全部值为 0。
  // 仅判 length 会漏掉「账户无数据」场景：调用方（账本详情页等）通常固定传全部分类
  // （如「投资资产 / 现金类资产」），空账户时两个值都是 0、数组长度仍为 2，空态不触发。
  // 而 ECharts 在总和为 0 时会把圆环按分类数均分（见 pieLayout.js：sum===0 时每个
  // 扇区取 unitRadian = 2π / 分类数），两个分类即各占 180°，视觉上变成误导性的
  // 「50% / 50%」，与"账户里根本没有数据"的事实不符。故总和为 0 一律按空态处理。
  const isDataEmpty = props.data.length === 0 || total === 0;
  const legendTextColor = getCssVar("--text-secondary", "#6b655c");
  const borderColor = getCssVar("--bg-card", "#ffffff");
  // 尊重系统减弱动效偏好：关闭 echarts 入场动画
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const showLegend = props.showLegend && !isDataEmpty;

  return {
    animation: !reduceMotion,
    tooltip: {
      trigger: "item",
      backgroundColor: getCssVar("--bg-card", "#ffffff"),
      borderColor: getCssVar("--border-light", "#f0ebe4"),
      textStyle: {
        color: getCssVar("--text-primary", "#2d2a24"),
        fontSize: 12
      },
      formatter: (params: { name: string; value: number }) => {
        const pct = total > 0 ? ((params.value / total) * 100).toFixed(1) : "0";
        const value = props.formatValue
          ? props.formatValue(params.value, Number(pct))
          : `¥${Number(params.value).toLocaleString()}（${pct}%）`;
        return `${params.name}<br/>${value}`;
      }
    },
    legend: showLegend
      ? {
          bottom: 0,
          icon: "circle",
          itemWidth: 8,
          itemHeight: 8,
          itemGap: 12,
          textStyle: { color: legendTextColor, fontSize: props.legendFontSize },
          // 分类名 + 占比（%），占比按 total 实时计算。
          // showLegendPercent=false 时只显示分类名（首页资产看板的图例条目已含
          // 分类名 + 金额，再加百分比会挤换行）。
          formatter: (name: string) => {
            if (!props.showLegendPercent) return name;
            const d = props.data.find(x => x.name === name);
            const pct =
              total > 0 ? (((d?.value || 0) / total) * 100).toFixed(1) : "0";
            return `${name} ${pct}%`;
          }
        }
      : undefined,
    series: [
      {
        type: "pie",
        // 有数据时**上移圆心并内缩外径**：给底部图例换行预留空间。
        //
        // ⚠️ 为什么必须留：legend 是 `bottom: 0` 的绝对定位，**换行时不会挤压
        // series**（pie 不参与 grid 布局）。容器 min-height 200px，图例 1 行约占底部
        // 10%、2 行约占 20%；而未内缩的圆环底缘在 50% + 70%/2 = 85% 处——
        // 2 行图例顶到 80%，就压住扇区约 5%，表现为「文字压在图形上」。
        //
        // 内缩到 42%/64% + 圆心 45% 后底缘落在 77%，两行图例也有 ~23% 余量。
        // 代价是圆环略小——宁可留白，不可重叠。
        radius: isDataEmpty ? "50%" : ["42%", "64%"],
        center: isDataEmpty ? ["50%", "50%"] : ["50%", "45%"],
        itemStyle: {
          color: (params: { name?: string }) => colorFor(params.name ?? ""),
          borderRadius: 6,
          borderColor,
          borderWidth: 2
        },
        // label 只在空态出现（position: "center"，居中占位文字），**任何一种形态都
        // 不需要引导线**。此前写 `show: !isDataEmpty` 与 `label: { show: false }`
        // 自相矛盾：有数据时画出一批指向空处的引线，视觉上就是「奇怪的线划过图形」。
        label: isDataEmpty
          ? {
              show: true,
              position: "center",
              formatter: props.emptyText,
              color: getCssVar("--text-tertiary", "#999"),
              fontSize: 12
            }
          : { show: false },
        labelLine: { show: false },
        data: isDataEmpty ? [{ name: props.emptyText, value: 1 }] : props.data
      }
    ]
  };
}

const { render } = useEchartsLifecycle(
  [
    {
      ref: chartRef,
      build: el => {
        const chart = echarts.init(el);
        chart.setOption(buildOption());
        return chart;
      }
    }
  ],
  { keepAlive: true }
);

// 数据变化（父组件传新数组引用）时重绘
watch(
  () => props.data,
  () => render()
);
</script>

<style scoped>
.allocation-donut {
  width: 100%;

  /* 容器高度由调用方通过 class（如 flex-1）控制 */
  height: 100%;
  min-height: 200px;
}
</style>
