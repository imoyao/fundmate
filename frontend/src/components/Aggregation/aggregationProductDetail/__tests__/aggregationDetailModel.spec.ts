import { describe, expect, it } from "vitest";
import type { AggregationSource } from "@/api/ledger";
import {
  buildAllocationPreview,
  canAllocate,
  cashFlowHintOf,
  dividendOrManagerText,
  fmtShortDate,
  navText,
  previewSumYuan,
  shareFromRaw,
  sourceDisplayName,
  sourceWeightCents,
  yuanFromCents
} from "../aggregationDetailModel";

/** 造一条来源（只给断言用到的字段，其余走类型可选/必填默认） */
function src(
  ledger_id: number,
  market_value_cents: number,
  extra: Partial<AggregationSource> = {}
): AggregationSource {
  return {
    ledger_id,
    ledger_name: `账本${ledger_id}`,
    institution_name: `机构${ledger_id}`,
    market_value_cents,
    quantity: 0,
    ...extra
  };
}

describe("份额 / 金额单位换算", () => {
  it("份额最小单位为份×10000", () => {
    expect(shareFromRaw(12345)).toBe(1.2345);
    expect(shareFromRaw(0)).toBe(0);
  });

  it("份额空值按 0 处理（不产生 NaN）", () => {
    expect(shareFromRaw(null)).toBe(0);
    expect(shareFromRaw(undefined)).toBe(0);
  });

  it("金额由分转元", () => {
    expect(yuanFromCents(123456)).toBe(1234.56);
    expect(yuanFromCents(1)).toBe(0.01);
  });

  it("金额空值按 0 处理", () => {
    expect(yuanFromCents(null)).toBe(0);
    expect(yuanFromCents(undefined)).toBe(0);
  });
});

describe("参考净值文案", () => {
  it("有值固定 4 位小数", () => {
    expect(navText(1.23456)).toBe("1.2346");
    expect(navText(2)).toBe("2.0000");
  });

  it("0 不算空值，仍按 4 位展示", () => {
    expect(navText(0)).toBe("0.0000");
  });

  it("null / undefined 展示 --", () => {
    expect(navText(null)).toBe("--");
    expect(navText(undefined)).toBe("--");
  });

  it("NaN 也按空值处理（原实现会渲染出 NaN）", () => {
    expect(navText(Number.NaN)).toBe("--");
  });
});

describe("短日期", () => {
  it("YYYY-MM-DD 截成 MM-DD", () => {
    expect(fmtShortDate("2026-03-05")).toBe("03-05");
  });

  it("非标准格式原样返回（不静默改写成 --）", () => {
    expect(fmtShortDate("2026/03/05")).toBe("2026/03/05");
  });

  it("空值展示 --", () => {
    expect(fmtShortDate(null)).toBe("--");
    expect(fmtShortDate(undefined)).toBe("--");
    expect(fmtShortDate("")).toBe("--");
  });
});

describe("分摊前置条件", () => {
  it("没有来源持仓时不允许改总价", () => {
    expect(canAllocate([])).toBe(false);
    expect(canAllocate([src(1, 100)])).toBe(true);
  });

  it("分摊分母为各来源市值之和（缺失按 0）", () => {
    expect(sourceWeightCents([src(1, 6000), src(2, 4000)])).toBe(10000);
    expect(
      sourceWeightCents([
        src(1, 6000),
        // 后端个别来源可能缺市值（未估值），不能算出 NaN
        { ...src(2, 0), market_value_cents: undefined as unknown as number }
      ])
    ).toBe(6000);
  });
});

