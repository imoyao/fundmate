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

const props = defineProps<{
  data: { nodes: any[]; links: any[] };
  displayMode: "amount" | "percent" | "hidden";
}>();

// #2164：实例生命周期（init / resize / dispose / 主题重绘 / keepAlive 恢复）交给
// `useEchartsLifecycle`，本组件只负责「给定实例把 option 画上去」。
// `reuse: true` 而非默认的全量重建：桑基图每次都要按 `clientWidth` 重算手动布局，
// 重建实例会丢掉动画状态并肉眼可见地闪一下。
const chartRef = ref<HTMLElement | null>(null);
const isEmpty = ref(true);
const totalValue = ref(0);
const containerHeight = ref(400);
// v-bind 在 <style> 中不能直接拼接字符串表达式，需在此先拼好带 px 的单位字符串
const containerHeightPx = computed(() => `${containerHeight.value}px`);

// 工具函数：读取 CSS 变量
const getCSSColor = (varName: string): string => {
  return getCssVar(varName);
};

function formatLabel(params: any) {
  const val = params.value ?? 0;
  if (props.displayMode === "hidden") return params.name;
  if (props.displayMode === "percent") {
    const pct =
      totalValue.value > 0
        ? ((val / totalValue.value) * 100).toFixed(1) + "%"
        : "0%";
    return `${params.name}\n${pct}`;
  }
  const amount =
    val >= 10000 ? (val / 10000).toFixed(1) + "万" : val.toLocaleString();
  return `${params.name}\n¥${amount}`;
}

// 节点颜色映射（使用 CSS 变量）
const NODE_COLOR_VARS: Record<string, string> = {
  总资产: "--brand-700",
  净资产: "--color-fall",
  总负债: "--color-neutral",
  流动资金: "--palette-mint-green",
  投资理财: "--palette-periwinkle",
  固定资产: "--palette-warm-taupe",
  应收款: "--palette-stone-gray",
  保险项目: "--color-accent",
  活钱: "--palette-muted-blue",
  稳健底仓: "--palette-thistle",
  长期增值: "--brand-700",
  高风险博弈: "--sankey-speculative",
  保险保障: "--color-accent",
  未配置资产: "--color-neutral",
  股票: "--asset-cat-stock",
  基金: "--asset-cat-fund",
  可转债: "--asset-cat-bond",
  ETF: "--asset-cat-etf",
  虚拟货币: "--asset-cat-crypto",
  银行存款: "--asset-cat-saving"
};

function getNodeColor(name: string): string {
  const varName = NODE_COLOR_VARS[name];
  if (varName) {
    const color = getCSSColor(varName);
    if (color) return color;
  }
  // 负债统一用 neutral
  if (/贷|借|信用卡|负债/.test(name)) {
    return getCSSColor("--color-neutral") || "var(--text-tertiary)";
  }
  return getCSSColor("--text-tertiary");
}

// 手动布局（保持不变，仅颜色部分已动态）
function computeManualLayout(
  nodes: any[],
  links: any[],
  chartWidth: number,
  levelCount: number,
  leftPad: number,
  rightPad: number
) {
  const outAdj: Record<string, string[]> = {};
  const inAdj: Record<string, string[]> = {};
  nodes.forEach(n => {
    outAdj[n.name] = [];
    inAdj[n.name] = [];
  });
  links.forEach(l => {
    outAdj[l.source].push(l.target);
    inAdj[l.target].push(l.source);
  });

  const nodeLevel: Record<string, number> = {};
  const queue: string[] = [];
  nodes.forEach(n => {
    if (inAdj[n.name].length === 0) {
      nodeLevel[n.name] = 0;
      queue.push(n.name);
    }
  });
  if (queue.length === 0 && nodes.length > 0) {
    nodeLevel[nodes[0].name] = 0;
    queue.push(nodes[0].name);
  }
  let head = 0;
  while (head < queue.length) {
    const curr = queue[head++];
    (outAdj[curr] || []).forEach(next => {
      if (nodeLevel[next] === undefined) {
        nodeLevel[next] = nodeLevel[curr] + 1;
        queue.push(next);
      }
    });
  }

  const branchMap: Record<string, "asset" | "liability"> = {};
  function markLiability(name: string) {
    if (branchMap[name] === "liability") return;
    branchMap[name] = "liability";
    (outAdj[name] || []).forEach(child => markLiability(child));
  }
  if (nodeLevel["总负债"] !== undefined) markLiability("总负债");
  nodes.forEach(n => {
    if (!branchMap[n.name]) branchMap[n.name] = "asset";
  });

  const outFlow: Record<string, number> = {};
  const inFlow: Record<string, number> = {};
  nodes.forEach(n => {
    outFlow[n.name] = 0;
    inFlow[n.name] = 0;
  });
  links.forEach(l => {
    outFlow[l.source] = (outFlow[l.source] || 0) + l.value;
    inFlow[l.target] = (inFlow[l.target] || 0) + l.value;
  });
  const nodeFlow: Record<string, number> = {};
  nodes.forEach(n => {
    nodeFlow[n.name] = Math.max(outFlow[n.name], inFlow[n.name]);
  });

  const drawWidth = chartWidth - leftPad - rightPad;
  const colWidth = levelCount > 1 ? drawWidth / (levelCount - 1) : drawWidth;

  const nodeHeight = 20;
  const gap = 10;
  const branchGap = 60;

  const orderWeight: Record<string, number> = {
    投资理财: 0,
    固定资产: 1,
    流动资金: 2,
    总资产: 0,
    净资产: 0,
    总负债: 1,
    长期增值: 0,
    股票: 0,
    未配置资产: 1,
    房贷: 2,
    借家人的钱: 3
  };

  const levelGroups = Object.entries(nodeLevel).reduce(
    (acc, [name, lvl]) => {
      if (!acc[lvl]) acc[lvl] = [];
      acc[lvl].push(name);
      return acc;
    },
    {} as Record<number, string[]>
  );

  const layouted: any[] = [];
  let globalMaxY = 0;

  Object.entries(levelGroups).forEach(([lvlStr, names]) => {
    const lvl = parseInt(lvlStr);
    const x = leftPad + lvl * colWidth;

    const assetNames = names.filter(n => branchMap[n] === "asset");
    const liabilityNames = names.filter(n => branchMap[n] === "liability");

    assetNames.sort(
      (a, b) => (orderWeight[a] ?? 999) - (orderWeight[b] ?? 999)
    );
    liabilityNames.sort(
      (a, b) => (orderWeight[a] ?? 999) - (orderWeight[b] ?? 999)
    );

    let yCursor = 20;

    assetNames.forEach(name => {
      const rawNode = nodes.find(n => n.name === name)!;
      layouted.push({
        ...rawNode,
        name,
        x,
        y: yCursor,
        value: nodeFlow[name] || 0,
        itemStyle: { color: getNodeColor(name) },
        label: {
          position: lvl === 0 ? "left" : "right",
          distance: 6
        }
      });
      yCursor += nodeHeight + gap;
    });

    if (liabilityNames.length > 0) {
      yCursor += branchGap - gap;
    }
    liabilityNames.forEach(name => {
      const rawNode = nodes.find(n => n.name === name)!;
      layouted.push({
        ...rawNode,
        name,
        x,
        y: yCursor,
        value: nodeFlow[name] || 0,
        itemStyle: { color: getNodeColor(name) },
        label: {
          position: "right",
          distance: 6
        }
      });
      yCursor += nodeHeight + gap;
    });

    globalMaxY = Math.max(globalMaxY, yCursor);
  });

  return { nodes: layouted, maxY: globalMaxY };
}

