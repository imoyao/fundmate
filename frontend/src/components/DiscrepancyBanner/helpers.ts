/**
 * 对账差异提醒（`DiscrepancyBanner`）的纯逻辑。
 *
 * 与组件结构解耦，便于 vitest 直接验证（前端单测是 node 环境、只跑 `__tests__` 下的
 * 纯函数，见 `vitest.config.ts`）。
 *
 * ## 为什么单独成文件而不是塞进组件
 *
 * 这几个函数承载的是**口径**（哪一类算「待处理」、按什么排序、天数怎么算），
 * 恰恰是最容易在重构中被顺手改坏的部分。放成纯函数才能被单测钉住。
 */

/** 对账工作台路由名：该页自带 banner + 指标卡 + Tab 角标，站外提醒不重复展示。 */
export const WORKBENCH_ROUTE_NAME = "ReconcileWorkbench";

/** 收起态最多展示几条（与域 D 的 `GhostDuplicateBanner` 同一量级）。 */
export const COLLAPSED_LIMIT = 5;

/** 差异行的最小形状（只取本模块用到的字段，避免与 API 类型强耦合）。 */
export interface PendingLike {
  id: number;
  domain: string;
  symbol: string;
  discrepancy_type: string;
  first_detected_at: string | null;
}

/**
 * 取出「域 B 的待处理差异」。
 *
 * 为什么只看域 B：
 * - 域 B = 持仓与流水的数量/成本差异，是**用户不主动查就永远不会发现**的一类；
 * - 域 C 是导入时当场触发的孤儿检测，用户正面对着那张导入单，不存在「看不见」；
 * - 只取域 B 还保证横幅上的数字与工作台「待裁决差异」指标**逐字相等**
 *   （工作台该指标在域 B 下算的正是 `domain==='B' && status==='pending'`）——
 *   两处数字对不上会直接让用户不信任提醒。
 */
export function pickDomainBPending<T extends PendingLike>(items: T[]): T[] {
  return items.filter(d => d.domain === "B");
}

/**
 * 待处理天数：按**首次发现日**算，整数天。
 *
 * - 只取日期部分（`YYYY-MM-DD`）按本地零点解析：后端时间戳是本地时间（Asia/Shanghai）
 *   且带微秒（`2026-09-01T06:06:39.184874`），交给 `new Date()` 解析在部分引擎上
 *   会被判为非法格式；只取日期既绕开这点，也天然抹掉「几点发现的」这种无意义精度。
 * - 用本地零点做差 → 整日计数，不会在同一天内来回跳（09:59 发现、10:01 打开
 *   不该从「1 天」跳回「0 天」）。
 * - 缺失或格式非法 → 返回 `null`（**未知**，不是 0 天）：把「不知道什么时候发现的」
 *   说成「今天发现」是失真，且会让它排到最前面假装最紧急。
 */
export function pendingDays(
  firstDetectedAt: string | null | undefined,
  now: Date
): number | null {
  if (!firstDetectedAt) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(firstDetectedAt);
  if (!m) return null;
  const detected = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (Number.isNaN(detected.getTime())) return null;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round((today.getTime() - detected.getTime()) / 86400000);
  return days < 0 ? 0 : days;
}

/**
 * 按「挂得最久」排序：待处理天数多的在前。
 *
 * 为什么不用接口默认的 `updated_at` 倒序：那是「最近被动过」的顺序，而用户该先看到
 * 的是**最久没被处理**的那条（017074 那条挂了 7 周，正是本提醒的由来）。
 * 天数未知（`null`）排最后——不是最紧急，别让它占头位。
 * 同天数按 `id` 升序，保证结果稳定可测（同一条数据两次渲染顺序一致）。
 */
export function sortByStaleness<T extends PendingLike>(
  items: T[],
  now: Date
): T[] {
  return [...items]
    .map((item, index) => ({
      item,
      index,
      days: pendingDays(item.first_detected_at, now)
    }))
    .sort((a, b) => {
      if (a.days === null && b.days === null) return a.item.id - b.item.id;
      if (a.days === null) return 1;
      if (b.days === null) return -1;
      if (a.days !== b.days) return b.days - a.days;
      return a.item.id - b.item.id;
    })
    .map(x => x.item);
}

/**
 * 天数文案。
 *
 * - `null` → 「发现时间未知」：宁可承认不知道，也不编一个天数；
 * - 0 天 → 「今天发现」；1 天 → 「昨天发现」；其余 → 「N 天前发现」。
 */
export function ageLabel(days: number | null): string {
  if (days === null) return "发现时间未知";
  if (days <= 0) return "今天发现";
  if (days === 1) return "昨天发现";
  return `${days} 天前发现`;
}

/**
 * 该路由是否展示站外提醒。
 *
 * 工作台页**不展示**：那页顶部已有 banner（"有 N 项差异待处理，点击切换到对应域"）、
 * 顶部指标卡「待裁决差异」、以及各 Tab 角标——三处都在说同一件事，再挂一条纯冗余。
 */
export function shouldShowOnRoute(
  routeName: string | undefined | null
): boolean {
  return routeName !== WORKBENCH_ROUTE_NAME;
}
