/**
 * 详情页「主理人调仓」的展示口径（纯函数，可单测）。
 *
 * 为什么单列而不是留在 .vue 里：`<script setup>` 里的 `computed` 测不到——组件测试
 * 要起 jsdom + 挂载，而这里要钉的只是「什么时候该挂口径声明」「空态说什么」这两条
 * 判断。抽出来之后它们是纯字符串 / 布尔，可以直接断言。
 */
import type { AdvisorAdjustGroup } from "@/api/funds";

/** 详情页展示的调仓组数：与自选速览抽屉同档（3 组）。再多会把区块拉长。 */
export const ADJUST_LIMIT = 3;

/**
 * 是否含「由持仓快照推导」的记录。
 *
 * 且慢**没有官方调仓接口**（`qieman.com/pmapi/**` 五个候选路径全返回 SPA HTML，
 * MCP 69 个工具里也没有调仓 / 交易历史工具），库里的记录是用持仓快照序列推导的。
 * 只要有一组来自推导，就必须挂声明——不写就等于冒充官方数据。
 *
 * 按 `source` 判定而**不是**按平台名硬编码：天天基金有官方接口（`tiantian`），
 * 同一平台将来也可能改口径，判据跟着数据走才不会漂移。
 */
export function derivedFromSnapshots(
  groups: Pick<AdvisorAdjustGroup, "source">[]
): boolean {
  return groups.some(group => group.source === "qieman");
}

/**
 * 空态文案。
 *
 * 且慢的空态必须解释「为什么没有」：记录由快照推导，至少两次快照才比得出来。
 * 只写「暂无调仓记录」会让用户以为功能坏了——而它只是还没攒够数据。
 */
export function adjustEmptyHint(platform: string | null | undefined): string {
  return platform === "QIEMAN"
    ? "暂无调仓记录（且慢按持仓快照推导，需累积 ≥2 次快照）"
    : "暂无调仓记录";
}
