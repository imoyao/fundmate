import { describe, expect, it } from "vitest";

import type { FundRiskRankingRow } from "@/api/products";

import {
  DASH,
  barWidth,
  buildBarRanges,
  dirLabel,
  formatCell,
  numClass
} from "../rankingCells";
import { columnGroups, tableColumns } from "../rankingColumns";

/**
 * 同类优选的单元格口径（#980 拆分后补的回归网）。
 *
 * 拆分前这些逻辑是组件内闭包：改错了只表现为「表格里的数字看着不对」，没有任何判据。
 * 抽成纯函数后，这里钉住四条容易在重构中被「顺手优化」掉的口径：
 *
 * 1. **null 降级「—」**，不编造 0（诚实降级）；
 * 2. **显式 +/- 只给收益列**——给风险比率加「+」会被读成「收益为正」（UI=+18.5 尤其误导，
 *    越高越煎熬）；给最大回撤（负数存储）加「+」同理；
 * 3. **红涨绿跌只染收益列**，0 与 null 不染（颜色不得成为唯一信息载体）；
 * 4. **数据条长度以当前榜单为基准**，null 不参与 min/max，全列同值给满条。
 */

function row(over: Partial<FundRiskRankingRow> = {}): FundRiskRankingRow {
  return {
    fund_code: "110011",
    fund_name: "易方达中小盘",
    fund_type_id: 3,
    as_of: "2026-10-23",
    in_holdings: false,
    in_watchlist: false,
    max_drawdown: -18.42,
    current_drawdown: -3.1,
    drawdown_days: 22,
    annual_return: 12.345,
    annual_volatility: 21.5,
    ret_1m: 1.234,
    ret_3m: -2.345,
    ret_1y: 8.1,
    sharpe: 0.8765,
    sortino: 1.2,
    calmar: 0.67,
    ulcer_index: 18.5,
    upi: 0.4,
    return_drawdown_ratio: 0.3,
    win_rate: 55.2,
    sample_points: 720,
    basis: "acc_nav",
    window_label: "近3年",
    ...over
  };
}

const col = (key: string) => {
  const found = tableColumns.find(c => c.key === key);
  if (!found) throw new Error(`列定义缺少 ${key}——改 key 必须同时改后端白名单`);
  return found;
};
type Column = ReturnType<typeof col>;

