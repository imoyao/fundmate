/**
 * 资产总览页的接口载荷最小契约（#2879 第八刀）。
 *
 * 这四个金额是 `/api/summary/` 的固定字段；桑基图的 nodes / links 由
 * `SankeyChart` 直接交给 echarts，页面层只负责透传，因此元素按 `unknown`
 * 处理——既不用 `any` 放行，也不假装页面知道图元素的形状。
 */

/** /api/summary/ 的 data：页面只读以下四档金额 */
export interface SummaryPayload {
  total_assets_cny?: number;
  total_liabilities_cny?: number;
  net_assets_cny?: number;
  total_pnl_cny?: number;
}

/** /api/sankey/ 的 data：nodes / links 仅透传，不解析元素 */
export interface SankeyPayload {
  nodes?: unknown[];
  links?: unknown[];
}
