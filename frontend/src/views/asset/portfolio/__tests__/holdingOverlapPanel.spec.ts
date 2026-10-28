/**
 * 持仓重叠度面板纯逻辑的回归网（#2604）。
 *
 * 判据纪律：断言完整行为，不只断言「函数存在」。
 * **本文件钉的是最要命的那条纪律**：「pairs 为空」有三种完全不同的成因，
 * 一律渲染成「重叠 0%」就是**错误安心** —— 用户会以为查过了、结果是零重合。
 * 1. 取数失败（degraded）→ 「暂时取不到」；
 * 2. 可比基金不足 2 只 → 「算不出」；
 * 3. 算出来了且 pairs 为空 → 结论是**确实不重叠**。
 */
import { describe, it, expect } from "vitest";
import {
  countSameSeriesPairs,
  describeBasis,
  describeCaveats,
  describeCoverage,
  describeDuplicateSummary,
  describeFoldHint,
  describeOverlapLevel,
  describePeriodMismatch,
  describeSkipped,
  FOLDED_PAGE_SIZE,
  formatAmountCents,
  formatJaccard,
  formatWeightedOverlap,
  pageFoldedPairs,
  resolveOverlapPanelState,
  splitOverlapPairs
} from "../holdingOverlapModel";
import type { HoldingOverlapData, OverlapPair } from "../holdingOverlapModel";

const pair = (over: Partial<OverlapPair> = {}): OverlapPair => ({
  fund_code_a: "110011",
  fund_name_a: "易方达优质精选",
  report_period_a: "2026Q2",
  fund_code_b: "005827",
  fund_name_b: "易方达蓝筹精选",
  report_period_b: "2026Q2",
  holding_basis: "top10",
  jaccard: 0.42,
  weighted_overlap: 18.6,
  overlap_amount_cents: 18600,
  overlap_level: "watch",
  overlap_reason: "共同重仓 1 只、18.6% 仓位重叠",
  common_holdings: [
    {
      stock_code: "600519",
      stock_name: "贵州茅台",
      ratio_a: 9.8,
      ratio_b: 8.4,
      min_ratio: 8.4
    }
  ],
  ...over
});

const data = (over: Partial<HoldingOverlapData> = {}): HoldingOverlapData => ({
  pairs: [pair()],
  fund_count: 3,
  skipped_basis_mismatch: 0,
  skipped_null_ratio: 0,
  total_market_value_cents: 1_000_000,
  coverage_pct: 82.5,
  uncovered: [],
  duplicate_count: 0,
  trivial_count: 0,
  min_overlap_amount_cents: 100000,
  caveats: ["重叠度基于基金定期报告披露的持仓快照，两次报告之间的调仓看不到。"],
  degraded: false,
  source: "fund_holdings",
  ...over
});

describe("重叠度面板状态判定（#2604）", () => {
  it("取数失败时是「暂时取不到」，不是「没有重叠」", () => {
    expect(resolveOverlapPanelState(data({ degraded: true, pairs: [] }))).toBe(
      "degraded"
    );
    expect(resolveOverlapPanelState(null)).toBe("degraded");
  });

  it("可比基金不足 2 只是「算不出」，不是「不重叠」", () => {
    expect(resolveOverlapPanelState(data({ fund_count: 1, pairs: [] }))).toBe(
      "not-computable"
    );
    expect(resolveOverlapPanelState(data({ fund_count: 0, pairs: [] }))).toBe(
      "not-computable"
    );
  });

  it("算出来了且没有共同重仓股，结论才是「确实不重叠」", () => {
    expect(resolveOverlapPanelState(data({ fund_count: 3, pairs: [] }))).toBe(
      "no-overlap"
    );
  });

  it("有重叠对时是「有重叠」", () => {
    expect(resolveOverlapPanelState(data())).toBe("has-pairs");
  });
});

describe("重叠度数值展示（#2604）", () => {
  it("加权口径按百分点展示", () => {
    // 用 18.66 而不是 18.65：后者在 IEEE754 下是 18.64999…，toFixed(1) 得 "18.6"
    expect(formatWeightedOverlap(18.66)).toBe("18.7%");
    expect(formatWeightedOverlap(18.6)).toBe("18.6%");
  });

  it("集合口径从 0~1 转成百分比", () => {
    expect(formatJaccard(0.42)).toBe("42%");
  });

  it("缺失值显示「—」而不是 0", () => {
    expect(formatWeightedOverlap(null)).toBe("—");
    expect(formatJaccard(undefined)).toBe("—");
    expect(formatJaccard(Number.NaN)).toBe("—");
  });

  it("极小正数不渲染成「0.0%」——列在重叠里却显示 0 会自相矛盾", () => {
    // 后端只下发 weighted_overlap > 0 的对，故 0.04 这种值只该显示下限，不该显示 0.0%
    expect(formatWeightedOverlap(0.04)).toBe("<0.1%");
    expect(formatWeightedOverlap(0.05)).toBe("0.1%");
    expect(formatWeightedOverlap(1.24)).toBe("1.2%");
  });
});

