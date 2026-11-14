/**
 * 首页「心理账户」卡的派生判据（纯函数，node 环境可测）。
 *
 * 这里钉的是三条容易退化的边界：
 *
 * 1. **空档必须保留**：`allocation_distribution` 只列非零桶是给图表的契约，
 *    卡片若也照抄，「保命钱为 0」就永远看不见——空档本身是财务信号。
 * 2. **档位名只能来自后端**：提示语里的「活钱」必须取 `buckets[].label`，
 *    一旦有人硬编码中文，后端改名就会两处不一致。
 * 3. **占比文案不能自相矛盾**：金额 ¥1,224 摆在旁边，百分比写 `0%` 就是撒谎。
 */
import { describe, expect, it } from "vitest";
import type { DistributionsData } from "@/api/summary";
import {
  buildMentalAccountView,
  percentTextOf,
  scopeFootnote
} from "../mentalAccounts";

function makeDist(
  overrides: Partial<DistributionsData> = {}
): DistributionsData {
  return {
    type_distribution: [],
    allocation_distribution: [{ name: "长期增值", value: 709369.8 }],
    market_distribution: [],
    account_distribution: [],
    category_distribution: [],
    liability_distribution: [],
    total_assets: 3384804.89,
    total_liabilities: 1760000,
    net_worth: 1624804.89,
    positions_total_mv: 709369.8,
    allocation_scope: {
      denominator: 709369.8,
      excluded_total: 2250091,
      excluded: [
        { name: "固定资产", value: 2200091 },
        { name: "应收款", value: 50000 }
      ],
      liabilities_total: 1760000,
      buckets: [
        { key: "liquid", label: "活钱", value: 0 },
        { key: "stable", label: "稳健底仓", value: 0 },
        { key: "longterm", label: "长期增值", value: 709369.8 },
        { key: "speculative", label: "高风险博弈", value: 0 },
        { key: "security", label: "保险保障", value: 0 }
      ]
    },
    ...overrides
  };
}

describe("percentTextOf", () => {
  it("≥1% 取整，<1% 留一位，再小就不写 0%", () => {
    expect(percentTextOf(709369.8, 709369.8)).toBe("100%");
    expect(percentTextOf(1224, 710593.8)).toBe("0.2%");
    expect(percentTextOf(10, 709379.8)).toBe("＜0.1%");
  });

  it("零值与零分母都是 0%", () => {
    expect(percentTextOf(0, 100)).toBe("0%");
    expect(percentTextOf(100, 0)).toBe("0%");
  });
});

describe("buildMentalAccountView", () => {
  it("五档全在，空档保留且标记 empty", () => {
    const view = buildMentalAccountView(makeDist())!;
    expect(view.items.map(i => i.key)).toEqual([
      "liquid",
      "stable",
      "longterm",
      "speculative",
      "security"
    ]);
    expect(view.items.filter(i => i.empty).map(i => i.key)).toEqual([
      "liquid",
      "stable",
      "speculative",
      "security"
    ]);
    // 反向验证锚点：有人把空档过滤掉，这里立刻红
    expect(view.items).toHaveLength(5);
  });

  it("每个档位拿到自己的语义色，不是同一个兜底色", () => {
    const view = buildMentalAccountView(makeDist())!;
    const colors = view.items.map(i => i.color);
    expect(colors).toEqual([
      "var(--sankey-liquid)",
      "var(--sankey-stable)",
      "var(--sankey-longterm)",
      "var(--sankey-speculative)",
      "var(--sankey-security)"
    ]);
  });

  it("占比按分母算，不是按最大的那档算", () => {
    const dist = makeDist();
    dist.allocation_scope!.buckets = [
      { key: "liquid", label: "活钱", value: 50000 },
      { key: "stable", label: "稳健底仓", value: 0 },
      { key: "longterm", label: "长期增值", value: 150000 },
      { key: "speculative", label: "高风险博弈", value: 0 },
      { key: "security", label: "保险保障", value: 0 }
    ];
    dist.allocation_scope!.denominator = 200000;
    const view = buildMentalAccountView(dist)!;
    expect(view.items.map(i => i.percentText)).toEqual([
      "25%",
      "0%",
      "75%",
      "0%",
      "0%"
    ]);
  });

  it("活钱为 0 时给提示，档位名取后端 label 而不是硬编码「活钱」", () => {
    const view = buildMentalAccountView(makeDist())!;
    expect(view.liquidHint).toContain("活钱为 0");
    expect(view.liquidHint).toContain("账户现金");

    // 后端改档位名，提示语跟着改（硬编码就会在这里红）
    const renamed = makeDist();
    renamed.allocation_scope!.buckets![0].label = "流动资金";
    expect(buildMentalAccountView(renamed)!.liquidHint).toContain(
      "流动资金为 0"
    );
  });

  it("活钱有金额就不提示", () => {
    const dist = makeDist();
    dist.allocation_scope!.buckets![0].value = 1224;
    dist.allocation_scope!.denominator = 710593.8;
    expect(buildMentalAccountView(dist)!.liquidHint).toBeNull();
  });

  it("分母为 0 时不说「活钱为 0」，那不是漏录而是没资产", () => {
    const dist = makeDist();
    dist.allocation_scope!.denominator = 0;
    dist.allocation_scope!.buckets = dist.allocation_scope!.buckets!.map(b => ({
      ...b,
      value: 0
    }));
    const view = buildMentalAccountView(dist)!;
    expect(view.denominator).toBe(0);
    expect(view.liquidHint).toBeNull();
  });

  it("未响应时返回 null，让组件区分「加载中」与「真的没有」", () => {
    expect(buildMentalAccountView(null)).toBeNull();
  });

  it("退化路径：老响应缺 buckets 时只列非零桶，且不伪造档位名", () => {
    const dist = makeDist();
    delete dist.allocation_scope!.buckets;
    const view = buildMentalAccountView(dist)!;
    expect(view.items).toHaveLength(1);
    expect(view.items[0].name).toBe("长期增值");
    // 没有 key 就找不到语义色，也不能硬凑一个品牌色冒充档位色
    expect(view.items[0].color).toBe("var(--text-primary)");
    expect(view.liquidHint).toBeNull();
  });
});

describe("scopeFootnote", () => {
  it("分母 / 未纳入逐项 / 负债三段都写出来", () => {
    const view = buildMentalAccountView(makeDist())!;
    const text = scopeFootnote(view);
    expect(text).toContain("分母 ¥709,370");
    expect(text).toContain("固定资产 ¥2,200,091");
    expect(text).toContain("应收款 ¥50,000");
    expect(text).toContain("负债 ¥1,760,000（不计入）");
  });

  it("没有未纳入项时不留空壳「未纳入」字样", () => {
    const dist = makeDist();
    dist.allocation_scope!.excluded = [];
    dist.allocation_scope!.excluded_total = 0;
    dist.allocation_scope!.liabilities_total = 0;
    expect(scopeFootnote(buildMentalAccountView(dist)!)).toBe("分母 ¥709,370");
  });
});
