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
 * ⚠️ 这里曾经写「且慢没有官方调仓接口」，那是**探错端点族**得出的错结论：当时只试了
 * `qieman.com/pmapi/**`（五个候选路径都落回 SPA HTML），从未试 `/alfa/v1/graphql`。
 * 官方调仓接口确实存在且匿名可取（详见后端 `qieman_advisor_adapter` 的模块注释）。
 *
 * 现在的两档来源：
 *
 * - `qieman_official` —— 官方调仓（主理人原文 + 逐基金动作），不需要任何声明；
 * - `qieman` —— 我们按持仓快照序列推导的（只保留给官方接口覆盖不到的计划型组合，
 *   如 `LONG_WIN` / `LONG_WIN_S`）。
 *
 * 只要有一组来自推导，就必须挂声明——不写就等于冒充官方数据。
 * 按 `source` 判定而**不是**按平台名硬编码：同一平台两种来源并存正是本次换源的形态，
 * 判据跟着数据走才不会漂移。
 */
export function derivedFromSnapshots(
  groups: Pick<AdvisorAdjustGroup, "source">[]
): boolean {
  return groups.some(group => group.source === "qieman");
}

/**
 * 空态文案。
 *
 * 且慢的空态必须解释「为什么没有」：官方接口只覆盖 `alfa/portfolio` 命名空间，
 * 计划型组合（`LONG_WIN` 等）落回快照推导，而推导至少要两份快照才比得出来。
 * 只写「暂无调仓记录」会让用户以为功能坏了——它可能只是还没攒够数据。
 */
export function adjustEmptyHint(platform: string | null | undefined): string {
  return platform === "QIEMAN"
    ? "暂无调仓记录（且慢官方接口未收录该组合，改由持仓快照推导，需累积 ≥2 次快照）"
    : "暂无调仓记录";
}