describe("重叠度口径说明（#2604）", () => {
  it("披露口径给出中文名", () => {
    expect(describeBasis("full")).toContain("全量");
    expect(describeBasis("top10")).toContain("前十大");
    expect(describeBasis("")).toBe("口径未知");
  });

  it("报告期错配时提示时点差，报告期相同则不提示", () => {
    expect(
      describePeriodMismatch(pair({ report_period_b: "2026Q1" }))
    ).toContain("报告期不同");
    expect(describePeriodMismatch(pair())).toBe("");
  });

  it("覆盖率说明带基金数", () => {
    expect(describeCoverage(data())).toContain("82.5%");
    expect(describeCoverage(data())).toContain("3");
  });

  it("披露口径不同而被跳过的对数要如实说出来", () => {
    const text = describeSkipped(data({ skipped_basis_mismatch: 2 }));
    expect(text).toContain("2");
    expect(text).toContain("披露口径");
  });

  it("占比缺失被排除的行数也要说出来", () => {
    const text = describeSkipped(data({ skipped_null_ratio: 5 }));
    expect(text).toContain("5");
    expect(text).toContain("占比缺失");
  });

  it("没有跳过项时不给空文案", () => {
    expect(describeSkipped(data())).toBe("");
  });
});

describe("配置重复提示（#866）", () => {
  it("duplicate 显示「配置重复」，watch 显示「需留意」，low 不占版面", () => {
    expect(describeOverlapLevel(pair({ overlap_level: "duplicate" }))).toEqual({
      label: "配置重复",
      tone: "danger"
    });
    expect(describeOverlapLevel(pair({ overlap_level: "watch" }))).toEqual({
      label: "需留意",
      tone: "warning"
    });
    expect(describeOverlapLevel(pair({ overlap_level: "low" }))).toBeNull();
  });

  it("同一基金的不同份额不得显示成「配置重复」", () => {
    // 同一只基金的 A/C 份额持仓逐行相同 ⇒ 算出来必然近 100% 重叠。
    // 若标成「配置重复」，用户会去卖掉本来正常持有的份额。
    const badge = describeOverlapLevel(pair({ overlap_level: "same-series" }));
    expect(badge?.label).not.toContain("配置重复");
    expect(badge?.label).toContain("份额");
    expect(badge?.tone).toBe("info");
  });

  it("汇总只数真重复，份额重复单独说", () => {
    const text = describeDuplicateSummary(
      data({
        pairs: [
          pair({ overlap_level: "duplicate" }),
          pair({ overlap_level: "same-series" })
        ],
        duplicate_count: 1
      })
    );
    expect(text).toContain("1 对配置重复");
    expect(text).toContain("1 对是同一基金的不同份额");
  });

  it("没有重复时不给汇总文案", () => {
    expect(
      describeDuplicateSummary(
        data({ pairs: [pair({ overlap_level: "low" })], duplicate_count: 0 })
      )
    ).toBe("");
  });

  it("份额重复的对数可单独统计（不混进配置重复）", () => {
    const payload = data({
      pairs: [
        pair({ overlap_level: "duplicate" }),
        pair({ overlap_level: "same-series" }),
        pair({ overlap_level: "same-series" })
      ]
    });
    expect(countSameSeriesPairs(payload)).toBe(2);
  });
});