describe("列定义与表头分组", () => {
  it("分组 keys 与 tableColumns 同序全覆盖（少一个键表头就错位）", () => {
    const flat = columnGroups.flatMap(g => g.keys);
    expect(flat).toEqual(tableColumns.map(c => c.key));
  });

  it("每个分组都有 tooltip 文案（分组行不可点，口径只能靠悬停讲）", () => {
    for (const g of columnGroups) {
      expect(g.label.length).toBeGreaterThan(0);
      expect(g.tip.length).toBeGreaterThan(0);
    }
  });

  it("列 key 不重复（重复会让表头 key 冲突、排序指向不明）", () => {
    const keys = tableColumns.map(c => c.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("只有收益列染涨跌色；风险比率列一律中性（合规：不替用户判好坏）", () => {
    const returns = tableColumns
      .filter(c => c.kind === "return")
      .map(c => c.key);
    expect(returns).toEqual(["annual_return", "ret_1m", "ret_3m", "ret_1y"]);
    for (const c of tableColumns) {
      if (c.kind !== "return") expect(c.kind).toMatch(/^(ratio|risk)$/);
    }
  });

  it("UI 的方向是「越低越好」，首击按 asc 排（否则先把最煎熬的排前面）", () => {
    expect(col("ulcer_index").dir).toBe("low");
    expect(tableColumns.filter(c => c.dir === "low").map(c => c.key)).toEqual([
      "ulcer_index"
    ]);
  });

  it("数据条只给夏普与卡玛（优中选优的核心指标）", () => {
    expect(tableColumns.filter(c => c.bar).map(c => c.key)).toEqual([
      "sharpe",
      "calmar"
    ]);
  });
});

describe("formatCell：null 降级与符号纪律", () => {
  it("null 一律「—」，不编造 0", () => {
    expect(formatCell(row({ sharpe: null }), col("sharpe") as Column)).toBe(
      DASH
    );
    expect(formatCell(row({ annual_return: null }), col("annual_return"))).toBe(
      DASH
    );
  });

  it("收益列为正时加 +，保留两位小数", () => {
    expect(formatCell(row({ ret_1m: 1.234 }), col("ret_1m"))).toBe("+1.23");
    expect(
      formatCell(row({ annual_return: 12.345 }), col("annual_return"))
    ).toBe("+12.35");
  });

  it("收益列为负时只留负号（不是一个 + 一个 -）", () => {
    expect(formatCell(row({ ret_3m: -2.345 }), col("ret_3m"))).toBe("-2.35");
  });

  it("收益列恰好 0 时不加符号（0 不是「涨」）", () => {
    expect(formatCell(row({ ret_1y: 0 }), col("ret_1y"))).toBe("0.00");
  });

  it("风险比率列即便是正数也不加 +（UI=18.50 而不是 +18.50）", () => {
    expect(formatCell(row({ ulcer_index: 18.5 }), col("ulcer_index"))).toBe(
      "18.50"
    );
    expect(formatCell(row({ sharpe: 0.8765 }), col("sharpe"))).toBe("0.88");
  });

  it("最大回撤以负数存储，照实显示带负号", () => {
    expect(formatCell(row({ max_drawdown: -18.42 }), col("max_drawdown"))).toBe(
      "-18.42"
    );
  });
});

describe("numClass：只给收益列上色", () => {
  it("收益正 → 涨色，负 → 跌色（红涨绿跌）", () => {
    expect(numClass(row({ ret_1m: 1.2 }), col("ret_1m"))).toBe("num--rise");
    expect(numClass(row({ ret_3m: -1.2 }), col("ret_3m"))).toBe("num--fall");
  });

  it("0 与 null 都不染（0 没有方向；null 没有值）", () => {
    expect(numClass(row({ ret_1m: 0 }), col("ret_1m"))).toBe("");
    expect(numClass(row({ ret_1m: null }), col("ret_1m"))).toBe("");
  });
});

describe("buildBarRanges：以当前榜单为基准", () => {
  const rows = [
    row({ fund_code: "A", sharpe: 2, calmar: 1 }),
    row({ fund_code: "B", sharpe: 0.5, calmar: 1 }),
    row({ fund_code: "C", sharpe: null, calmar: 1 })
  ];

  it("只给 bar 列算区间，非 bar 列不产出", () => {
    const ranges = buildBarRanges(rows, tableColumns);
    expect(Object.keys(ranges).sort()).toEqual(["calmar", "sharpe"]);
  });

  it("null 不参与 min/max（当作 0 会把条长整体拉偏）", () => {
    const ranges = buildBarRanges(rows, tableColumns);
    expect(ranges.sharpe).toEqual({ min: 0.5, max: 2 });
  });

  it("整列都是 null 时不产出（否则 min/max 会是 Infinity）", () => {
    const ranges = buildBarRanges(
      [row({ sharpe: null })],
      tableColumns.filter(c => c.key === "sharpe")
    );
    expect(ranges.sharpe).toBeUndefined();
  });
});

describe("barWidth：条长 = 榜单内相对位置", () => {
  const ranges = { sharpe: { min: 0.5, max: 2 } };

  it("最小值仍有 4% 可见宽度（0 宽等于没有数据条）", () => {
    expect(barWidth(row({ sharpe: 0.5 }), "sharpe", ranges)).toBe("4%");
  });

  it("最大值是满条", () => {
    expect(barWidth(row({ sharpe: 2 }), "sharpe", ranges)).toBe("100%");
  });

  it("中间值按线性比例", () => {
    expect(barWidth(row({ sharpe: 1.25 }), "sharpe", ranges)).toBe("50%");
  });

  it("全列同值（span=0）给满条——都排在同一位置，没有长短可比", () => {
    const same = { sharpe: { min: 1.1, max: 1.1 } };
    expect(barWidth(row({ sharpe: 1.1 }), "sharpe", same)).toBe("100%");
  });

  it("缺区间或值为 null 时不画条（返回 undefined，模板不渲染 style）", () => {
    expect(barWidth(row({ sharpe: 1 }), "calmar", ranges)).toBeUndefined();
    expect(barWidth(row({ sharpe: null }), "sharpe", ranges)).toBeUndefined();
  });
});

describe("dirLabel：方向文案", () => {
  it("high / low 分别对应用户语言", () => {
    expect(dirLabel("high")).toBe("越高越好");
    expect(dirLabel("low")).toBe("越低越好");
  });
});
