import { describe, expect, it } from "vitest";
import type { AllocationData } from "@/api/strategyEngine";
import {
  buildAddableSymbols,
  buildSaveItems,
  buildVisibleRows,
  formatPct,
  signedPct,
  sumTargets,
  toEditRows,
  type EditRow
} from "../allocationTargetModel";
import {
  actionLabel,
  buildProfileMap,
  formatNullable,
  formatSignedMoney,
  strategyName
} from "../diagnosisModel";

/**
 * #980 拆分回归：目标配比与策略诊断的口径。
 *
 * 两处都有「显示错了不报错」的坑：
 * - 目标配比留空保存成 0% 会被当成真目标（0% 是合法值）；
 * - 机会成本为负时取绝对值，会把「提前卖出躲过下跌」显示成「少赚」。
 */
const data = (over: Partial<AllocationData> = {}) =>
  ({
    items: [
      {
        symbol: "110011",
        name: "易方达中小盘",
        weight_pct: 46.2,
        target_pct: 40,
        deviation_pct: 6.2,
        breached: true
      },
      {
        symbol: "000001",
        name: "华夏成长",
        weight_pct: 20,
        target_pct: null,
        deviation_pct: null,
        breached: false
      }
    ],
    configured_count: 1,
    breached_count: 1,
    threshold_pct: 5,
    ...over
  }) as unknown as AllocationData;

describe("allocationTargetModel：只读 / 编辑两态", () => {
  it("只读态直接用后端事实", () => {
    const rows = buildVisibleRows(data(), false, []);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({
      symbol: "110011",
      target_pct: 40,
      deviation_pct: 6.2,
      breached: true
    });
    expect(rows[1].target_pct).toBeNull();
  });

  it("编辑态目标以用户输入为准，当前占比仍取后端事实", () => {
    const edit: EditRow[] = [
      { symbol: "110011", name: "易方达中小盘", target: 50 }
    ];
    const rows = buildVisibleRows(data(), true, edit);
    expect(rows[0].target_pct).toBe(50);
    expect(rows[0].weight_pct).toBe(46.2);
    // 偏离按「当前 - 目标」当场重算
    expect(rows[0].deviation_pct).toBeCloseTo(-3.8);
  });

  it("编辑态清空目标 → 偏离回到 null，不当成 0 偏离", () => {
    const rows = buildVisibleRows(data(), true, [
      { symbol: "110011", name: "易方达中小盘", target: null }
    ]);
    expect(rows[0].target_pct).toBeNull();
    expect(rows[0].deviation_pct).toBeNull();
  });

  it("进入编辑态复制后端目标值", () => {
    expect(toEditRows(data())).toEqual([
      { symbol: "110011", name: "易方达中小盘", target: 40 },
      { symbol: "000001", name: "华夏成长", target: null }
    ]);
  });

  it("可添加标的 = 持仓里还没在编辑行中的", () => {
    expect(
      buildAddableSymbols(data(), [
        { symbol: "110011", name: "易方达中小盘", target: 40 }
      ])
    ).toEqual([{ symbol: "000001", name: "华夏成长" }]);
  });

  it("目标总和与保存载荷：留空行被剔除，0% 不被剔除", () => {
    const rows: EditRow[] = [
      { symbol: "A", name: "A", target: 40 },
      { symbol: "B", name: "B", target: 0 },
      { symbol: "C", name: "C", target: null }
    ];
    expect(sumTargets(rows)).toBe(40);
    expect(buildSaveItems(rows)).toEqual([
      { symbol: "A", target_weight: 40 },
      { symbol: "B", target_weight: 0 }
    ]);
  });
});

describe("allocationTargetModel：百分点格式", () => {
  it("最多两位小数且去尾零，阈值 5 不显示成 5.00", () => {
    expect(formatPct(5)).toBe("5");
    expect(formatPct(46.2)).toBe("46.2");
    expect(formatPct(5.006)).toBe("5.01");
    expect(formatPct(null)).toBe("0");
  });

  it("偏离正数显式补 +，负数保留自带符号且不取绝对值", () => {
    expect(signedPct(6.2)).toBe("+6.2");
    expect(signedPct(-3.8)).toBe("-3.8");
    expect(signedPct(0)).toBe("0");
  });
});

describe("diagnosisModel：翻译与格式化", () => {
  it("action 翻成区间状态词，未收录原样退回", () => {
    expect(actionLabel("buy")).toBe("买入区间");
    expect(actionLabel("sell")).toBe("离场区间");
    expect(actionLabel("hold")).toBe("持有区间");
    expect(actionLabel("unknown" as any)).toBe("unknown");
  });

  it("策略名：有元信息用人话，否则退回 code", () => {
    const metas = [{ code: "ma_cross", name: "均线交叉" }] as any;
    expect(strategyName(metas, "ma_cross")).toBe("均线交叉");
    expect(strategyName(metas, "unknown")).toBe("unknown");
    expect(strategyName(undefined, "x")).toBe("x");
  });

  it("null 指标显示「—」而不是 0", () => {
    expect(formatNullable(null, "天")).toBe("—");
    expect(formatNullable(undefined, "%")).toBe("—");
    expect(formatNullable(12.345, "天")).toBe("12.35天");
  });

  it("机会成本带符号：负数必须原样显示（躲过下跌也是事实）", () => {
    expect(formatSignedMoney(120.456)).toBe("+120.46 元");
    expect(formatSignedMoney(-80)).toBe("-80 元");
    expect(formatSignedMoney(0)).toBe("0 元");
    expect(formatSignedMoney(null)).toBe("—");
  });

  it("行为画像按 symbol 建索引", () => {
    const map = buildProfileMap({
      profiles: [{ symbol: "110011", trade_count: 3 }]
    } as any);
    expect(map["110011"].trade_count).toBe(3);
    expect(map["000001"]).toBeUndefined();
    expect(buildProfileMap(null)).toEqual({});
  });
});
