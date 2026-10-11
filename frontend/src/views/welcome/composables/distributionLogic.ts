/**
 * 首页「资产构成分布」环形图的数据口径（#1955）。
 *
 * 抽成独立模块而非写在 .vue 里：口径选择是需要被回归测试钉住的行为，
 * `.vue` 的 computed 在 node 环境下测不了（vitest environment: node）。
 *
 * 缺陷背景（实测本机真实库 family_id=1，154 笔持仓）：
 * 原实现消费 `summary.market_distribution`——按持仓 `market` 分组，
 * 而全部持仓都是 `CN_A`，实际只回 `{"CN_A": 659104.65}` 一个键。
 * 环形图单扇区占满整圈 + 索引 0 取到品牌红 `--chart-01`(#e34f38)
 * ⇒ 首页出现一个「完整的红色圆环」。
 *
 * **数据是真的，是取数维度选错了。** 改为按资产大类分组：
 * `distributions.category_distribution`，各项之和 === `total_assets`，
 * 与看板左侧「家庭总资产」同一口径。
 */
import type { DistributionsData } from "@/api/summary";

/**
 * 资产大类 → 语义色 CSS 变量名。
 *
 * 取自 `SankeyChart.vue` 的 `NODE_COLOR_VARS`（同一套大类用同一套色），
 * 保证首页环形图与资产总览桑基图对「流动资金 / 投资理财 / 固定资产 / 应收款」
 * 配色一致——否则同一个大类在两页两色，用户会当成两类资产。
 *
 * 不传 colorMap 时 `AssetAllocationDonut` 会按数据索引取 `--chart-01~08`，
 * 首个扇区恒为品牌红。资产构成没有「涨跌」语义，用品牌红还会和涨红跌绿的
 * 惯例撞车，故必须显式指定。
 */
export const CATEGORY_COLOR_MAP: Record<string, string> = {
  流动资金: "--palette-mint-green",
  投资理财: "--palette-periwinkle",
  固定资产: "--palette-warm-taupe",
  应收款: "--palette-stone-gray"
};

/**
 * 环形图入参：`[{name, value}]`
 *
 * 请求失败（distributions 为 null）或后端返回空数组时一律给`[]`，
 * 由 `AssetAllocationDonut` 自行走空态（「暂无数据」居中显示），
 * 不在此处抛错——一张次要图表的数据不该让整块看板崩掉。
 */
export function buildDistributionData(
  distributions: DistributionsData | null | undefined
): Array<{ name: string; value: number }> {
  return distributions?.category_distribution ?? [];
}
