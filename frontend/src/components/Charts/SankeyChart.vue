<!--
  SankeyChart · 资产构成桑基图

  #980 批 B8 拆分后本文件只剩三件事：**容器与空态的模板**、**「什么时候画」**、
  **ECharts 实例的生命周期接线**。几何与配置已分别搬到：
  - `sankeyLayout.ts` —— 分层 BFS、资产负债分支、同层排序、取色（纯函数，可单测）
  - `sankeyOption.ts` —— option 组装（改它通常是调视觉，与几何无关）

  `reuse: true` 而非默认的全量重建：桑基图每次都要按 `clientWidth` 重算手动布局，
  重建实例会丢掉动画状态并肉眼可见地闪一下。
-->
<template>
  <div class="sankey-chart-container">
    <div v-show="isEmpty" class="empty-state">
      <IconifyIconOffline
        icon="ep:folder-opened"
        class="text-4xl mb-2"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      />
      <p :style="{ color: 'var(--text-tertiary-ink)' }">暂无资产构成数据</p>
    </div>
    <div
      ref="chartRef"
      class="chart"
      :style="{ visibility: isEmpty ? 'hidden' : 'visible' }"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue";
import echarts from "@/plugins/echarts";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getCssVar } from "@/composables/echarts/theme";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import {
  computeManualLayout,
  computeMaxLevel,
  hasDrawableData
} from "./sankeyLayout";
import { buildSankeyOption } from "./sankeyOption";

const props = defineProps<{
  data: { nodes: any[]; links: any[] };
  displayMode: "amount" | "percent" | "hidden";
}>();

const chartRef = ref<HTMLElement | null>(null);
const isEmpty = ref(true);
const totalValue = ref(0);
const containerHeight = ref(400);
// v-bind 在 <style> 中不能直接拼接字符串表达式，需在此先拼好带 px 的单位字符串
const containerHeightPx = computed(() => `${containerHeight.value}px`);

/** CSS 变量读取（生产实现；布局函数通过参数接收它，以便单测换假实现） */
const readVar = (varName: string): string => getCssVar(varName);

const LEFT_PAD = 100;
const RIGHT_PAD = 80;

/**
 * 把 option 画到**给定实例**上。init / dispose 归 composable，本函数只做绘制，
 * 便于 build（首绘）与 update（复用后重绘）两条路径共用同一份绘制逻辑。
 */
function paint(chart: echarts.ECharts, el: HTMLElement) {
  isEmpty.value = !hasDrawableData(props.data);

  if (isEmpty.value) {
    // 空数据不画图（保留空白绘图区 + 空态遮罩）。这里 dispose 而非「留一张全 0 的空图」——
    // composable 下次 render 会因 isDisposed() 为真而重新 build，故这里可以安全交回收。
    chart.dispose();
    return;
  }

  const maxLevel = computeMaxLevel(props.data.nodes, props.data.links);
  const { nodes: layoutNodes, maxY } = computeManualLayout(
    props.data.nodes,
    props.data.links,
    el.clientWidth,
    maxLevel,
    LEFT_PAD,
    RIGHT_PAD,
    readVar
  );

  containerHeight.value = Math.max(maxY + 40, 400);

  const totalNode = layoutNodes.find(n => n.name === "总资产");
  totalValue.value = (totalNode?.value as number) || 0;

  chart.setOption(
    buildSankeyOption({
      links: props.data.links,
      layoutNodes,
      displayMode: props.displayMode,
      totalValue: totalValue.value,
      leftPad: LEFT_PAD,
      rightPad: RIGHT_PAD,
      readVar
    }),
    true
  );
}

// #2164：实例生命周期交给 composable —— window resize 自动 resize、卸载 dispose、
// 主题切换重绘（composable 内置 `watch(themeTick, render)`）、keepAlive 恢复时 resize，
// 这四项原先是本文件手写的（与 components.md:539「禁止各页面重新手写」相悖）。
const { render } = useEchartsLifecycle(
  [
    {
      ref: chartRef,
      build: el => {
        const chart = echarts.init(el);
        paint(chart, el);
        return chart;
      },
      update: chart => {
        const el = chartRef.value;
        if (!el) return;
        paint(chart, el);
      }
    }
  ],
  {
    keepAlive: true,
    // 复用实例：桑基图每次都按 clientWidth 重算手动布局，重建会闪
    reuse: true,
    // 首次绘制交给下面的 watch（immediate + nextTick，等 DOM 挂载后再画）
    autoRenderOnMount: false
  }
);

// 数据 / 显示模式变化时重绘。`nextTick` 不能省：watch 的 immediate 在 setup 阶段
// 就跑，此时 `chartRef.value` 还是 null（composable 内部会因 `if (!el) return` 跳过）。
watch(
  () => [props.data.nodes, props.data.links, props.displayMode],
  () => nextTick(render),
  { deep: true, immediate: true }
);
</script>

<style scoped>
.sankey-chart-container {
  position: relative;
  width: 100%;

  /* 注意：CSS v-bind 区分大小写，必须与 script 中的 containerHeightPx 完全一致 */
  height: v-bind(containerHeightPx);
  contain: layout style;
}

.chart {
  width: 100%;
  height: 100%;
}

.empty-state {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
</style>
