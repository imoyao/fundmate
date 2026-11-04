import { describe, expect, it } from "vitest";
import {
  type EnrichedHolding,
  UNTAGGED,
  buildStrategyGroups,
  diffTags,
  enrichHoldings,
  sliceGroupPage,
  sumMarketValue,
  sumPnl,
  withTag,
  withoutTag,
  withoutTagEverywhere
} from "../strategyViewModel";

/** 测试里的盈亏口径桩：真正的 confirmedPnl 由页面注入，这里只验证「透传 + null 落 0」 */
const noPnl = () => null;

/** 造一条富化后的持仓（默认已挂一个标签） */
function holding(
  id: number,
  tags: string[] = [],
  patch: Partial<EnrichedHolding> = {}
): EnrichedHolding {
  return {
    id,
    name: `持仓${id}`,
    symbol: `00000${id}`,
    marketValue: 100,
    pnl: 10,
    pnlRate: 1,
    _tags: tags,
    ...patch
  };
}

describe("持仓富化", () => {
  it("市值 = 份额 × 现价（后端概览的 quantity 已是可读份额，不再 /10000）", () => {
    const [row] = enrichHoldings(
      [{ id: 1, quantity: 200000, current_price: 2.5, avg_price: 2 }],
      {},
      noPnl
    );
    expect(row.marketValue).toBe(500000);
  });

  it("盈亏率 =（现价 − 均价）/ 均价，无均价时给 0（不产生 NaN）", () => {
    const [withAvg] = enrichHoldings(
      [{ id: 1, quantity: 100, current_price: 3, avg_price: 2 }],
      {},
      noPnl
    );
    expect(withAvg.pnlRate).toBeCloseTo(50, 10);

    const [noAvg] = enrichHoldings(
      [{ id: 2, quantity: 100, current_price: 3 }],
      {},
      noPnl
    );
    expect(noAvg.pnlRate).toBe(0);
  });

  it("盈亏取注入的 pnlOf（页面传 confirmedPnl），null 视为 0", () => {
    // 货基 / 逆回购没有「份额 × 现价」口径，confirmedPnl 返回 null ⇒ 这里落 0
    const pnlOf = (h: { id: number }) => (h.id === 1 ? 12.5 : null);
    const rows = enrichHoldings(
      [
        {
          id: 1,
          type: "fund",
          quantity: 100000,
          current_price: 2,
          avg_price: 1
        },
        {
          id: 2,
          type: "money_fund",
          quantity: 100000,
          current_price: 1,
          avg_price: 1
        }
      ],
      {},
      pnlOf
    );
    expect(rows[0].pnl).toBe(12.5);
    expect(rows[1].pnl).toBe(0);
  });

  it("标签从 relations 挂上；没有关系时给空数组（模板靠 .length 判断）", () => {
    const rows = enrichHoldings(
      [
        { id: 1, quantity: 1, current_price: 1 },
        { id: 2, quantity: 1, current_price: 1 }
      ],
      { 1: ["价值", "低波"] },
      noPnl
    );
    expect(rows[0]._tags).toEqual(["价值", "低波"]);
    expect(rows[1]._tags).toEqual([]);
  });
});

describe("汇总", () => {
  const rows = [
    holding(1, [], { marketValue: 100, pnl: 10 }),
    holding(2, [], { marketValue: 250, pnl: -30 })
  ];

  it("市值求和", () => {
    expect(sumMarketValue(rows)).toBe(350);
  });

  it("盈亏求和（含负数）", () => {
    expect(sumPnl(rows)).toBe(-20);
  });

  it("空列表为 0", () => {
    expect(sumMarketValue([])).toBe(0);
    expect(sumPnl([])).toBe(0);
  });
});

