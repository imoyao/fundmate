import type { App } from "vue";
import * as echarts from "echarts/core";
import {
  PieChart,
  BarChart,
  LineChart,
  SankeyChart,
  CandlestickChart,
  ScatterChart
} from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import {
  GridComponent,
  LegendComponent,
  GraphicComponent,
  TooltipComponent,
  TitleComponent,
  MarkLineComponent
} from "echarts/components";

const { use } = echarts;

// 仅注册项目实际使用的图表类型和组件。
//
// ⚠️ 这份清单**不是**一次审计就完事的：审计只覆盖当时存在的用法，之后每个新增
// series / 组件都必须回来补登记，否则 ECharts 会「静默不画」——控制台报
// `Series X is used but not imported`，图照常渲染、唯独缺那一层，没有任何
// 页面级异常。#2453：走势图的买卖点（scatter）+ 清仓轮次竖线（markLine）+
// 场内 K 线（candlestick）就是踩的这条线——三者上了线但从没画出来过。
//
// 对账（2026-10-21，#2453 复盘后全项目复查）：
//   line ×7 / bar ×4 / pie ×2 / sankey ×1 → LineChart / BarChart / PieChart / SankeyChart
//   candlestick ×1（详情页走势 K 线视图）  → CandlestickChart（本次补）
//   scatter ×2（详情页走势买卖点）        → ScatterChart（本次补）
//   markLine ×3（走势清仓轮次 / 累计收益面板 / 探市温度图）→ MarkLineComponent（本次补）
//
// 移除：SVGRenderer, PolarComponent, ToolboxComponent, DataZoomComponent, VisualMapComponent
// 保留 TitleComponent：welcome/index.vue 资产分布饼图空状态用 title 显示「暂无资产数据」，
// 误删会导致 [ECharts] Component title is used but not imported，空状态标题不渲染。
use([
  PieChart,
  BarChart,
  LineChart,
  SankeyChart,
  CandlestickChart,
  ScatterChart,
  CanvasRenderer,
  GridComponent,
  LegendComponent,
  GraphicComponent, // 用于 echarts.graphic.LinearGradient 面积渐变
  TooltipComponent,
  TitleComponent,
  MarkLineComponent
]);

/**
 * @description 按需引入echarts，具体看 https://echarts.apache.org/handbook/zh/basics/import/#%E5%9C%A8-typescript-%E4%B8%AD%E6%8C%89%E9%9C%80%E5%BC%95%E5%85%A5
 * @see 温馨提示：必须将 `$echarts` 添加到全局 `globalProperties` ，具体看 https://pure-admin-utils.netlify.app/hooks/useECharts/useECharts#%E4%BD%BF%E7%94%A8%E5%89%8D%E6%8F%90
 */
export function useEcharts(app: App) {
  app.config.globalProperties.$echarts = echarts;
}

export default echarts;
