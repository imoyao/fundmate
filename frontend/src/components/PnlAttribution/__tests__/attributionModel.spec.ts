/**
 * 区间收益归因的纯计算（#980 批 B4 从 `index.vue` 抽到 `attributionModel.ts` 时补的网）。
 *
 * 两条容易写反的口径：
 * ① 区间预设的边界（「今年」必须是 1-1 起，不是「近 12 个月」）；
 * ② 空态那两句话不能混用——「数据不足」与「没有可归因持仓」是两件事，
 *    混了用户就会去翻持仓，而真正缺的是数据。
 */
import { describe, expect, it } from "vitest";
import type { PnlAttributionPayload } from "@/api/summary";
import {
  barWidthFor,
  buildRows,
  computeMaxAbs,
  emptyTextFor,
  fmtDate,
  presetRange,
  sectionInfoFor,
  type ViewRow
} from "../attributionModel";

const NOW = new Date(2026, 9, 27); // 2026-10-27 本地时区

function payload(
  over: Partial<PnlAttributionPayload> = {}
): PnlAttributionPayload {
  return {
    scope: "family",
    ledger_id: null,
    portfolio_id: null,
    start_date: "2026-10-01",
    end_date: "2026-10-27",
    total_pnl: 0,
    has_any_computable: true,
    positions: [],
    categories: [],
    unpriced_positions: [],
    ...over
  } as PnlAttributionPayload;
}

describe("fmtDate", () => {
  it("月 / 日补零", () => {
    expect(fmtDate(new Date(2026, 0, 5))).toBe("2026-01-05");
    expect(fmtDate(new Date(2026, 11, 31))).toBe("2026-12-31");
  });
});

describe("presetRange", () => {
  it("今年 = 1-1 起（不是「近 12 个月」）", () => {
    expect(presetRange("ytd", NOW)).toEqual({
      start_date: "2026-01-01",
      end_date: "2026-10-27"
    });
  });

  it("近1月 / 近3月 / 近1年按月回退", () => {
    expect(presetRange("1m", NOW).start_date).toBe("2026-09-27");
    expect(presetRange("3m", NOW).start_date).toBe("2026-07-27");
    expect(presetRange("1y", NOW).start_date).toBe("2025-10-27");
  });

  it("终点恒为今天（所有预设共用一个 end）", () => {
    for (const key of ["1m", "3m", "ytd", "1y"] as const) {
      expect(presetRange(key, NOW).end_date).toBe("2026-10-27");
    }
  });
});

describe("buildRows", () => {
  it("无载荷 ⇒ 空行", () => {
    expect(buildRows(null, "position", t => String(t))).toEqual([]);
  });

  it("大类维度：名称走标签函数，副标题说明由几只组成", () => {
    const rows = buildRows(
      payload({
        categories: [
          { asset_type: "fund", positions_count: 3, pnl: 120, pct: 1.2 }
        ] as PnlAttributionPayload["categories"]
      }),
      "category",
      t => `L:${t}`
    );
    expect(rows).toEqual([
      { key: "fund", name: "L:fund", sub: "3 只", pnl: 120, pct: 1.2 }
    ]);
  });

  it("品种维度：有名称用名称，无名称回落到代码", () => {
    const rows = buildRows(
      payload({
        positions: [
          {
            position_id: 7,
            name: "沪深300ETF",
            symbol: "510300",
            asset_type: "etf",
            pnl: -80,
            pct: -0.8
          },
          {
            position_id: 8,
            name: "",
            symbol: "000001",
            asset_type: "fund",
            pnl: 40,
            pct: null
          }
        ] as PnlAttributionPayload["positions"]
      }),
      "position",
      t => `L:${t}`
    );
    expect(rows[0].key).toBe("7");
    expect(rows[0].name).toBe("沪深300ETF");
    expect(rows[0].sub).toBe("510300 · L:etf");
    expect(rows[1].name).toBe("000001");
    expect(rows[1].sub).toBe("000001 · L:fund");
    expect(rows[1].pct).toBeNull();
  });

  it("品种无 asset_type 时副标题只留代码（不留孤零零的分隔点）", () => {
    const rows = buildRows(
      payload({
        positions: [
          {
            position_id: 9,
            name: "现金",
            symbol: "CASH",
            asset_type: null,
            pnl: 1,
            pct: 0
          }
        ] as unknown as PnlAttributionPayload["positions"]
      }),
      "position",
      t => `L:${t}`
    );
    expect(rows[0].sub).toBe("CASH");
  });
});

describe("computeMaxAbs / barWidthFor", () => {
  const rows: ViewRow[] = [
    { key: "a", name: "A", sub: "", pnl: 100, pct: null },
    { key: "b", name: "B", sub: "", pnl: -50, pct: null }
  ];

  it("分母取最大绝对值（符号不影响）", () => {
    expect(computeMaxAbs(rows)).toBe(100);
  });

  it("宽度按最大绝对值归一；负收益也占宽", () => {
    expect(barWidthFor(100, 100)).toBe("100%");
    expect(barWidthFor(-50, 100)).toBe("50%");
  });

  it("全零时宽度一律 0%（不留一条满格假条）", () => {
    expect(computeMaxAbs([{ ...rows[0], pnl: 0 }])).toBe(0);
    expect(barWidthFor(0, 0)).toBe("0%");
  });

  it("空行 ⇒ 分母 0", () => {
    expect(computeMaxAbs([])).toBe(0);
  });
});

describe("emptyTextFor", () => {
  it("整窗算不了 ⇒ 说数据不足", () => {
    expect(emptyTextFor(payload({ has_any_computable: false }))).toBe(
      "数据不足，无法计算区间贡献"
    );
  });

  it("能算但没行 ⇒ 说区间内没有可归因的持仓", () => {
    expect(emptyTextFor(payload({ has_any_computable: true }))).toBe(
      "区间内没有可归因的持仓"
    );
  });

  it("还没响应（null）⇒ 退回「没有可归因持仓」，不说数据不足", () => {
    expect(emptyTextFor(null)).toBe("区间内没有可归因的持仓");
  });
});

describe("sectionInfoFor", () => {
  it("有载荷时带上实际区间", () => {
    expect(sectionInfoFor(payload())).toContain("（2026-10-01 ~ 2026-10-27）");
  });

  it("无载荷时不写括号（不显示 undefined）", () => {
    const text = sectionInfoFor(null);
    expect(text).not.toContain("（");
    expect(text).not.toContain("undefined");
    expect(text).toContain("逐品种贡献之和与区间合计一致");
  });
});