describe("分摊预览（与后端同算法）", () => {
  it("按既有市值占比分摊，预览合计严格等于输入总价", () => {
    const rows = buildAllocationPreview([src(1, 6000), src(2, 4000)], 1000);
    expect(rows.map(r => r.allocatedYuan)).toEqual([600, 400]);
    expect(rows.map(r => r.ratioText)).toEqual(["60.0%", "40.0%"]);
    expect(previewSumYuan(rows)).toBe(1000);
  });

  it("整数分四舍五入后尾差归占比最大的一笔", () => {
    // 100 元按 1:1:1 摊：3333 分 ×3 = 9999，差 1 分归第一笔（并列最大取首条）
    const rows = buildAllocationPreview(
      [src(1, 100), src(2, 100), src(3, 100)],
      100
    );
    expect(rows.map(r => r.allocatedYuan)).toEqual([33.34, 33.33, 33.33]);
    expect(previewSumYuan(rows)).toBeCloseTo(100, 10);
  });

  it("尾差只落在占比最大的一笔（而不是第一条）", () => {
    // 1:1:1 太均匀看不出定向，换成 1:1:8 且总价除不尽
    const rows = buildAllocationPreview(
      [src(1, 10000), src(2, 10000), src(3, 80000)],
      33.33
    );
    // 3333 分：334 / 333 / 2666，合计 3333（差 0）
    expect(previewSumYuan(rows)).toBeCloseTo(33.33, 10);
    expect(rows[2].allocatedYuan).toBeGreaterThan(rows[0].allocatedYuan);
  });

  it("行 key 用 ledger_id + 下标（同账本多分红方式不会撞 key）", () => {
    const rows = buildAllocationPreview([src(7, 100), src(7, 100)], 10);
    expect(rows.map(r => r.key)).toEqual(["7-0", "7-1"]);
  });

  it("展示名回退：账本名 → 机构名 → 兜底", () => {
    const rows = buildAllocationPreview(
      [
        src(1, 100, { ledger_name: "支付宝-基金", institution_name: "某基金" }),
        src(2, 100, { ledger_name: null, institution_name: "某机构" }),
        src(3, 100, { ledger_name: null, institution_name: null })
      ],
      30
    );
    expect(rows.map(r => r.name)).toEqual([
      "支付宝-基金",
      "某机构",
      "未关联账户"
    ]);
  });

  it("分母为 0 时不给预览（避免除零得到一堆 NaN）", () => {
    expect(buildAllocationPreview([src(1, 0), src(2, 0)], 1000)).toEqual([]);
  });

  it("输入为空 / 0 / 负数 / 非数字时不给预览", () => {
    const sources = [src(1, 6000), src(2, 4000)];
    expect(buildAllocationPreview(sources, null)).toEqual([]);
    expect(buildAllocationPreview(sources, 0)).toEqual([]);
    expect(buildAllocationPreview(sources, -1)).toEqual([]);
    expect(buildAllocationPreview(sources, Number.NaN)).toEqual([]);
  });

  it("来源为空时不给预览", () => {
    expect(buildAllocationPreview([], 1000)).toEqual([]);
  });

  it("previewSumYuan 空数组为 0", () => {
    expect(previewSumYuan([])).toBe(0);
  });
});

describe("展示名 / 角标", () => {
  it("sourceDisplayName 与预览行同名口径", () => {
    expect(sourceDisplayName(src(1, 0, { ledger_name: "A" }))).toBe("A");
    expect(
      sourceDisplayName(src(1, 0, { ledger_name: null, institution_name: "B" }))
    ).toBe("B");
    expect(
      sourceDisplayName(
        src(1, 0, { ledger_name: null, institution_name: null })
      )
    ).toBe("未关联账户");
  });

  it("角标优先分红方式，其次管理人，都空则空串", () => {
    expect(
      dividendOrManagerText(
        src(1, 0, { dividend_preference: "红利转投", fund_manager: "张三" })
      )
    ).toBe("红利转投");
    expect(
      dividendOrManagerText(
        src(1, 0, { dividend_preference: null, fund_manager: "张三" })
      )
    ).toBe("张三");
    expect(
      dividendOrManagerText(
        src(1, 0, { dividend_preference: null, fund_manager: null })
      )
    ).toBe("");
  });
});

describe("资金进出提示（#1217）", () => {
  it("检测到资金进出且给出下一开盘日时拼出完整文案", () => {
    expect(
      cashFlowHintOf({
        cash_flow_detected: true,
        next_trading_day: "2026-03-09"
      })
    ).toBe(
      "本次分摊前该账户有资金进出记录，建议在下一个开盘日（2026-03-09）更新其他存量持仓的总价。"
    );
  });

  it("未检测到资金进出时不给提示", () => {
    expect(
      cashFlowHintOf({
        cash_flow_detected: false,
        next_trading_day: "2026-03-09"
      })
    ).toBeNull();
  });

  it("检测到但没有下一开盘日时不猜日期，宁可不提示", () => {
    expect(
      cashFlowHintOf({ cash_flow_detected: true, next_trading_day: null })
    ).toBeNull();
    expect(cashFlowHintOf({ cash_flow_detected: true })).toBeNull();
  });

  it("后端没返回 data 时不报错", () => {
    expect(cashFlowHintOf(undefined)).toBeNull();
    expect(cashFlowHintOf(null)).toBeNull();
  });
});
