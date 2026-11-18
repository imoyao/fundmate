import { describe, expect, it } from "vitest";
import {
  fundTypeColorMap,
  typeColorMap,
  ledgerTypeMap,
  getTemplateKeyForLedger,
  formatFileSize,
  getFundTypeColor,
  getTypeColor,
  addRowKeys,
  getRowClassName,
  getCellClassName,
  getCategoryDesc,
  getCategoryTagType
} from "../importPresentation";
import type { LedgerItem } from "@/api/ledger";

const ledger = (ledger_type: string) =>
  ({ ledger_type }) as unknown as LedgerItem;

describe("展示用常量映射（完整键值逐字钉住，防漏项 / 防改名）", () => {
  it("fundTypeColorMap", () => {
    expect(fundTypeColorMap).toEqual({
      股票型: "var(--asset-cat-stock)",
      混合型: "var(--asset-cat-fund)",
      债券型: "var(--asset-cat-bond)",
      货币型: "var(--asset-cat-money-fund)",
      指数型: "var(--asset-cat-etf)",
      QDII: "var(--asset-cat-fund)",
      FOF: "var(--asset-cat-portfolio)"
    });
  });

  it("typeColorMap", () => {
    expect(typeColorMap).toEqual({
      stock: "var(--asset-cat-stock)",
      fund: "var(--asset-cat-fund)",
      bond: "var(--asset-cat-bond)",
      etf: "var(--asset-cat-etf)",
      crypto: "var(--asset-cat-crypto)",
      saving: "var(--asset-cat-saving)",
      cash: "var(--asset-cat-money-fund)",
      static: "var(--color-neutral)"
    });
  });

  it("ledgerTypeMap", () => {
    expect(ledgerTypeMap).toEqual({
      stock: "股票账户",
      fund: "基金账户",
      cash: "现金账户",
      general: "综合账户",
      family: "家庭账户"
    });
  });

  it("ledgerTypeMap 未知键 → undefined", () => {
    expect(ledgerTypeMap["unknown"]).toBeUndefined();
  });
});

describe("formatFileSize", () => {
  it.each([
    [0, "0 B"],
    [1023, "1023 B"],
    [1024, "1.0 KB"],
    [1536, "1.5 KB"],
    [1048575, "1024.0 KB"],
    [1048576, "1.00 MB"],
    [1572864, "1.50 MB"],
    [5 * 1024 * 1024, "5.00 MB"]
  ])("%i → %s", (bytes, expected) => {
    expect(formatFileSize(bytes)).toBe(expected);
  });
});

describe("getFundTypeColor", () => {
  it.each([
    ["股票型", "var(--asset-cat-stock)"],
    ["FOF", "var(--asset-cat-portfolio)"],
    ["未知类型", "var(--palette-stone-gray)"]
  ])("%s → %s", (typeName, expected) => {
    expect(getFundTypeColor(typeName)).toBe(expected);
  });
});

describe("getTypeColor", () => {
  it.each([
    ["stock", "var(--asset-cat-stock)"],
    ["cash", "var(--asset-cat-money-fund)"],
    ["static", "var(--color-neutral)"],
    ["unknown", "var(--palette-stone-gray)"]
  ])("%s → %s", (type, expected) => {
    expect(getTypeColor(type)).toBe(expected);
  });
});

describe("getTemplateKeyForLedger", () => {
  const templateCases: Array<[string | null, string]> = [
    [null, ""],
    ["stock", "standard_stock"],
    ["fund", "standard_fund"],
    ["cash", "standard_fund"],
    ["general", ""]
  ];

  it.each(templateCases)("ledger_type=%s → %s", (type, expected) => {
    expect(getTemplateKeyForLedger(type === null ? null : ledger(type))).toBe(
      expected
    );
  });
});

describe("addRowKeys", () => {
  it("逐行补 _rowKey 并覆盖旧值", () => {
    expect(addRowKeys([{ a: 1 }, { b: 2, _rowKey: "old" }])).toEqual([
      { a: 1, _rowKey: "row_0" },
      { b: 2, _rowKey: "row_1" }
    ]);
  });

  it("不改动原数组与原对象（浅拷贝 + 覆盖旧 _rowKey）", () => {
    const first = { a: 1 };
    const second = { b: 2, _rowKey: "old" };
    const input = [first, second];
    const result = addRowKeys(input);

    expect(input).toEqual([{ a: 1 }, { b: 2, _rowKey: "old" }]);
    expect(input[0]).toBe(first);
    expect(input[1]).toBe(second);
    expect(result[0]).not.toBe(first);
    expect(result[1]).not.toBe(second);
    expect(first).not.toHaveProperty("_rowKey");
    expect(second._rowKey).toBe("old");
  });

  it("空数组 → 空数组", () => {
    expect(addRowKeys([])).toEqual([]);
  });

  it("3 行按数组下标生成 row_0 / row_1 / row_2", () => {
    expect(addRowKeys([{ a: 1 }, { a: 2 }, { a: 3 }])).toEqual([
      { a: 1, _rowKey: "row_0" },
      { a: 2, _rowKey: "row_1" },
      { a: 3, _rowKey: "row_2" }
    ]);
  });

  it("嵌套对象引用相同（浅拷贝而非深拷贝）", () => {
    const nested = { v: 1 };
    const input = [{ nested }];
    const result = addRowKeys(input);

    expect(result[0].nested).toBe(nested);
    expect(result[0].nested).toBe(input[0].nested);
  });
});

