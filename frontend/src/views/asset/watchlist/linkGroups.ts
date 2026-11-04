/**
 * 自选「关联」列的数据与文案整形（#2503）。
 *
 * 为什么单独成文件、不直接写在 `columnRenderers.tsx` 里：
 * 渲染器为了画单元格会 import MoneyDisplay / ProductDisplay 等 `.vue` 组件，而这些
 * 组件的依赖链最终会**初始化整个应用**（实测：单测里 import 渲染器会一路要求
 * VITE_SUPABASE_URL → VITE_ROUTER_HISTORY，因为某组件牵出了 router）。
 * 把纯整形逻辑留在这里（只依赖 `vue` 的 h，不碰组件 / DOM / 路由），分组与措辞
 * 就能独立于应用启动被测试——vitest 环境是 node，没有 DOM 也不该有。
 *
 * 边界：本文件**只**产出结构与文案，不负责 ElTooltip 包装（那是 renderLinks 的事）。
 */

import { h, type VNode } from "vue";

/** 自选行内下发的关联条目。后端只给这三个字段（见 watchlist_display）。
 * 详情页 `/api/products/related-symbols/` 另有 label / peer_role，行内没有，
 * 故这里不做任何假设——拿不到就按代码显示，不编造近1年 / 费率 / 规模。 */
export interface WatchlistLinkItem {
  code: string;
  name: string | null;
  link_type?: string | null;
}

export interface LinkGroup {
  /** 浮层组标题（人可读全称） */
  title: string;
  /** 角标里的组简称（列宽有限，用短词） */
  short: string;
  items: WatchlistLinkItem[];
}

const LINK_GROUP_DEFS = [
  { type: "index_etf", title: "场内 ETF", short: "场内" },
  { type: "etf_feeder", title: "场外联接", short: "场外" }
] as const;

/** 兜底组：link_type 超出已知两类时也要显示——已入库的关联不该凭空消失 */
const LINK_GROUP_OTHER = { title: "其他关联", short: "其他" };

/** 按 `link_type` 分组：组内保持下发顺序，组间按 LINK_GROUP_DEFS 顺序，未知类型落兜底组。 */
export function groupLinks(links: WatchlistLinkItem[]): LinkGroup[] {
  const knownTypes = LINK_GROUP_DEFS.map(d => d.type);
  const known = LINK_GROUP_DEFS.map(def => ({
    title: def.title,
    short: def.short,
    items: links.filter(l => l.link_type === def.type)
  }));
  const rest = links.filter(l => !knownTypes.includes(l.link_type as never));
  return [...known, { ...LINK_GROUP_OTHER, items: rest }].filter(
    g => g.items.length
  );
}

/**
 * 角标措辞：**站在本行视角**说人话，而不是复述关系类型。
 *
 * - 场外联接行（asset_type=fund）：对端一律是场内 ETF ⇒ 「对应场内 N」，
 *   比中性词「场外 N」更能回答用户真正在问的「同一暴露在哪个渠道能买」；
 * - 指数行 / ETF 行：可能同时挂两类 ⇒ 按组并列「场内 N · 场外 M」，
 *   不必展开浮层就知道这一行两个渠道都有出口。
 */
export function linkBadgeText(groups: LinkGroup[], assetType: string): string {
  if (assetType === "fund") {
    return `对应场内 ${groups.reduce((sum, g) => sum + g.items.length, 0)}`;
  }
  return groups.map(g => `${g.short} ${g.items.length}`).join(" · ");
}

/** 条目文案：有名称带代码，缺名称只给代码（不渲染 null、不留空条目）。 */
export function linkItemText(item: WatchlistLinkItem): string {
  return item.name ? `${item.name}（${item.code}）` : item.code;
}

/**
 * 浮层内容：按组分区块，组标题带数量，组内一行一条。
 *
 * 走 VNode 而不是拼字符串——分组是结构化的，拼成一句会让场内/场外重新混在一起
 * （那正是 #2503 要修的形态）。
 */
export function buildLinkTip(groups: LinkGroup[]): VNode {
  return h(
    "div",
    { class: "link-tip" },
    groups.map(g =>
      h("div", { class: "link-tip-group" }, [
        h("div", { class: "link-tip-title" }, `${g.title} · ${g.items.length}`),
        ...g.items.map(l =>
          h("div", { class: "link-tip-item" }, linkItemText(l))
        )
      ])
    )
  );
}
