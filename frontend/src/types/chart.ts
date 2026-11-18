/**
 * 图表层的共享类型（#2879）。
 *
 * 各页的 `formatter` / `color` 回调此前一律写 `params: any`，实际读取的字段
 * 只有下面这几个。逐个登记字段、不开放索引签名：写错字段名要当场报错，
 * 而不是静默得到 unknown（那只是把 any 换个写法留在原地）。
 *
 * 本类型只描述「本仓代码读取的形状」，不是 echarts 的完整回调参数定义。
 */

export interface SankeyLinkData {
  source?: string;
  target?: string;
  value?: number | string | null;
}

export interface ChartCallbackParam {
  name?: string;
  value?: number | string | null;
  percent?: number;
  dataIndex?: number;
  dataType?: string;
  data?: SankeyLinkData;
  seriesName?: string;
  axisValue?: string | number;
  color?: string;
  marker?: string;
}

/** `echarts.init()` 的实例类型；图表 ref 统一用它，不再用 any 兜底。 */
export type ChartInstance = ReturnType<typeof import("echarts/core").init>;