describe("仓位闸门：观察仓不提示（#866 追加）", () => {
  it("trivial 不占版面——不能标成「配置重复」，也不该有任何标签", () => {
    // 实测场景：一只投 ¥0.53、一只投 ¥19,404，weighted 86.5%。
    // 比例上是重复，但重复的只有 4 毛 6；给标签就是把噪音贴回列表。
    expect(describeOverlapLevel(pair({ overlap_level: "trivial" }))).toBeNull();
  });

  it("金额格式化保留小额精度，大额加千分位", () => {
    expect(formatAmountCents(0)).toBe("¥0");
    expect(formatAmountCents(46)).toBe("¥0.46"); // 四舍五入成 ¥0 会像取数缺失
    expect(formatAmountCents(99)).toBe("¥0.99");
    expect(formatAmountCents(1250)).toBe("¥13"); // ≥1 元后取整：精确到分对判断没帮助
    expect(formatAmountCents(727957)).toBe("¥7,280");
    expect(formatAmountCents(null)).toBe("—");
  });

  it("汇总把「金额不足未提示」单独说，不混进配置重复数", () => {
    const text = describeDuplicateSummary(
      data({ duplicate_count: 3, trivial_count: 42 })
    );
    expect(text).toContain("3 对配置重复");
    // 提示线来自后端字段（分 → 元），前端不另写一个数
    expect(text).toContain("42 对重复投入不足 ¥1,000");
    expect(text).toContain("不计入提示");
  });

  it("只有 trivial 时不能给出「检出 N 对配置重复」——那是假的", () => {
    const text = describeDuplicateSummary(
      data({ duplicate_count: 0, trivial_count: 9 })
    );
    expect(text).not.toContain("配置重复");
    expect(text).toContain("9 对重复投入不足");
  });

  it("折叠只保留要点档位，low / trivial 归入折叠区", () => {
    const payload = data({
      pairs: [
        pair({ overlap_level: "duplicate" }),
        pair({ overlap_level: "watch" }),
        pair({ overlap_level: "same-series" }),
        pair({ overlap_level: "low" }),
        pair({ overlap_level: "trivial" }),
        pair({ overlap_level: "trivial" })
      ]
    });
    const { highlighted, folded, foldedCount } = splitOverlapPairs(payload);
    expect(highlighted.map(p => p.overlap_level)).toEqual([
      "duplicate",
      "watch",
      "same-series"
    ]);
    expect(folded.map(p => p.overlap_level)).toEqual([
      "low",
      "trivial",
      "trivial"
    ]);
    expect(foldedCount).toBe(3);
  });

  it("全部是要点时不给折叠计数", () => {
    expect(
      splitOverlapPairs(data({ pairs: [pair({ overlap_level: "duplicate" })] }))
    ).toEqual({
      highlighted: [pair({ overlap_level: "duplicate" })],
      folded: [],
      foldedCount: 0
    });
  });

  it("缺数据时不崩，折叠计数为 0", () => {
    expect(splitOverlapPairs(null)).toEqual({
      highlighted: [],
      folded: [],
      foldedCount: 0
    });
  });

  it("展开只渲染前 50 对，并如实报出没显示的条数", () => {
    // 真实库 1817 对折叠项：全量渲染 = 几千个 <li>，点一下「展开」标签页要僵住
    const folded = Array.from({ length: 120 }, () =>
      pair({ overlap_level: "trivial" as const })
    );
    const { visible, hiddenCount } = pageFoldedPairs(folded);
    expect(visible).toHaveLength(FOLDED_PAGE_SIZE);
    expect(hiddenCount).toBe(70);
  });

  it("折叠项不足一页时全部显示，没有隐藏计数", () => {
    const folded = [pair({ overlap_level: "trivial" as const })];
    expect(pageFoldedPairs(folded)).toEqual({
      visible: folded,
      hiddenCount: 0
    });
  });

  it("折叠说明：未展开时给条数，展开后给「还有多少没显示」", () => {
    // 实测文案：1817 对折叠 → 展开只渲染 50 对，必须说清 1767 对没显示，
    // 否则用户以为「已展开」= 看到全部
    const base = {
      foldedCount: 1817,
      visibleCount: 50,
      gateText: "¥1,000"
    };
    expect(describeFoldHint({ ...base, expanded: false, hiddenCount: 0 })).toBe(
      "另有 1817 对未达提示线（比例不够，或重复投入不足 ¥1,000），已折叠"
    );
    expect(
      describeFoldHint({ ...base, expanded: true, hiddenCount: 1767 })
    ).toBe("已展开前 50 对未达提示线的重叠，另有 1767 对金额更低的未显示");
    // 折叠项不足一页：不能凭空冒出「另有 0 对」
    expect(describeFoldHint({ ...base, expanded: true, hiddenCount: 0 })).toBe(
      "已展开前 50 对未达提示线的重叠"
    );
  });
});

describe("口径声明（#866 换手率约束）", () => {
  it("原样透传后端的口径声明", () => {
    const caveats = describeCaveats(
      data({ caveats: ["持仓是快照", "高换手基金失真"] })
    );
    expect(caveats).toEqual(["持仓是快照", "高换手基金失真"]);
  });

  it("空串项被滤掉，不渲染空行", () => {
    expect(describeCaveats(data({ caveats: ["有内容", "   ", ""] }))).toEqual([
      "有内容"
    ]);
  });

  it("缺字段时返回空数组而不是崩", () => {
    expect(describeCaveats(null)).toEqual([]);
  });
});
