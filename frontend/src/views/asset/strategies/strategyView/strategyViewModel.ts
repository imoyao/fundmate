/**
 * 策略视图的纯函数层（#980 拆分自 views/asset/strategies/index.vue）。
 *
 * 三块口径都在这里，便于直接喂数据断言：
 * - **持仓富化**：市值 / 盈亏 / 盈亏率的换算，以及「一行挂多标签」的关系合并
 * - **分组**：一只持仓按标签复制进多个组（多对多），「未分类」恒排最后
 * - **标签增减**：把「勾选后的全集」与「当前集合」差出 toAdd / toRemove
 */

/** 「未分类」分组名（无标签的持仓归到这里，排序恒在最后） */
export const UNTAGGED = "未分类";

export interface EnrichedHolding {
  id: number;
  name?: string;
  symbol?: string;
  type_label?: string;
  account_name?: string;
  marketValue: number;
  pnl: number;
  pnlRate: number;
  _tags: string[];
  /** 价格时点（#2140 / #2210）：行数据来自 getStrategyOverview，后端行级 price_date */
  price_date?: string | null;
  /**
   * 当日确认口径是否已定型（#2210）：true = 估值副行应隐藏；null / 缺省 = 不隐藏。
   * **状态 = 后端字段契约**，前端禁止按日期自行推断。
   */
  settled_today?: boolean | null;
  [key: string]: any;
}

/** 后端概览里的一条原始持仓（只声明这里用到的字段，其余原样透传） */
export interface RawHolding {
  id: number;
  quantity?: number | null;
  current_price?: number | null;
  avg_price?: number | null;
  [key: string]: any;
}

/**
 * 富化持仓：算市值 / 盈亏 / 盈亏率，并挂上标签名数组。
 *
 * 盈亏口径**由调用方注入**（`pnlOf`，页面传 `confirmedPnl`）：这里原本是页面自算的
 * 同款公式，与「已确认」双线并存就会出现同一行两套公式——货基 / 逆回购的豁免
 * 只在一处生效（#1104）。
 *
 * 注入而不是直接 import：`usePositionValuation` 会沿依赖链拉进行情与路由模块，
 * 单元测试只要 import 一次就会去初始化 Supabase 客户端（实测直接抛错）。
 */
export function enrichHoldings(
  holdings: RawHolding[],
  relations: Record<number, string[]>,
  pnlOf: (holding: RawHolding) => number | null
): EnrichedHolding[] {
  return holdings.map(h => ({
    ...h,
    marketValue: (h.quantity || 0) * (h.current_price || 0),
    pnl: pnlOf(h) ?? 0,
    pnlRate: h.avg_price
      ? (((h.current_price || 0) - h.avg_price) / h.avg_price) * 100
      : 0,
    _tags: relations[h.id] || []
  })) as EnrichedHolding[];
}

/**
 * 用**当前**的标签映射重投影持仓的 `_tags`。
 *
 * 必须每次从映射算，不能沿用 `enrichHoldings` 时的快照：勾选/取消标签后映射变了，
 * 而持仓对象本身没变——直接复用快照会让表格里的标签徽标停在旧值（实测：取消绑定
 * 成功了、请求也发了，但勾选框仍是选中态、分组也不重排）。
 */
export function applyTags(
  holdings: EnrichedHolding[],
  map: Record<number, string[]>
): EnrichedHolding[] {
  return holdings.map(h => ({ ...h, _tags: map[h.id] || [] }));
}

/** 汇总市值 */
export function sumMarketValue(holdings: EnrichedHolding[]): number {
  return holdings.reduce((sum, h) => sum + (h.marketValue || 0), 0);
}

/** 汇总盈亏（静态确认口径，不含当日预估） */
export function sumPnl(holdings: EnrichedHolding[]): number {
  return holdings.reduce((sum, h) => sum + (h.pnl || 0), 0);
}

export interface StrategyGroup {
  /** 分组名 = 标签名；无标签时为「未分类」 */
  tag: string;
  holdings: EnrichedHolding[];
  totalMarketValue: number;
  totalPnl: number;
}

/**
 * 按标签分组。
 *
 * 一只持仓可以带多个标签 ⇒ **会同时出现在多个组里**（多对多，不是互斥分区），
 * 所以各组的市值/盈亏相加**不等于**页面顶部汇总——顶部汇总取原始持仓，不取分组结果。
 * 排序：「未分类」恒最后，其余按中文拼音序（`localeCompare("zh-Hans")`）。
 */
export function buildStrategyGroups(
  holdings: EnrichedHolding[]
): StrategyGroup[] {
  const groups: Record<string, EnrichedHolding[]> = {};

  holdings.forEach(h => {
    const tags = h._tags.length ? h._tags : [UNTAGGED];
    tags.forEach(tag => {
      if (!groups[tag]) groups[tag] = [];
      groups[tag].push(h);
    });
  });

  const entries: [string, EnrichedHolding[]][] = Object.entries(groups);
  entries.sort(([a], [b]) => {
    if (a === UNTAGGED) return 1;
    if (b === UNTAGGED) return -1;
    return a.localeCompare(b, "zh-Hans");
  });

  return entries.map(([tag, items]) => ({
    tag,
    holdings: items,
    totalMarketValue: sumMarketValue(items),
    totalPnl: sumPnl(items)
  }));
}

/** 某个标签分组的当前页切片（分组内分页，页码从 1 开始） */
export function sliceGroupPage(
  groups: StrategyGroup[],
  tag: string,
  page: number,
  pageSize: number
): EnrichedHolding[] {
  const group = groups.find(g => g.tag === tag);
  if (!group) return [];
  const start = (page - 1) * pageSize;
  return group.holdings.slice(start, start + pageSize);
}

/**
 * 差出「要绑定」与「要解绑」的标签名。
 *
 * 输入是**勾选后的全集**（el-checkbox-group 的行为），故必须双向 diff：
 * 只算新增会让「取消勾选」静默不生效。
 */
export function diffTags(
  current: string[],
  selected: string[]
): { toAdd: string[]; toRemove: string[] } {
  return {
    toAdd: selected.filter(t => !current.includes(t)),
    toRemove: current.filter(t => !selected.includes(t))
  };
}

/** 删除某持仓上的一个标签（返回新映射，不改入参——避免就地 splice 让引用计数失效） */
export function withoutTag(
  map: Record<number, string[]>,
  positionId: number,
  tagName: string
): Record<number, string[]> {
  const current = map[positionId];
  if (!current) return map;
  return { ...map, [positionId]: current.filter(n => n !== tagName) };
}

/** 给某持仓追加一个标签（已在则原样返回，不产生重复） */
export function withTag(
  map: Record<number, string[]>,
  positionId: number,
  tagName: string
): Record<number, string[]> {
  const current = map[positionId] ?? [];
  if (current.includes(tagName)) return map;
  return { ...map, [positionId]: [...current, tagName] };
}

/** 全局删除某个标签：从所有持仓上摘掉它（返回新映射） */
export function withoutTagEverywhere(
  map: Record<number, string[]>,
  tagName: string
): Record<number, string[]> {
  const next: Record<number, string[]> = {};
  Object.keys(map).forEach(key => {
    const id = Number(key);
    next[id] = map[id].filter(n => n !== tagName);
  });
  return next;
}
