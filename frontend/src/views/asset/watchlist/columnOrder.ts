/**
 * 自选表格「列序重建」纯函数（2026-10-30 抽，修表头整段重复列）。
 *
 * WHY 独立文件：重建算法无 IO、无 Vue 状态，抽出来才能被 vitest 直接单测，
 * 不必连带加载 composable 的 localforage / http 依赖链（同 `watchlistColumnPrefs` 的做法）。
 *
 * ## 背景：表头同一列出现两次（用户实测）
 *
 * 持久化的 `order` **只包含用户当时可见的列**——写入侧是
 * `useWatchlistStickyLayout.headerKeys()`，取的是过滤后的 `dataColumns`，
 * 通常只有 7~8 个 key；而可拖拽槽位约 50 个。
 *
 * 旧实现把这份「部分顺序」当成「全量顺序」按槽位 shift：
 *
 * ```ts
 * const queue = [...orderedKeys];                       // 只有 7~8 个
 * return defs.map(d => (d.draggable ? queue.shift() ?? d : d)); // 队列空 → 保留原位
 * ```
 *
 * ⇒ 拖拽区前 N 个槽位被这 N 列占掉，而它们**自己的原生槽位**又照旧渲染自己
 * ⇒ 同一列出现两次。用户看到的是「走势 / 持有数量 / 持仓市值 / 添加后涨幅 /
 * 持仓收益」各两遍、当日盈亏一前一后。
 *
 * ## 现口径
 *
 * 先把**全量可拖拽列**凑齐，再逐槽位填入：
 * 1) 用户排过的 key 按 `order` 顺序在前（重复 key、定义里已删除的 key、非拖拽 key 一律丢弃）；
 * 2) 没排过的列（新增列、当时隐藏的列）按 `defs` 默认顺序补在队尾。
 *
 * ⇒ 拖拽区不重复、不丢列，且老用户的坏缓存**不需要「恢复默认」即自愈**。
 *
 * ## 有意接受的代价
 *
 * 「当时隐藏、后来被开启」的列会落在拖拽区末尾，而不是它在 `defs` 里的默认位置。
 * 理由：用户从没对它排过序，就没有位置信息；给一个稳定、可预期的位置（末尾）
 * 好过猜一个。若该列本就默认可见（默认集），则它必然出现在 `order` 里，不受影响。
 */
import type { ColumnDef } from "@/views/asset/watchlist/columnDefs";

/**
 * 按用户的（**可能不完整**的）顺序重建全量列序。
 *
 * @param defs  全量列定义（顺序即默认展示顺序）
 * @param order 持久化的可拖拽列顺序；空数组 = 从未排序，直接返回默认序
 * @returns 新数组：非拖拽列（固定列 / 内置列）保持默认锚点位置，拖拽列逐槽位填入
 *
 * 不变量（回归判据见 `__tests__/columnOrder.spec.ts`）：
 * - 结果与 `defs` **等长**，每个 key **恰好出现一次**；
 * - 非拖拽列的位置与 `defs` 完全一致。
 */
export function rebuildColumnOrder(
  defs: ColumnDef[],
  order: string[]
): ColumnDef[] {
  if (order.length === 0) return defs;

  const byKey = new Map(defs.map(d => [d.key, d]));
  const placed = new Set<string>();
  const queue: ColumnDef[] = [];

  for (const key of order) {
    const def = byKey.get(key);
    // 非拖拽 / 已被删掉的列 / 重复 key：都不占槽位，否则会把别的列挤掉
    if (!def || !def.draggable || placed.has(key)) continue;
    placed.add(key);
    queue.push(def);
  }
  if (queue.length === 0) return defs;

  // 用户没排过的列按默认顺序补齐——这是「不重复」的关键：
  // 槽位数 == 全量可拖拽列数，队列必须等长才不会退化成「保留原位」
  for (const def of defs) {
    if (def.draggable && !placed.has(def.key)) queue.push(def);
  }

  let next = 0;
  return defs.map(d => (d.draggable ? queue[next++] : d));
}