describe("getRowClassName", () => {
  it("重复行优先于 error / blocked → row-duplicate", () => {
    expect(
      getRowClassName({
        row: { is_duplicate: true, error: "解析失败", quantity: 0, price: 10 }
      })
    ).toBe("row-duplicate");
  });

  it("error → row-blocked", () => {
    expect(getRowClassName({ row: { error: "解析失败" } })).toBe("row-blocked");
  });

  it("isRowBlocked 行（quantity 0 / price 10）→ row-blocked", () => {
    expect(getRowClassName({ row: { quantity: 0, price: 10 } })).toBe(
      "row-blocked"
    );
  });

  it("正常行 → 空串", () => {
    expect(getRowClassName({ row: { quantity: 1, price: 10 } })).toBe("");
  });

  const exemptionCases: Array<[string, Record<string, unknown>]> = [
    ["is_cash_transfer", { is_cash_transfer: true, quantity: 0, price: 0 }],
    ["consumed_by", { consumed_by: "bond_redeem", quantity: 0, price: 0 }],
    [
      "QTY_PRICE_OPTIONAL_OPS(dividend)",
      { op_type: "dividend", quantity: 0, price: 0 }
    ]
  ];

  it.each(exemptionCases)("%s 豁免行 → 空串", (_label, row) => {
    expect(getRowClassName({ row })).toBe("");
  });
});

describe("getCellClassName", () => {
  it("blocked 行 + quantity 列 → cell-blocked", () => {
    expect(
      getCellClassName({
        row: { quantity: 0, price: 10 },
        column: { property: "quantity" }
      })
    ).toBe("cell-blocked");
  });

  it("blocked 行 + price 列 → cell-blocked", () => {
    expect(
      getCellClassName({
        row: { quantity: 0, price: 10 },
        column: { property: "price" }
      })
    ).toBe("cell-blocked");
  });

  it("重复且 blocked 的行 + quantity 列 → 空串（!row.is_duplicate 生效）", () => {
    expect(
      getCellClassName({
        row: { quantity: 0, price: 10, is_duplicate: true },
        column: { property: "quantity" }
      })
    ).toBe("");
  });

  it.each([null, undefined, "", "abc", NaN])(
    "amount=%p 的金额列 → cell-missing",
    amount => {
      expect(
        getCellClassName({
          row: { amount, quantity: 1, price: 10 },
          column: { property: "amount" }
        })
      ).toBe("cell-missing");
    }
  );

  it("缺金额行永不返回 cell-fee（isMissingAmount 分支优先）", () => {
    const cls = getCellClassName({
      row: {
        amount: null,
        quantity: 100,
        price: 10,
        fee: 5,
        op_type: "buy",
        type: "stock"
      },
      column: { property: "amount" }
    });
    expect(cls).toBe("cell-missing");
    expect(cls).not.toBe("cell-fee");
  });

  it("差额被手续费解释的金额列 → cell-fee", () => {
    expect(
      getCellClassName({
        row: {
          quantity: 1,
          price: 10,
          amount: 9,
          fee: 1,
          op_type: "buy",
          type: "stock"
        },
        column: { property: "amount" }
      })
    ).toBe("cell-fee");
  });

  it("带费被解释（quantity 100 / price 10 / amount 995 / fee 5）→ cell-fee", () => {
    expect(
      getCellClassName({
        row: {
          quantity: 100,
          price: 10,
          amount: 995,
          fee: 5,
          op_type: "buy",
          type: "stock"
        },
        column: { property: "amount" }
      })
    ).toBe("cell-fee");
  });

  it("正常行的金额列 → 空串", () => {
    expect(
      getCellClassName({
        row: { quantity: 1, price: 10, amount: 10, fee: 0 },
        column: { property: "amount" }
      })
    ).toBe("");
  });

  it.each(["symbol", "name"])("无关列 %s → 空串", property => {
    expect(
      getCellClassName({
        row: { quantity: 1, price: 10, amount: 10 },
        column: { property }
      })
    ).toBe("");
  });

  const duplicateErrorCases: Array<[string, Record<string, unknown>]> = [
    ["duplicate", { quantity: 0, price: 10, is_duplicate: true }],
    ["error", { quantity: 0, price: 10, error: "解析失败" }]
  ];

  it.each(duplicateErrorCases)("%s + quantity 列 → 空串", (_label, row) => {
    expect(getCellClassName({ row, column: { property: "quantity" } })).toBe(
      ""
    );
  });
});

describe("getCategoryDesc", () => {
  it.each([
    ["error", "解析错误，无法在面板内修正"],
    ["missingCode", "系统无法识别以下证券代码"],
    ["missingQtyPrice", "数量或价格缺失"],
    ["mismatch", "金额与数量×价格不符，且差额超过手续费"]
  ])("%s → %s", (key, expected) => {
    expect(getCategoryDesc(key)).toBe(expected);
  });

  it.each([
    ["unknown", ""],
    ["reverse_repo", ""],
    ["", ""],
    ["ERROR", ""]
  ])("未知 key %s → 空串", (key, expected) => {
    expect(getCategoryDesc(key)).toBe(expected);
  });
});

describe("getCategoryTagType", () => {
  it.each([
    ["error", "danger"],
    ["missingQtyPrice", "danger"],
    ["missingCode", "warning"],
    ["mismatch", "warning"],
    ["reverse_repo", "info"],
    ["unknown", "info"]
  ])("%s → %s", (key, expected) => {
    expect(getCategoryTagType(key)).toBe(expected);
  });

  it("已知 key 永不返回 success", () => {
    for (const key of [
      "error",
      "missingCode",
      "missingQtyPrice",
      "mismatch",
      "reverse_repo"
    ]) {
      expect(getCategoryTagType(key)).not.toBe("success");
    }
  });
});
