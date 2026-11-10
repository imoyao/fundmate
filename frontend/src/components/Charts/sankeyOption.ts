/**
 * 桑基图的 ECharts option 组装（#980 批 B8 从 `Charts/SankeyChart.vue` 抽出）。
 *
 * 与 `sankeyLayout.ts` 的分工：那边算**节点数据**（顺序、流量、颜色、标签朝向、
 * 最小绘图高度），这边只把这些结果填进 ECharts 的配置形状。拆成两个文件是因为
 * 前者是纯函数、值得单测；option 是配置字面量、改它通常是调视觉，两者改动的
 * 理由完全不同。
 */
import { CHART_FALLBACKS } from "@/composables/echarts/theme";
import type { ChartCallbackParam } from "@/types/chart";
import type { SankeyLink } from "./sankeyLayout";
import {
  formatNodeLabel,
  SANKEY_NODE_GAP,
  type VarReader
} from "./sankeyLayout";

export type DisplayMode = "amount" | "percent" | "hidden";

export interface SankeyOptionInput {
  links: SankeyLink[];
  /** `computeSankeyNodes` 的输出（节点带流量、颜色、标签朝向） */
  layoutNodes: Record<string, unknown>[];
  displayMode: DisplayMode;
  /** 「总资产」节点的值，percent 模式的分母 */
  totalValue: number;
  leftPad: number;
  rightPad: number;
  readVar: VarReader;
}

/**
 * 组装桑基图 option。
 *
 * ⚠️ **不要再写 `layout: "none"`**：ECharts 6 已删掉这个选项（6.1.0 的
 * `SankeySeriesOption` 无 `layout` 字段，布局阶段无条件跑自动布局），旧配置
 * 是无效配置，还让人误以为节点坐标是手算生效的。分层语义靠 `data` 顺序 +
 * 显式 `depth` 维持，详见 `sankeyLayout.ts` 的文件头。
 *
 * ⚠️ **下面这组形态参数是用户认可参考实现的同款，改动前先看 2×2 受控对照**：
 *   - `nodeWidth: 7` + `nodeGap: 16`：粗节点（旧 14 / 36）配合大间距会在中间列
 *     撑出一块楔形空白，就是用户指出的「多出来一截」；
 *   - `layoutIterations: 0`：默认 32 次重心松弛会把节点拉向下游重心、破坏
 *     barycenter 排好的上下次序，是 X 形斜穿的放大器；
 *   - `nodeAlign: 'justify'`：在**所有节点都带显式 depth** 时是安全的，
 *     `moveSinksRight()` 会跳过它们；此前旧拓扑下的「必须 `left`」是局部结论，
 *     起因是那张图的汇点深度不一致，不能照搬；
 *   - `curveness: 0.5` + `opacity: 0.42`：流量带柔和半透明，节点细竖条不再抢视线。
 * 结论：**X 形交叉由节点顺序造成，尖楔由渲染配置造成，两者独立**，只改一边都不够。
 *
 * ⚠️ 标签是**单行 rich**（`{name|…}  {val|…}`），不设 `backgroundColor` / `padding`。
 * 旧版为了可读性给两行标签加了卡片色背景块，结果白底长条盖住流量带；现在显式给
 * `rich.name` / `rich.val` 文字色即可（ECharts 按节点色自动挑对比色才会出白字压浅带）。
 * 同样不要 `width` + `overflow: "truncate"`，它会把标签撑成一条白长条并挤掉数值。
 */
export function buildSankeyOption(input: SankeyOptionInput) {
  const { links, layoutNodes, displayMode, totalValue, leftPad, rightPad } =
    input;
  const readVar = input.readVar;
  const textPrimary = readVar("--text-primary") || CHART_FALLBACKS.textPrimary;
  const textSecondary =
    readVar("--text-secondary") || CHART_FALLBACKS.textSecondary;

  return {
    tooltip: {
      trigger: "item",
      triggerOn: "mousemove",
      backgroundColor: "rgba(255,255,255,0.95)",
      borderColor: readVar("--border-light") || CHART_FALLBACKS.borderLight,
      textStyle: {
        color: textPrimary,
        fontSize: 12
      },
      formatter: (params: ChartCallbackParam) => {
        if (params.dataType === "node") {
          const disp =
            displayMode === "hidden"
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
        data: layoutNodes,
        links,
        draggable: false,
        emphasis: { focus: "adjacency", lineStyle: { opacity: 0.68 } },
        lineStyle: {
          color: "gradient",
          curveness: 0.5,
          opacity: 0.42
        },
        itemStyle: { borderWidth: 0 },
        // 所有节点带显式 depth ⇒ justify 不会把汇点推走；形态与参考实现一致
        nodeAlign: "justify",
        layoutIterations: 0,
        nodeWidth: 7,
        nodeGap: SANKEY_NODE_GAP,
        label: {
          show: true,
          position: "right",
          distance: 8,
          fontSize: 12,
          formatter: (params: { name: string; value?: number }) =>
            formatNodeLabel(params, displayMode, totalValue),
          color: textPrimary,
          rich: {
            name: { fontSize: 12, color: textPrimary },
            val: { fontSize: 12, color: textSecondary, fontWeight: 700 }
          }
        },
        left: leftPad,
        right: rightPad,
        top: 12,
        bottom: 12
      }
    ]
  };
}
