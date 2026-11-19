/**
 * 把「挂错标的」「无归属」的组并进域 F 的只读快照（2026-11-13 / #3126）。
 *
 * ## 为什么在 loader 里合并，而不是多开一个数据源
 *
 * 域 F 的界面（阶段面板 / 组卡 / 抽屉执行区）全部按 `danglingRefs.groups` +
 * `bucketByStage` 渲染；错挂组、无归属组与悬空组**结构兼容**（同一张卡、
 * 同一个动作面），只多个别字段（错挂：`mislinked` / `fix_mode` /
 * `wrong_positions`；无归属：`unowned`）。若各另起一个数据源，
 * 就要在队列、抽屉、阶段面板、执行区各增加一条分支，而 `ReconQueueDetail.vue`
 * 已经贴着 400 行门禁（没有余量）—— 四处分叉换不来任何用户可见的差别，
 * 只会让「一个数据只有一个可用入口」这条约束失效。
 *
 * ## 计数必须跟着涨
 *
 * `total` / `group_count` / `fixable_count` 是分诊卡的条数口径（和式不变量：
 * 卡上条数 = 队列项 count 之和）。合并 groups 却不调这几个数，就是「列出来了但
 * 数字里没有它」的静默漏算 —— 故这里显式加，且只加与该类组有关的项：
 * `null_symbol` / `null_trade_date` / `batches` 属于悬空口径，两类组都不贡献
 * （错挂组没有导入批次语义；无归属组按契约自带 batches，但不并入悬空批次数）。
 *
 * `fixable_count` 对无归属组**刻意不涨**：契约里该值恒 0 —— 这类组没有可挂回的
 * 持仓指针，「可直接回补」的口径不适用；rebuild 也只对「净额 > 0 且同账本无同标的
 * 持仓」的组可用，不能算进「可直接修」。把它们算进「可修」会让分诊卡宣称能处理
 * 一个实际要按组判定的阶段（仿上方 mislinked 只加 `fixable` 组的
 * 计数纪律，方向相反：这里是**一类都不加**）。
 *
 * 批次数 `batch_count` 不变：并入只进 groups，不动悬空批次的清单与计数。
 */

import type {
  DanglingRefList,
  MislinkedRefList,
  UnownedRefList
} from "@/api/reconciliation";

/** 合并后的快照；三个接口都没数据时返回 null（与既有「无数据」表达一致） */
export function mergeDanglingLists(
  base: DanglingRefList | null | undefined,
  mislinked: MislinkedRefList | null | undefined,
  unowned?: UnownedRefList | null | undefined
): DanglingRefList | null {
  const extra = Array.isArray(mislinked?.groups) ? mislinked.groups : [];
  const unownedExtra = Array.isArray(unowned?.groups) ? unowned.groups : [];
  if (!base) return null;
  if (extra.length === 0 && unownedExtra.length === 0) return base;
  const fixableExtra = extra
    .filter(g => g.fixable)
    .reduce((sum, g) => sum + g.txn_count, 0);
  return {
    ...base,
    total:
      base.total +
      (mislinked?.total ?? extra.length) +
      (unowned?.total ?? unownedExtra.length),
    group_count: base.group_count + extra.length + unownedExtra.length,
    // 无归属组的 fixable 恒 false，且不进「可回补」口径（见文件头），不参与求和
    fixable_count: base.fixable_count + fixableExtra,
    groups: [...base.groups, ...extra, ...unownedExtra]
  };
}