/** 数据是否可画：props 就绪且 nodes/links 都非空 */
function hasDrawableData(): boolean {
  return (
    !!props.data &&
    Array.isArray(props.data.nodes) &&
    Array.isArray(props.data.links) &&
    props.data.nodes.length > 0 &&
    props.data.links.length > 0
  );
}

/**
 * 把 option 画到**给定实例**上。原先这里是 `renderChart()`：自己 init、自己
 * dispose、自己读 clientWidth。现在 init/dispose 归 composable，本函数只做绘制，
 * 便于 build（首绘）与 update（复用后重绘）两条路径共用同一份绘制逻辑。
 */
function paint(chart: echarts.ECharts, el: HTMLElement) {
  isEmpty.value = !hasDrawableData();

  if (isEmpty.value) {
    // 空数据不画图（保留空白绘图区 + 空态遮罩）。这里 dispose 而非「留一张全 0 的空图」——
    // composable 下次 render 会因 isDisposed() 为真而重新 build，故这里可以安全交回收。
    chart.dispose();
    return;
  }

  const chartWidth = el.clientWidth;
  const leftPad = 100;
  const rightPad = 80;

  // 计算最大层级（复用逻辑）
  const levels: Record<string, number> = {};
  const queue: string[] = [];
  props.data.nodes.forEach(n => {
    levels[n.name] = -1;
  });
  props.data.nodes.forEach(n => {
    const hasSource = props.data.links.some(l => l.target === n.name);
    if (!hasSource) {
      levels[n.name] = 0;
      queue.push(n.name);
    }
  });
  if (queue.length === 0 && props.data.nodes.length > 0) {
    levels[props.data.nodes[0].name] = 0;
    queue.push(props.data.nodes[0].name);
  }
  let head = 0;
  while (head < queue.length) {
    const curr = queue[head++];
    props.data.links.forEach(l => {
      if (l.source === curr && levels[l.target] === -1) {
        levels[l.target] = levels[curr] + 1;
        queue.push(l.target);
      }
    });
  }
  const maxLevel = Math.max(...Object.values(levels), 0);

  const { nodes: layoutNodes, maxY } = computeManualLayout(
    props.data.nodes,
    props.data.links,
    chartWidth,
    maxLevel,
    leftPad,
    rightPad
  );

  containerHeight.value = Math.max(maxY + 40, 400);

  const totalNode = layoutNodes.find(n => n.name === "总资产");
  totalValue.value = totalNode?.value || 0;

  chart.setOption(
    {
      tooltip: {
        trigger: "item",
        triggerOn: "mousemove",
        backgroundColor: "rgba(255,255,255,0.95)",
        borderColor: getCSSColor("--border-light"),
        textStyle: { color: getCSSColor("--text-primary"), fontSize: 12 },
        formatter: (params: any) => {
          if (params.dataType === "node") {
            const disp =
              props.displayMode === "hidden"
                ? "***"
                : "¥" + (params.value || 0).toLocaleString();
            return `${params.name}<br/>${disp}`;
          }
          return `${params.data.source} → ${params.data.target}<br/>¥${(params.value || 0).toLocaleString()}`;
        }
      },
      series: [
        {
          type: "sankey",
          layout: "none",
          data: layoutNodes,
          links: props.data.links,
          emphasis: { focus: "adjacency" },
          lineStyle: {
            color: "gradient",
            curveness: 0.3,
            opacity: 0.5
          },
          nodeWidth: 14,
          nodeGap: 10,
          label: {
            show: true,
            fontSize: 12,
            lineHeight: 16,
            formatter: formatLabel,
            overflow: "truncate",
            width: 130
          },
          left: leftPad,
          right: rightPad,
          top: 10,
          bottom: 10
        }
      ]
    },
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
