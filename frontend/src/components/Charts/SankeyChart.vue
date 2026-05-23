<template>
  <div class="sankey-chart-container">
    <div v-show="isEmpty" class="empty-state">
      <IconifyIconOffline icon="ep:folder-opened" class="text-4xl text-gray-300 mb-2" />
      <p class="text-gray-400">暂无资产构成数据</p>
    </div>
    <div ref="chartRef" class="chart" :style="{ visibility: isEmpty ? 'hidden' : 'visible' }" />
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, watch, nextTick } from "vue";
import * as echarts from "echarts";

const props = defineProps<{
  data: { nodes: any[]; links: any[] };
  displayMode: "amount" | "percent" | "hidden";
}>();

const chartRef = ref<HTMLDivElement>();
let chart: echarts.ECharts | null = null;
const isEmpty = ref(true);
const totalValue = ref(0);
const containerHeight = ref(400);

function formatLabel(params: any) {
  const val = params.value ?? 0;
  if (props.displayMode === "hidden") return params.name;
  if (props.displayMode === "percent") {
    const pct = totalValue.value > 0
      ? ((val / totalValue.value) * 100).toFixed(1) + "%"
      : "0%";
    return `${params.name}\n${pct}`;
  }
  const amount = val >= 10000
    ? (val / 10000).toFixed(1) + "万"
    : val.toLocaleString();
  return `${params.name}\n¥${amount}`;
}

// ────────────── 颜色系统 ──────────────
function resolveCssVar(varName: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return value || "";
}

const NODE_COLOR_VARS: Record<string, string> = {
  总资产: "--color-primary",
  净资产: "--color-success",
  总负债: "--color-neutral",
  流动资金: "--tag-mint-green",
  投资理财: "--tag-periwinkle",
  固定资产: "--tag-warm-taupe",
  应收款: "--tag-stone-gray",
  保险项目: "--color-accent",
  活钱: "--tag-muted-blue",
  稳健底仓: "--tag-thistle",
  长期增值: "--color-primary",
  高风险博弈: "--color-danger",
  保险保障: "--color-accent",
  未配置资产: "--color-neutral",
  股票: "--asset-stock",
  基金: "--asset-fund",
  可转债: "--asset-bond",
  ETF: "--asset-etf",
  虚拟货币: "--asset-crypto",
  银行存款: "--asset-saving",
};