describe("按标签分组", () => {
  it("无标签的持仓归到「未分类」，且它恒排最后", () => {
    const groups = buildStrategyGroups([
      holding(1, ["价值"]),
      holding(2, []),
      holding(3, ["成长"])
    ]);
    expect(groups.map(g => g.tag).at(-1)).toBe(UNTAGGED);
    expect(
      groups.find(g => g.tag === UNTAGGED)?.holdings.map(h => h.id)
    ).toEqual([2]);
  });

  it("一只持仓带多个标签 ⇒ 同时出现在多个组里（多对多，不是互斥分区）", () => {
    const groups = buildStrategyGroups([holding(1, ["价值", "低波"])]);
    expect(groups.map(g => g.tag).sort()).toEqual(["价值", "低波"].sort());
    expect(groups.every(g => g.holdings.length === 1)).toBe(true);
  });

  it("组内市值 / 盈亏是组内合计", () => {
    const groups = buildStrategyGroups([
      holding(1, ["价值"], { marketValue: 100, pnl: 10 }),
      holding(2, ["价值"], { marketValue: 200, pnl: -40 })
    ]);
    expect(groups[0].totalMarketValue).toBe(300);
    expect(groups[0].totalPnl).toBe(-30);
  });

  it("空持仓给空分组列表（模板据此渲染空态）", () => {
    expect(buildStrategyGroups([])).toEqual([]);
  });
});

describe("分组内分页", () => {
  const groups = buildStrategyGroups(
    Array.from({ length: 5 }, (_, i) => holding(i + 1, ["价值"]))
  );

  it("第一页取前 pageSize 条，第三页取剩余", () => {
    expect(sliceGroupPage(groups, "价值", 1, 2).map(h => h.id)).toEqual([1, 2]);
    expect(sliceGroupPage(groups, "价值", 3, 2).map(h => h.id)).toEqual([5]);
  });

  it("未知标签返回空数组（标签被删后分页器仍可能持有旧 tag）", () => {
    expect(sliceGroupPage(groups, "不存在的标签", 1, 2)).toEqual([]);
  });
});

describe("标签双向 diff", () => {
  it("同时算出要绑定与要解绑的标签", () => {
    expect(diffTags(["价值", "低波"], ["价值", "成长"])).toEqual({
      toAdd: ["成长"],
      toRemove: ["低波"]
    });
  });

  it("全选 / 全不选两个极端", () => {
    expect(diffTags([], ["价值"])).toEqual({ toAdd: ["价值"], toRemove: [] });
    expect(diffTags(["价值"], [])).toEqual({ toAdd: [], toRemove: ["价值"] });
  });

  it("没有变化时两边都空", () => {
    expect(diffTags(["a"], ["a"])).toEqual({ toAdd: [], toRemove: [] });
  });
});

describe("标签映射的不可变更新", () => {
  it("withoutTag 返回新对象，不改入参", () => {
    const map = { 1: ["价值", "低波"] };
    const next = withoutTag(map, 1, "价值");
    expect(next[1]).toEqual(["低波"]);
    expect(map[1]).toEqual(["价值", "低波"]);
  });

  it("withoutTag 对没有标签的持仓原样返回（同一引用）", () => {
    const map = { 1: ["价值"] };
    expect(withoutTag(map, 9, "价值")).toBe(map);
  });

  it("withTag 不产生重复标签", () => {
    const map = { 1: ["价值"] };
    expect(withTag(map, 1, "价值")).toBe(map);
    expect(withTag(map, 1, "低波")[1]).toEqual(["价值", "低波"]);
  });

  it("withTag 对尚未有映射的持仓从空数组开始", () => {
    expect(withTag({}, 7, "价值")[7]).toEqual(["价值"]);
  });

  it("withoutTagEverywhere 把所有持仓上的同名标签摘掉（删除全局标签）", () => {
    const map = { 1: ["价值", "低波"], 2: ["价值"], 3: ["成长"] };
    const next = withoutTagEverywhere(map, "价值");
    expect(next).toEqual({ 1: ["低波"], 2: [], 3: ["成长"] });
    // 入参不变
    expect(map[1]).toEqual(["价值", "低波"]);
  });
});
