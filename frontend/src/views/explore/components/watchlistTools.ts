/**
 * 探市观察列表的「深度分析」外链清单（#980 批 B5 从 `ExploreWatchlistTable.vue` 抽出）。
 *
 * 纯函数，没有运行时依赖，便于单测钉住「哪些类型多一个天天的入口」——
 * 这条规则以前藏在 `.vue` 的 `if (type === "fund" || type === "etf")` 里，
 * 改 `.vue` 时很容易顺手写成 `!==`。
 */

export type AnalysisTool = { key: string; label: string };

/**
 * 该资产类型可用的深度分析站点。
 *
 * 基金 / ETF 多一个天天基金：它是唯一能查基金持仓明细与历史净值曲线的地方，
 * 而股票 / 债券 / 指数在天天基金上没有对应页面。
 */
export function getAvailableTools(type: string): AnalysisTool[] {
  const tools: AnalysisTool[] = [
    { key: "xueqiu", label: "雪球社区" },
    { key: "eastmoney", label: "东方财富" }
  ];
  if (type === "fund" || type === "etf") {
    tools.push({ key: "tiantian", label: "天天基金" });
  }
  return tools;
}
