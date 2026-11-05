import { describe, expect, it } from "vitest";
import {
  createFormatGuides,
  IMPORT_WIZARD_STEPS,
  FUND_TABLE_COLUMNS,
  STOCK_TABLE_COLUMNS,
  columnsForMode
} from "../importWizardData";

const GUIDE_KEYS = [
  "standard_stock",
  "standard_fund",
  "ths",
  "tiantian_fund",
  "alipay_fund",
  "alipay_pdf"
];

const PROPS = [
  "status",
  "product",
  "opType",
  "trade_date",
  "quantity",
  "price",
  "amount",
  "fee",
  "allocation"
];

describe("createFormatGuides", () => {
  it("恰好 6 个格式 key，多一个少一个都要红", () => {
    expect(Object.keys(createFormatGuides()).sort()).toEqual(
      [...GUIDE_KEYS].sort()
    );
  });

  it("每个 guide 的 title / tips 均非空，tips 全为字符串", () => {
    const guides = createFormatGuides();
    for (const guide of Object.values(guides)) {
      expect(guide.title.length).toBeGreaterThan(0);
      expect(guide.tips.length).toBeGreaterThan(0);
      for (const tip of guide.tips) {
        expect(typeof tip).toBe("string");
        expect(tip.length).toBeGreaterThan(0);
      }
    }
  });

  it("standard_fund 有 5 条 tips，其余格式各 4 条", () => {
    const guides = createFormatGuides();
    expect(guides.standard_fund.tips).toHaveLength(5);
    for (const key of GUIDE_KEYS.filter(k => k !== "standard_fund")) {
      expect(guides[key as keyof typeof guides].tips).toHaveLength(4);
    }
  });

  it("关键文案锚定（防搬运手滑改写）", () => {
    const guides = createFormatGuides();
    expect(guides.alipay_pdf.tips.join("\n")).toContain("基金交易明细");
    expect(guides.ths.tips.join("\n")).toContain("制表符分隔的文本文件");
    expect(guides.standard_fund.tips.join("\n")).toContain("红利再投资");
  });

  it("工厂语义：每次返回独立副本（对象与 tips 数组都不共享引用）", () => {
    const a = createFormatGuides();
    const b = createFormatGuides();

    expect(a).not.toBe(b);
    expect(a.standard_stock).not.toBe(b.standard_stock);
    expect(a.standard_stock.tips).not.toBe(b.standard_stock.tips);

    a.standard_stock.title = "改过";
    expect(b.standard_stock.title).not.toBe("改过");
  });
});

describe("IMPORT_WIZARD_STEPS", () => {
  it("4 步，标题依次为 选择导入账户 / 上传交易文件 / 预览与修正 / 导入完成", () => {
    expect(IMPORT_WIZARD_STEPS).toHaveLength(4);
    expect(IMPORT_WIZARD_STEPS.map(s => s.title)).toEqual([
      "选择导入账户",
      "上传交易文件",
      "预览与修正",
      "导入完成"
    ]);
  });
});

describe("columnsForMode", () => {
  it("基金与股票模式都是 9 列，prop 序列一致", () => {
    expect(columnsForMode(true)).toHaveLength(9);
    expect(columnsForMode(false)).toHaveLength(9);
    expect(columnsForMode(true).map(c => c.prop)).toEqual(PROPS);
    expect(columnsForMode(false).map(c => c.prop)).toEqual(PROPS);
  });

  it("文案差异锁定：基金 份额/确认净值/金额，股票 数量/单价/交易金额", () => {
    const fund = columnsForMode(true);
    const stock = columnsForMode(false);
    const labelOf = (cols: typeof fund, prop: string) =>
      cols.find(c => c.prop === prop)?.label;

    expect(labelOf(fund, "quantity")).toBe("份额");
    expect(labelOf(fund, "price")).toBe("确认净值");
    expect(labelOf(fund, "amount")).toBe("金额");

    expect(labelOf(stock, "quantity")).toBe("数量");
    expect(labelOf(stock, "price")).toBe("单价");
    expect(labelOf(stock, "amount")).toBe("交易金额");
  });

  it("两套都有「手续费」，且 fee 紧跟在 amount 之后", () => {
    for (const cols of [FUND_TABLE_COLUMNS, STOCK_TABLE_COLUMNS]) {
      const props = cols.map(c => c.prop);
      expect(cols.find(c => c.prop === "fee")?.label).toBe("手续费");
      expect(props.indexOf("fee")).toBe(props.indexOf("amount") + 1);
    }
  });

  it("宽度预算：各自 minWidth 合计 + 170（勾选 50 + 操作 120）≤ 1060", () => {
    for (const cols of [FUND_TABLE_COLUMNS, STOCK_TABLE_COLUMNS]) {
      const sum = cols.reduce((acc, c) => acc + c.minWidth, 0);
      expect(sum + 170).toBeLessThanOrEqual(1060);
    }
  });
});
