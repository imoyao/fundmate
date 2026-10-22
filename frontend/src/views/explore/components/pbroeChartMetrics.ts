// frontend/src/views/explore/components/pbroeChartMetrics.ts
/**
 * 行业 PB-ROE 散点的数据口径（#2481）。
 *
 * 两个不许肉眼发现的坑：
 * 1. **负 ROE 必须保留**——房地产实测 -16.78，在 PB-ROE 模型下负盈利行业
 *   照样是图上的有效点；旧惯性思维「收益率负数剔掉」会把整个地产/亏损行业
 *   从图上抹掉，且散点图不报错（少几个点看不出来）；
 * 2. **NaN 点防御**——上游形态异常时 roe/pb 可能是 null，ECharts 对 null
 *   数值点直接不画但不告警；这里在进 option 前过滤，并让「过滤后为空」
 *   与「本来就没数据」走同一条空态提示。
 */

import type { IndustryPbroePoint } from "@/api/market";

/** 有效散点：roe/pb 均非 null（负值有效，不过滤） */
export function toScatterPoints(
  series: IndustryPbroePoint[] | null | undefined
): IndustryPbroePoint[] {
  return (series ?? []).filter(p => p.roe != null && p.pb != null);
}

/** 是否有可画数据（过滤后非空） */
export function hasScatterPoints(
  series: IndustryPbroePoint[] | null | undefined
): boolean {
  return toScatterPoints(series).length > 0;
}
