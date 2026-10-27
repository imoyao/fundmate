/**
 * 桑基图的 ECharts option 组装（#980 批 B8 从 `Charts/SankeyChart.vue` 抽出）。
 *
 * 与 `sankeyLayout.ts` 的分工：那边算**几何**（节点 x/y、高度、颜色），
 * 这边只把这些结果填进 ECharts 的配置形状。拆成两个文件是因为几何是纯数学、
 * 值得单测；option 是配置字面量、改它通常是调视觉，两者改动的理由完全不同。
 */
import type { SankeyLink } from "./sankeyLayout";
import { formatNodeLabel, type VarReader } from "./sankeyLayout";

export type DisplayMode = "amount" | "percent" | "hidden";

export interface SankeyOptionInput {
  links: SankeyLink[];
  /** `computeManualLayout` 的输出（节点带 x/y/颜色） */
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
 * `layout: "none"` 是**必须**的：节点坐标已经手算好，交给 ECharts 自动布局会把
 * 资产 / 负债两支混在一起（见 `sankeyLayout.computeManualLayout` 的说明）。
 */
export function buildSankeyOption(input: SankeyOptionInput) {
  const { links, layoutNodes, displayMode, totalValue, leftPad, rightPad } =
    input;
  const readVar = input.readVar;

  return {
    tooltip: {
      trigger: "item",
      triggerOn: "mousemove",
      backgroundColor: "rgba(255,255,255,0.95)",
      borderColor: readVar("--border-light"),
      textStyle: { color: readVar("--text-primary"), fontSize: 12 },
      formatter: (params: any) => {
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
        layout: "none",
        data: layoutNodes,
        links,
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
          formatter: (params: { name: string; value?: number }) =>
            formatNodeLabel(params, displayMode, totalValue),
          overflow: "truncate",
          width: 130
        },
        left: leftPad,
        right: rightPad,
        top: 10,
        bottom: 10
      }
    ]
  };
}
