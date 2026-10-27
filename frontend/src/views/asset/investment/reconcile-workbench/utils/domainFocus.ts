/**
 * 横幅点击「跳到第一个有待办的域」的选域规则（#1259，自 index.vue 抽出）。
 *
 * 为什么固定顺序而不是取「待处理数最大的域」：横幅的文案是「点击切换到对应域
 * 处理」，用户点它是想**开始处理**，不是想看统计。固定顺序保证同一个页面状态下
 * 每次点击落在同一个域（可预期、可重放），而「最大数」会随着一次忽略/补充而
 * 在几个域之间来回跳，用户会觉得点了两次去的地方不一样。
 *
 * 顺序的语义：B（持仓快照，主链路）→ C（对账单导入，入口域）→ A（E账户）
 * → D（跨账本重复）→ E（分红税）。**改这个数组等于改用户点击后落到哪个页签**，
 * 没有配套的验收就别动。
 */
import type { WorkbenchDomainKey } from "../constants/domainTabs";

/** 横幅点击时的选域优先级（见文件头：固定顺序，非「数最大者」） */
export const DOMAIN_FOCUS_ORDER: readonly WorkbenchDomainKey[] = [
  "B",
  "C",
  "A",
  "D",
  "E"
] as const;

/**
 * 取第一个待处理数 > 0 的域。
 *
 * @param pending 给定域标识返回其待处理数
 * @param order   选域优先级（默认 DOMAIN_FOCUS_ORDER，测试可注入）
 * @returns 命中的域标识；全部域都为 0 时返回 null（调用方据此不切域）
 */
export function pickFirstPendingDomain(
  pending: (key: WorkbenchDomainKey) => number,
  order: readonly WorkbenchDomainKey[] = DOMAIN_FOCUS_ORDER
): WorkbenchDomainKey | null {
  return order.find(key => pending(key) > 0) ?? null;
}
