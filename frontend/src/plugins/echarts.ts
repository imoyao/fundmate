import type { App } from "vue";
import * as echarts from "echarts/core";
import { PieChart, BarChart, LineChart, SankeyChart } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import {
  GridComponent,
  LegendComponent,
  GraphicComponent,
  TooltipComponent,
  TitleComponent
} from "echarts/components";

const { use } = echarts;

// 仅注册项目实际使用的图表类型和组件（经 2026-08-04 全量审计）
// 移除：SVGRenderer, PolarComponent, ToolboxComponent, DataZoomComponent, VisualMapComponent
// 保留 TitleComponent：welcome/index.vue 资产分布饼图空状态用 title 显示「暂无资产数据」，
// 误删会导致 [ECharts] Component title is used but not imported，空状态标题不渲染。
use([
  PieChart,
  BarChart,
  LineChart,
  SankeyChart,
  CanvasRenderer,
  GridComponent,
  LegendComponent,
  GraphicComponent, // 用于 echarts.graphic.LinearGradient 面积渐变
  TooltipComponent,
  TitleComponent
]);

/**
 * @description 按需引入echarts，具体看 https://echarts.apache.org/handbook/zh/basics/import/#%E5%9C%A8-typescript-%E4%B8%AD%E6%8C%89%E9%9C%80%E5%BC%95%E5%85%A5
 * @see 温馨提示：必须将 `$echarts` 添加到全局 `globalProperties` ，具体看 https://pure-admin-utils.netlify.app/hooks/useECharts/useECharts#%E4%BD%BF%E7%94%A8%E5%89%8D%E6%8F%90
 */
export function useEcharts(app: App) {
  app.config.globalProperties.$echarts = echarts;
}

export default echarts;
