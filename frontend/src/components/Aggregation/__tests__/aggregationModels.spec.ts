import { describe, expect, it } from "vitest";
import { reactive } from "vue";
import type {
  AggregationProductGroup,
  AggregationResult,
  AggregationSource
} from "@/api/ledger";
import {
  formatReturnPct,
  returnBadgeClass,
  shortDate,
  useProductCardModel
} from "../productCardModel";
import { buildTypeOptions } from "../aggregationToolbarModel";

/**
 * #980 拆分回归：聚合视图模型层的口径。
 *
 * 这几条断言锁的是「拆分前后卡片显示的数字必须一模一样」——
 * 模型层被搬出组件后，谁改动派生逻辑都会在这里变红。
 */
describe("formatReturnPct：收益率文案", () => {
  it("无成本数据（null）显示 --，不当成 0.00%", () => {
    expect(formatReturnPct(null)).toBe("--");
    expect(formatReturnPct(undefined)).toBe("--");
  });

  it("正收益带 +，负收益带 -，0 也带 +", () => {
    expect(formatReturnPct(0.079)).toBe("+7.90%");
    expect(formatReturnPct(-0.0123)).toBe("-1.23%");
    expect(formatReturnPct(0)).toBe("+0.00%");
  });
});

describe("returnBadgeClass：涨跌语义", () => {
  it("null / 0 走中性，正负分明", () => {
    expect(returnBadgeClass(null)).toBe("return-badge--flat");
    expect(returnBadgeClass(0)).toBe("return-badge--flat");
    expect(returnBadgeClass(0.001)).toBe("return-badge--positive");
    expect(returnBadgeClass(-0.001)).toBe("return-badge--negative");
  });
});

describe("shortDate：只折叠 YYYY-MM-DD", () => {
  it("标准日期折成 MM-DD，其它形态原样返回", () => {
    expect(shortDate("2026-10-27")).toBe("10-27");
    expect(shortDate("2026/10/27")).toBe("2026/10/27");
    expect(shortDate(null)).toBeNull();
    expect(shortDate("")).toBeNull();
  });
});

const group = (over: Partial<AggregationProductGroup> = {}) =>
  ({
    symbol: "000001",
    name: "华夏成长",
    quantity: 12000,
    market_value_cents: 123456,
    nav_yuan: 1.2345,
    return_pct: 0.079,
    fund_manager: "张三",
    snapshot_date: "2026-10-27",
    sources: [],
    ...over
  }) as unknown as AggregationProductGroup;

const source = (over: Partial<AggregationSource> = {}) =>
  ({
    ledger_id: 1,
    ledger_name: "招商银行",
    institution_name: "招商银行股份有限公司",
    institution_alias: "招行",
    symbol: "600519",
    name: "贵州茅台",
    quantity: 20000,
    market_value_cents: 500000,
    return_pct: -0.02,
    snapshot_date: "2026-10-26",
    ...over
  }) as unknown as AggregationSource;

describe("useProductCardModel：product 模式", () => {
  it("份额除以 10000、市值除以 100，副标题取基金管理人", () => {
    const m = useProductCardModel(
      reactive({ group: group(), mode: "product" })
    );
    expect(m.shares.value).toBeCloseTo(1.2);
    expect(m.marketValueYuan.value).toBeCloseTo(1234.56);
    expect(m.subtitle.value).toBe("张三");
    expect(m.subtitleIcon.value).toBe("");
    expect(m.nav.value).toBe(1.2345);
    expect(m.displayDate.value).toBe("10-27");
  });

  it("多渠道持有：>1 才提示，tooltip 列出账本名", () => {
    const single = useProductCardModel(
      reactive({
        group: group({ sources: [source({ ledger_name: "A" })] }),
        mode: "product"
      })
    );
    expect(single.multiChannelHint.value).toBe(false);

    const multi = useProductCardModel(
      reactive({
        group: group({
          sources: [source({ ledger_name: "A" }), source({ ledger_name: "B" })]
        }),
        mode: "product"
      })
    );
    expect(multi.multiChannelHint.value).toBe(true);
    expect(multi.channelCount.value).toBe(2);
    expect(multi.channelTooltip.value).toBe("该基金分散在 2 个账户持有：A、B");
  });
});

describe("useProductCardModel：institution 模式", () => {
  it("副标题取账本名，tooltip 用机构全称 + 别名，净值由父级传入", () => {
    const m = useProductCardModel(
      reactive({
        source: source(),
        mode: "institution",
        navYuan: 9.8765
      })
    );
    expect(m.productName.value).toBe("贵州茅台");
    expect(m.subtitle.value).toBe("招商银行");
    expect(m.subtitleIcon.value).toBe("ep:wallet");
    expect(m.subtitleTitle.value).toBe("招商银行股份有限公司（招行）");
    expect(m.nav.value).toBe(9.8765);
    expect(m.marketValueYuan.value).toBeCloseTo(5000);
    expect(m.multiChannelHint.value).toBe(false);
    expect(m.channelTooltip.value).toBe("");
  });

  it("字段缺失时兜底 -- / 0，不抛错", () => {
    const m = useProductCardModel(reactive({ mode: "institution" }));
    expect(m.productName.value).toBe("--");
    expect(m.productCode.value).toBe("");
    expect(m.subtitle.value).toBeNull();
    expect(m.shares.value).toBe(0);
    expect(m.marketValueYuan.value).toBe(0);
    expect(m.displayDate.value).toBeNull();
  });
});

const result = (over: Partial<AggregationResult> = {}) =>
  ({ ...over }) as unknown as AggregationResult;

describe("buildTypeOptions：类型 Tab 只列有产品的分类", () => {
  it("fund_type 侧：过滤计数为 0 的分类，未分类按需追加", () => {
    const opts = buildTypeOptions(
      result({
        fund_type_counts: { 股票型: 3, 债券型: 0, 混合型: 2 },
        fund_type_unclassified_count: 1
      }),
      "fund_type"
    );
    expect(opts.map(o => o.label)).toEqual([
      "全部",
      "股票型",
      "混合型",
      "未分类"
    ]);
    expect(opts[3].value).toBe("__none__");
  });

  it("未分类为 0 时不出现「未分类」", () => {
    const opts = buildTypeOptions(
      result({
        fund_type_counts: { 股票型: 3 },
        fund_type_unclassified_count: 0
      }),
      "fund_type"
    );
    expect(opts.map(o => o.label)).toEqual(["全部", "股票型"]);
  });

  it("asset_type 侧：从中文明细反查原始枚举值", () => {
    const opts = buildTypeOptions(
      result({
        fund_type_breakdown: [
          { name: "股票", market_value_cents: 100 },
          { name: "ETF", market_value_cents: 200 }
        ]
      } as Partial<AggregationResult>),
      "asset_type"
    );
    expect(opts).toEqual([
      { label: "全部", value: "" },
      { label: "股票", value: "stock" },
      { label: "ETF", value: "etf" }
    ]);
  });

  it("result 为 null 时只留「全部」，不抛错", () => {
    expect(buildTypeOptions(null, "fund_type")).toEqual([
      { label: "全部", value: "" }
    ]);
  });
});
