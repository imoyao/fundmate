/**
 * 把「挂错标的」的组并进域 F 的只读快照（2026-11-13）。
 *
 * ## 为什么在 loader 里合并，而不是多开一个数据源
 *
 * 域 F 的界面（阶段面板 / 组卡 / 抽屉执行区）全部按 `danglingRefs.groups` +
 * `bucketByStage` 渲染；错挂组与悬空组**结构兼容**（同一张卡、同一个动作面），
 * 只多三个字段（`mislinked` / `fix_mode` / `wrong_positions`）。若另起一个
 * `mislinked` 数据源，就要在队列、抽屉、阶段面板、执行区各增加一条分支，
 * 而 `ReconQueueDetail.vue` 已经贴着 400 行门禁（没有余量）—— 四处分叉换不来
 * 任何用户可见的差别，只会让「一个数据只有一个可用入口」这条约束失效。
 *
 * ## 计数必须跟着涨
 *
 * `total` / `group_count` / `fixable_count` 是分诊卡的条数口径（和式不变量：
 * 卡上条数 = 队列项 count 之和）。合并 groups 却不调这三个数，就是「列出来了但
 * 数字里没有它」的静默漏算 —— 故这里显式加，且只加与错挂组有关的项：
 * `null_symbol` / `null_trade_date` / `batches` 属于悬空口径，错挂组两个都不贡献。
 *
 * 批次数 `batch_count` 也不变：错挂组没有导入批次语义（按标的归属聚合），
 * 它们的 `batch_id` 是 null。
 */

import type { DanglingRefList, MislinkedRefList } from "@/api/reconciliation";

/** 合并后的快照；两个接口都没数据时返回 null（与既有「无数据」表达一致） */
export function mergeDanglingLists(
  base: DanglingRefList | null | undefined,
  mislinked: MislinkedRefList | null | undefined
): DanglingRefList | null {
  const extra = Array.isArray(mislinked?.groups) ? mislinked.groups : [];
  if (!base) return null;
  if (extra.length === 0) return base;
  const fixableExtra = extra
    .filter(g => g.fixable)
    .reduce((sum, g) => sum + g.txn_count, 0);
  return {
    ...base,
    total: base.total + (mislinked?.total ?? extra.length),
    group_count: base.group_count + extra.length,
    fixable_count: base.fixable_count + fixableExtra,
    groups: [...base.groups, ...extra]
  };
}