function getNodeColor(name: string): string {
  const varName = NODE_COLOR_VARS[name];
  if (varName) {
    const color = resolveCssVar(varName);
    if (color && /^#[0-9a-fA-F]{3,8}$/.test(color)) return color;
  }
  if (/贷|借|信用卡|负债/.test(name)) return resolveCssVar("--color-neutral") || "#8E8B82";
  return "#cccccc";
}

// ────────────── 手动布局核心 ──────────────
function computeManualLayout(
  nodes: any[],
  links: any[],
  chartWidth: number,
  levelCount: number,
  leftPad: number,
  rightPad: number
) {
  // 1. 构建邻接表及拓扑层级
  const outAdj: Record<string, string[]> = {};
  const inAdj: Record<string, string[]> = {};
  nodes.forEach((n) => {
    outAdj[n.name] = [];
    inAdj[n.name] = [];
  });
  links.forEach((l) => {
    outAdj[l.source].push(l.target);
    inAdj[l.target].push(l.source);
  });

  const nodeLevel: Record<string, number> = {};
  const queue: string[] = [];
  nodes.forEach((n) => {
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
    (outAdj[curr] || []).forEach((next) => {
      if (nodeLevel[next] === undefined) {
        nodeLevel[next] = nodeLevel[curr] + 1;
        queue.push(next);
      }
    });
  }

  // 2. 分支识别：从“总负债”向下游全部标记为负债
  const branchMap: Record<string, "asset" | "liability"> = {};
  function markLiability(name: string) {
    if (branchMap[name] === "liability") return;
    branchMap[name] = "liability";
    (outAdj[name] || []).forEach((child) => markLiability(child));
  }
  if (nodeLevel["总负债"] !== undefined) markLiability("总负债");
  nodes.forEach((n) => {
    if (!branchMap[n.name]) branchMap[n.name] = "asset";
  });

  // 3. 流量值（仅用于节点高度估算，不污染 data.value）
  const outFlow: Record<string, number> = {};
  const inFlow: Record<string, number> = {};
  nodes.forEach((n) => {
    outFlow[n.name] = 0;
    inFlow[n.name] = 0;
  });
  links.forEach((l) => {
    outFlow[l.source] = (outFlow[l.source] || 0) + l.value;
    inFlow[l.target] = (inFlow[l.target] || 0) + l.value;
  });
  const nodeFlow: Record<string, number> = {};
  nodes.forEach((n) => {
    nodeFlow[n.name] = Math.max(outFlow[n.name], inFlow[n.name]);
  });

  // 4. 计算列宽（动态适配）
  const drawWidth = chartWidth - leftPad - rightPad;
  const colWidth = levelCount > 1 ? drawWidth / (levelCount - 1) : drawWidth;

  // 5. 固定节点高度与间距
  const nodeHeight = 20;
  const gap = 10;
  const branchGap = 60; // 资产与负债分支的垂直隔离带

  // 6. 内部排序权重
  const orderWeight: Record<string, number> = {
    投资理财: 0, 固定资产: 1, 流动资金: 2,
    总资产: 0,
    净资产: 0, 总负债: 1,
    长期增值: 0,
    股票: 0, 未配置资产: 1, 房贷: 2, 借家人的钱: 3,
  };

  // 7. 按层级分组，并分配坐标
  const levelGroups = Object.entries(nodeLevel).reduce((acc, [name, lvl]) => {
    if (!acc[lvl]) acc[lvl] = [];
    acc[lvl].push(name);
    return acc;
  }, {} as Record<number, string[]>);

  const layouted: any[] = [];
  let globalMaxY = 0;

  Object.entries(levelGroups).forEach(([lvlStr, names]) => {
    const lvl = parseInt(lvlStr);
    const x = leftPad + lvl * colWidth; // 水平起点

    const assetNames = names.filter((n) => branchMap[n] === "asset");
    const liabilityNames = names.filter((n) => branchMap[n] === "liability");

    assetNames.sort((a, b) => (orderWeight[a] ?? 999) - (orderWeight[b] ?? 999));
    liabilityNames.sort((a, b) => (orderWeight[a] ?? 999) - (orderWeight[b] ?? 999));

    let yCursor = 20; // 从顶部开始

    // 资产分支
    assetNames.forEach((name) => {
      const rawNode = nodes.find((n) => n.name === name)!;
      layouted.push({
        ...rawNode,
        name,
        x,
        y: yCursor,
        value: nodeFlow[name] || 0,
        itemStyle: { color: getNodeColor(name) },
        label: {
          position: lvl === 0 ? "left" : "right",
          distance: 6,
        },
      });
      yCursor += nodeHeight + gap;
    });

    // 负债分支：在资产分支下方，强制物理隔离
    if (liabilityNames.length > 0) {
      yCursor += branchGap - gap; // 跳过隔离带
    }
    liabilityNames.forEach((name) => {
      const rawNode = nodes.find((n) => n.name === name)!;
      layouted.push({
        ...rawNode,
        name,
        x,
        y: yCursor,
        value: nodeFlow[name] || 0,
        itemStyle: { color: getNodeColor(name) },
        label: {
          position: "right",
          distance: 6,
        },
      });
      yCursor += nodeHeight + gap;
    });

    globalMaxY = Math.max(globalMaxY, yCursor);
  });

  return { nodes: layouted, maxY: globalMaxY };
}

function renderChart() {
  if (!chartRef.value) return;
  if (!props.data || !Array.isArray(props.data.nodes) || !Array.isArray(props.data.links)) return;

  const hasData = props.data.nodes.length > 0 && props.data.links.length > 0;
  isEmpty.value = !hasData;

  if (!hasData) {
    chart?.dispose();
    chart = null;
    return;
  }

  if (!chart) {
    chart = echarts.init(chartRef.value);
  }

  // 获取图表容器尺寸
  const chartWidth = chartRef.value.clientWidth;
  const leftPad = 100;
  const rightPad = 80;
  const maxLevel = Math.max(
    ...props.data.nodes.map((n) => {
      // 简单映射层级，与 computeManualLayout 中的计算保持一致
      // 这里预计算一下最大层级，用于计算列宽
      const inAdj: Record<string, string[]> = {};
      props.data.nodes.forEach((n) => { inAdj[n.name] = []; });
      props.data.links.forEach((l) => {
        if (!inAdj[l.target]) inAdj[l.target] = [];
        inAdj[l.target].push(l.source);
      });
      const queue: string[] = [];
      const levels: Record<string, number> = {};
      props.data.nodes.forEach((n) => {
        if (inAdj[n.name]?.length === 0) {
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
        props.data.links.forEach((l) => {
          if (l.source === curr && levels[l.target] === undefined) {
            levels[l.target] = levels[curr] + 1;
            queue.push(l.target);
          }
        });
      }
      return levels[n.name] ?? 2;
    })
  ) || 0;

  const { nodes: layoutNodes, maxY } = computeManualLayout(
    props.data.nodes,
    props.data.links,
    chartWidth,
    maxLevel,
    leftPad,
    rightPad
  );

  // 动态调整容器高度
  containerHeight.value = Math.max(maxY + 40, 400);

  const totalNode = layoutNodes.find((n) => n.name === "总资产");
  totalValue.value = totalNode?.value || 0;

  chart.setOption(
    {
      tooltip: {
        trigger: "item",
        triggerOn: "mousemove",
        backgroundColor: "rgba(255,255,255,0.95)",
        borderColor: "#e5e7eb",
        textStyle: { color: "#333", fontSize: 12 },
        formatter: (params: any) => {
          if (params.dataType === "node") {
            const disp =
              props.displayMode === "hidden"
                ? "***"
                : "¥" + (params.value || 0).toLocaleString();
            return `${params.name}<br/>${disp}`;
          }
          return `${params.data.source} → ${params.data.target}<br/>¥${(params.value || 0).toLocaleString()}`;
        },
      },
      series: [
        {
          type: "sankey",
          layout: "none", // 手动坐标
          data: layoutNodes,
          links: props.data.links,
          emphasis: { focus: "adjacency" },
          lineStyle: {
            color: "gradient",
            curveness: 0.3,
            opacity: 0.5,
          },
          nodeWidth: 14,
          nodeGap: 10,
          label: {
            show: true,
            fontSize: 12,
            lineHeight: 16,
            formatter: formatLabel,
            overflow: "truncate",
            width: 130,
            // position 由节点级覆盖
          },
          left: leftPad,
          right: rightPad,
          top: 10,
          bottom: 10,
        },
      ],
    },
    true
  );
}

watch(
  () => [props.data.nodes, props.data.links, props.displayMode],
  () => nextTick(renderChart),
  { deep: true, immediate: true }
);

const resizeHandler = () => chart?.resize();
window.addEventListener("resize", resizeHandler);

onBeforeUnmount(() => {
  chart?.dispose();
  window.removeEventListener("resize", resizeHandler);
});
</script>
<style scoped>
.sankey-chart-container {
  position: relative;
  width: 100%;
  /* 绑定动态计算的高度 */
  height: v-bind(containerHeight + "px");
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
