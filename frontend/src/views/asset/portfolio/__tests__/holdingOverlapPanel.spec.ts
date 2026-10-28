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
  describeOverlapLevel,
  describeOverlapTally,
  describePeriodMismatch,
  describeSkipped,
  describeWeakHint,
  describeWeakReason,
  filterWeakPairs,
  formatAmountCents,
  formatJaccard,
  formatWeightedOverlap,
  resolveOverlapPanelState,
  sliceWeakPairs,
  splitOverlapPairs,
  tallyOverlap,
  WEAK_PAGE_SIZE
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
  weak_count: 0,
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

  it("汇总按档位分开计数，份额重复不被算成配置重复", () => {
    const chips = describeOverlapTally(
      data({
        pairs: [
          pair({ overlap_level: "duplicate" }),
          pair({ overlap_level: "same-series" }),
          pair({ overlap_level: "low" })
        ]
      })
    );
    const byKey = Object.fromEntries(chips.map(chip => [chip.key, chip.count]));
    expect(byKey.duplicate).toBe(1);
    expect(byKey.sameSeries).toBe(1);
    expect(byKey.weak).toBe(1);
    // 没有 watch 就不占一个「0」位置——空档位只会让汇总条变长
    expect(byKey.watch).toBeUndefined();
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

describe("分档：小仓位进弱提醒而不是消失（#866 追加）", () => {
  it("trivial 不进要点列表，也不贴「配置重复」标签", () => {
    // 实测场景：一只投 ¥0.53、一只投 ¥19,404，weighted 86.5%。
    // 比例上是重复，但重复的只有 4 毛 6；贴标签就是把噪音贴回第一屏。
    expect(describeOverlapLevel(pair({ overlap_level: "trivial" }))).toBeNull();
    expect(describeOverlapLevel(pair({ overlap_level: "low" }))).toBeNull();
  });

  it("金额格式化保留小额精度，大额加千分位", () => {
    expect(formatAmountCents(0)).toBe("¥0");
    expect(formatAmountCents(46)).toBe("¥0.46"); // 四舍五入成 ¥0 会像取数缺失
    expect(formatAmountCents(99)).toBe("¥0.99");
    expect(formatAmountCents(1250)).toBe("¥13"); // ≥1 元后取整：精确到分对判断没帮助
    expect(formatAmountCents(727957)).toBe("¥7,280");
    expect(formatAmountCents(null)).toBe("—");
  });

  it("四类计数互斥，加起来正好等于 pairs 条数", () => {
    const payload = data({
      pairs: [
        pair({ overlap_level: "duplicate" }),
        pair({ overlap_level: "duplicate" }),
        pair({ overlap_level: "watch" }),
        pair({ overlap_level: "same-series" }),
        pair({ overlap_level: "low" }),
        pair({ overlap_level: "trivial" })
      ]
    });
    const tally = tallyOverlap(payload);
    expect(tally).toEqual({ duplicate: 2, watch: 1, sameSeries: 1, weak: 2 });
    const total = tally.duplicate + tally.watch + tally.sameSeries + tally.weak;
    expect(total).toBe(payload.pairs.length);
  });

  it("计数从 pairs 现算，不读摘要字段（否则会出现标题与列表不一致）", () => {
    // 后端字段与列表漂移时（缓存/版本错配），页面必须以「看到的列表」为准
    const tally = tallyOverlap(
      data({
        pairs: [
          pair({ overlap_level: "trivial" }),
          pair({ overlap_level: "trivial" })
        ],
        weak_count: 99,
        duplicate_count: 7
      })
    );
    expect(tally.weak).toBe(2);
    expect(tally.duplicate).toBe(0);
  });

  it("弱提醒不混进「配置重复」：那 10 对是 10 对，不是 1827 对", () => {
    const chips = describeOverlapTally(
      data({
        pairs: [
          ...Array.from({ length: 3 }, () =>
            pair({ overlap_level: "duplicate" as const })
          ),
          ...Array.from({ length: 42 }, () =>
            pair({ overlap_level: "trivial" as const })
          )
        ]
      })
    );
    const duplicateChip = chips.find(chip => chip.key === "duplicate");
    const weakChip = chips.find(chip => chip.key === "weak");
    expect(duplicateChip?.count).toBe(3);
    expect(weakChip?.count).toBe(42);
    // 弱提醒是灰档，不能借用「配置重复」的红
    expect(weakChip?.tone).toBe("muted");
  });

  it("只有弱提醒时，汇总里根本不该出现「配置重复」", () => {
    const chips = describeOverlapTally(
      data({
        pairs: Array.from({ length: 9 }, () =>
          pair({ overlap_level: "trivial" as const })
        )
      })
    );
    expect(chips.map(chip => chip.label)).toEqual(["弱提醒"]);
  });

  it("拆堆：要点是 duplicate/watch/same-series，弱提醒是 low/trivial", () => {
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
    const { primary, weak } = splitOverlapPairs(payload);
    expect(primary.map(p => p.overlap_level)).toEqual([
      "duplicate",
      "watch",
      "same-series"
    ]);
    // 弱提醒**保留**而不是丢弃：用户想核对「我是不是买重了」时必须找得到
    expect(weak.map(p => p.overlap_level)).toEqual([
      "low",
      "trivial",
      "trivial"
    ]);
  });

  it("缺数据时不崩，两堆都是空", () => {
    expect(splitOverlapPairs(null)).toEqual({ primary: [], weak: [] });
    expect(tallyOverlap(null)).toEqual({
      duplicate: 0,
      watch: 0,
      sameSeries: 0,
      weak: 0
    });
  });

  it("弱提醒说明同时交代「为什么降档」和「怎么看全部」", () => {
    const hint = describeWeakHint("¥1,000");
    expect(hint).toContain("¥1,000"); // 分档线来自后端，前端不另写一个数
    expect(hint).toContain("观察仓");
    expect(hint).toContain("折叠");
    expect(hint).toContain("查看"); // 折叠 ≠ 藏起来，必须告诉用户能看到
  });

  it("low 没有后端理由时补一句兜底，否则用户不知道它为什么在这", () => {
    expect(
      describeWeakReason(
        pair({
          overlap_level: "low",
          overlap_reason: "",
          weighted_overlap: 6.4
        })
      )
    ).toBe("重合 6.4%，未达「需留意」的仓位线");
    // 后端给了理由就原样用——它比前端拼的更准（含触发点）
    expect(
      describeWeakReason(
        pair({
          overlap_reason: "重叠 94.8% 但重复投入约 ¥12，低于 ¥1,000，仅作弱提醒"
        })
      )
    ).toContain("仅作弱提醒");
  });

  it("筛选命中基金代码或名称，大小写不敏感", () => {
    const weak = [
      pair({ fund_code_a: "012414", fund_name_a: "招商中证白酒C" }),
      pair({ fund_code_a: "017513", fund_name_a: "广发北证50C" }),
      pair({ fund_code_a: "161725", fund_name_a: "招商中证白酒A" }),
      pair({ fund_code_a: "000001", fund_name_a: "华夏上证50ETF" })
    ];
    expect(filterWeakPairs(weak, "白酒").map(p => p.fund_code_a)).toEqual([
      "012414",
      "161725"
    ]);
    expect(filterWeakPairs(weak, "017513").map(p => p.fund_code_a)).toEqual([
      "017513"
    ]);
    expect(filterWeakPairs(weak, "etf").map(p => p.fund_code_a)).toEqual([
      "000001"
    ]);
    // 空关键词 = 不筛选（返回全量，而不是空数组）
    expect(filterWeakPairs(weak, "   ")).toHaveLength(4);
  });

  it("分页：默认一页 50 条，剩余条数如实报", () => {
    // 真实库 1817 对弱提醒：全量渲染 = 几千个 <li>，标签页会僵住
    const weak = Array.from({ length: 120 }, () =>
      pair({ overlap_level: "trivial" as const })
    );
    const first = sliceWeakPairs(weak, WEAK_PAGE_SIZE);
    expect(first.visible).toHaveLength(WEAK_PAGE_SIZE);
    expect(first.remaining).toBe(70);
    expect(first.hasMore).toBe(true);

    const all = sliceWeakPairs(weak, 120);
    expect(all.visible).toHaveLength(120);
    expect(all.remaining).toBe(0);
    expect(all.hasMore).toBe(false);

    // 加载数超过总数也不能越界报负数
    const over = sliceWeakPairs(weak, 200);
    expect(over.visible).toHaveLength(120);
    expect(over.remaining).toBe(0);
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
