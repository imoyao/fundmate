/**
 * 详情页「主理人调仓」的展示口径（纯函数，可单测）。
 *
 * 为什么单列而不是留在 .vue 里：`<script setup>` 里的 `computed` 测不到——组件测试
 * 要起 jsdom + 挂载，而这里要钉的只是「什么时候该挂口径声明」「空态说什么」这两条
 * 判断。抽出来之后它们是纯字符串 / 布尔，可以直接断言。
 */
import type { AdvisorAdjustGroup } from "@/api/funds";
import { advisorOpTone } from "@/utils/advisorAdjust";

/**
 * 详情页展示的调仓组数（一组 = 一个调仓日）。
 *
 * 与自选速览抽屉**刻意不同档**：抽屉是提示位，3 组（再多会把下方的持仓本身挤下去）；
 * 详情页的语境就是「看这个组合」，缺的是历史而不是篇幅。后端上限 50。
 */
export const ADJUST_LIMIT = 10;

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

/**
 * 来源码 → 中文标注（写在时间轴每一节上）。
 *
 * 「快照推导」四个字是判据的一部分：它让用户一眼看出这条记录不是平台官方披露的，
 * 与卡片底部的免责声明互为表里（`derivedFromSnapshots` 决定要不要挂那段声明）。
 * 未知来源原样透出，不吞掉——新来源接入时宁可显示英文码，也不要伪装成已知来源。
 */
const SOURCE_LABEL: Record<string, string> = {
  qieman_official: "官方披露",
  qieman: "快照推导",
  tiantian: "天天官方",
  qieman_manual: "手动导入"
};

export function sourceLabelOf(source: string): string {
  return SOURCE_LABEL[source] ?? source;
}

/**
 * 一次调仓里的加 / 减仓计数。
 *
 * 两套用词都归到同一档（`advisorOpTone` 里已收口）：天天基金 / 快照推导说
 * 「加仓、减仓」，且慢官方说「调入、调增、调出、调减」。漏掉任一套的后果不是报错，
 * 而是整片计数变成 0——用户看到「加仓 0、减仓 0」会以为调仓记录坏了。
 * 「持平」与未知动作不计入两侧（它们不是方向）。
 */
export function countByTone(group: AdvisorAdjustGroup): {
  add: number;
  cut: number;
} {
  let add = 0;
  let cut = 0;
  for (const item of group.items) {
    const tone = advisorOpTone(item.op_name);
    if (tone === "add") add += 1;
    else if (tone === "cut") cut += 1;
  }
  return { add, cut };
}
