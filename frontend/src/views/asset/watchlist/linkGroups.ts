/**
 * 自选「关联」列的分组语义（#2503，补齐 #1394 的剩余缺口）
 *
 * `channel_links` 存两类**有向**关系，自选接口按裸代码**双向**查后把「另一侧」下发到行里
 * （`backend/app/services/watchlist_display.py:725`），因此同一行的 `links` 里可能出现两类：
 *
 * | 行品类 | link_type | 另一侧是 | 组标题 | 角标短词 |
 * |---|---|---|---|---|
 * | 指数 index | `index_etf` | 场内 ETF | 场内 ETF | 场内 |
 * | ETF etf | `index_etf` | **指数**（它跟踪谁） | 跟踪指数 | 指数 |
 * | ETF etf | `etf_feeder` | 场外联接基金 | 场外联接 | 场外 |
 * | 场外联接 fund | `etf_feeder` | **场内 ETF**（对着哪只场内） | 对应场内 ETF | 对应场内 |
 *
 * ⚠️ 组标题**不能**只由 `link_type` 决定：`index_etf` 在指数行看到的另一侧是 ETF、
 * 在 ETF 行看到的另一侧是**指数**（本地库实测 453 只 ETF 同时挂着两类关系）。
 * 若一律按 `link_type` 贴「场内 ETF」/「场外联接」，ETF 行会把「跟踪的指数」
 * 标成「场内 ETF」——读者会以为那个代码能在场内买到。故标题必须由
 * **行品类 × link_type** 共同决定。
 *
 * 这里是纯函数（无 Vue / 无 DOM 依赖）：浮层与角标都从它取文案，
 * 单测见 `__tests__/linksRenderer.spec.ts`。
 */

/** 单条关联（后端 `links[]` 的元素，字段与 `api/types.d.ts` 一致） */
export interface WatchlistLink {
  code: string;
  name: string | null;
  link_type: string | null;
}

/** 一个分组（浮层里一个小区块；角标按组取短词） */
export interface LinkGroup {
  /** `link_type` 原值，兼作组顺序键与去重键 */
  linkType: string;
  /** 浮层组标题（「本行视角」下另一侧是什么） */
  title: string;
  /** 角标短词，空格 + 数量拼成「场内 5 / 指数 1 · 场外 3」 */
  short: string;
  /** 组内条目（已按 code 去重，保持后端下发顺序） */
  items: WatchlistLink[];
}

/** 组的固定顺序：先「我能买到什么」（场内 ETF / 跟踪指数），再「场外」。
 *  不按数量排序——数量会随数据刷新变化，顺序跳动比不排序更难读。 */
const GROUP_ORDER = ["index_etf", "etf_feeder"];

/**
 * 浮层单组最多列出的条目数。
 * 本地库实测一个指数最多挂 **35** 只 ETF（`000510` / `931071`），全量平铺会把浮层
 * 拉成 700px 长条、超出视口；截断后剩余数量由「另有 N 只」交代。
 */
export const LINK_GROUP_MAX_ITEMS = 8;

/** 行品类 × link_type → 文案。未知组合退化为中性「关联」，不猜语义。 */
function labelsFor(
  linkType: string,
  assetType: string
): { title: string; short: string } {
  if (linkType === "index_etf") {
    return assetType === "etf"
      ? { title: "跟踪指数", short: "指数" }
      : { title: "场内 ETF", short: "场内" };
  }
  if (linkType === "etf_feeder") {
    return assetType === "fund"
      ? { title: "对应场内 ETF", short: "对应场内" }
      : { title: "场外联接", short: "场外" };
  }
  return { title: "其他关联", short: "关联" };
}

/**
 * 把行内 `links` 分组成「本行视角」的若干区块。
 *
 * - 空数组返回空数组（调用方据此渲染 `—`，不渲染空浮层）；
 * - 未知 `link_type` 归入同名的末位分组（排在两类已知关系之后）；
 * - 同组内按 `code` 去重：`channel_links` 理论上不该同时存 A→B 与 B→A，
 *   但双向查的实现下重复会让浮层出现两遍同一只标的，去重是廉价的兜底。
 */
export function groupLinks(
  links: readonly WatchlistLink[] | null | undefined,
  assetType: string
): LinkGroup[] {
  const byType = new Map<string, LinkGroup>();
  for (const link of links ?? []) {
    if (!link || !link.code) continue;
    const linkType = link.link_type || "";
    let group = byType.get(linkType);
    if (!group) {
      group = { linkType, ...labelsFor(linkType, assetType), items: [] };
      byType.set(linkType, group);
    }
    if (!group.items.some(item => item.code === link.code)) {
      group.items.push(link);
    }
  }
  const rank = (linkType: string): number => {
    const i = GROUP_ORDER.indexOf(linkType);
    return i === -1 ? GROUP_ORDER.length : i;
  };
  return [...byType.values()].sort(
    (a, b) => rank(a.linkType) - rank(b.linkType)
  );
}

/**
 * 角标文案：按组给出「短词 + 数量」，组间用 `·` 连接。
 * 单组 `场内 5`；两组 `指数 1 · 场外 3`。无分组返回空串（调用方此时应渲染 `—`）。
 */
export function linkBadgeText(groups: readonly LinkGroup[]): string {
  return groups
    .filter(group => group.items.length > 0)
    .map(group => `${group.short} ${group.items.length}`)
    .join(" · ");
}

/** 单条关联的展示文案：`名称（代码）`，缺名时退化为代码（都是后端下发字段，不编造） */
export function linkItemText(link: WatchlistLink): string {
  return link.name ? `${link.name}（${link.code}）` : link.code;
}

/**
 * 浮层展示用切片：[可见条目, 剩余数量]。
 * 剩余 > 0 时调用方追加「另有 N 只」。
 */
export function splitForTooltip(group: LinkGroup): [WatchlistLink[], number] {
  const shown = group.items.slice(0, LINK_GROUP_MAX_ITEMS);
  return [shown, group.items.length - shown.length];
}
