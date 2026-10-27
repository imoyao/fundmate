/**
 * 拥挤度表格的展示纯函数（#980 批 B5 从 `CrowdingTable.vue` 抽出）。
 *
 * 抽出的理由不只是「让 .vue 变短」：这四个函数决定的是**同一张表里四处数字的写法**
 * （`--` 占位、一位小数、正负号、亿单位）。它们原先散在 `.vue` 里，只能靠肉眼看表，
 * 而「缺数据显示 `--` 而不是 0」这条纪律一旦在某一列写漏，界面上看不出错，
 * 只会让用户把「没数据」读成「真的是 0」。
 *
 * 注意：`formatValue`（乖离率自适应小数）仍留在 `@/utils/temperatureFormat`，
 * 本模块不转手——它带着 `@/constants` 的依赖，转手会让这里的单测连带整棵常量表。
 */

/** 行业乖离率窗口（简单 MA 口径，与后端 `sw_industry_source.BIAS_WINDOWS` 对齐） */
export const BIAS_WINDOWS = [6, 20, 60];

/** 百分比展示：null/undefined → 「--」，否则一位小数 + %（外部源与自算值共用） */
export function fmtPct(v: number | null | undefined): string {
  return v == null ? "--" : `${Number(v).toFixed(1)}%`;
}

/** 百万大单着色：净买入红、净卖出绿（沿用全站涨跌配色语义）；0 与缺数据都不着色 */
export function bigOrderClass(v: number | null | undefined): string {
  if (v == null || v === 0) return "";
  return v > 0 ? "big-order--in" : "big-order--out";
}

/** 百万大单文案：带正负号 + 「亿」；缺数据显示「--」，不显示 0.0 亿 */
export function bigOrderText(v: number | null | undefined): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}亿`;
}
