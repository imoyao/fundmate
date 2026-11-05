import { describe, expect, it } from "vitest";
import {
  applyRowFilters,
  bucketFixSections,
  countBlockedRows,
  countByCategory,
  countCompleteTransfers,
  countHiddenSelectedDuplicates,
  countPendingFix,
  countSelectedTransfers,
  groupAllocationByType,
  mergeLinkGroups,
  pickAutoFillableRows,
  pickFilledRows,
  pickReverseRepoRows,
  sectionCountsOf,
  shouldShowPriceUpdateTip,
  summarizeErrors
} from "../previewPipeline";

/**
 * 预览行管线纯计算核（#2876 增量 4a）的黄金用例。
 *
 * 与增量 2/3 的 spec 同一条纪律：**直接喂行对象给纯模块**，不 import
 * `useImportWizard`、不 `vi.mock` 任何东西。这样断言失败时定位到的就是管线本身，
 * 而不是「组件外壳 + 响应式包装 + 一堆 mock」里的某一层。
 *
 * 下面每条断言都取自当前实现的行为；写测试时**没有**为了让断言变绿而改动
 * `previewPipeline.ts` 的任何一行（做法：先写断言 → 跑红 → 再改实现在别处验证，
 * 见交付报告里的「故意改错」记录）。
 */

let seq = 0;
/** 补一个唯一 `_rowKey`：合并行的父 key 由它派生（`merged_<父行>`） */
function keyed<T extends Record<string, any>>(row: T): T & { _rowKey: string } {
  seq += 1;
  return { _rowKey: `row_${seq}`, ...row } as T & { _rowKey: string };
}

/** 健康行：数量单价金额自洽，无代码/金额问题 */
function baseRow(overrides: Record<string, any> = {}) {
  return keyed({
    symbol: "002311",
    name: "海大集团",
    op_type: "buy",
    trade_date: "2026-10-28",
    quantity: 100,
    price: 10,
    amount: 1000,
    fee: 0,
    type: "stock",
    ...overrides
  });
}

/** 债券兑息行（丰山转债真实值：60 张、单价 1.5、利息 90 元） */
function interestRow(overrides: Record<string, any> = {}) {
  return keyed({
    symbol: "SH113649",
    name: "丰山转债",
    op_type: "dividend_cash",
    trade_date: "2026-06-26",
    quantity: 60,
    price: 1.5,
    amount: 90,
    fee: 0,
    type: "bond",
    link_group_id: "bond_interest_tax:SH113649:2026-06-26",
    ...overrides
  });
}

/** 代扣个税行：沿用利息行的数量单价，金额 −18 */
function taxRow(overrides: Record<string, any> = {}) {
  return keyed({
    symbol: "SH113649",
    name: "丰山转债",
    op_type: "tax",
    trade_date: "2026-06-26",
    quantity: 60,
    price: 1.5,
    amount: -18,
    fee: 0,
    type: "bond",
    link_group_id: "bond_interest_tax:SH113649:2026-06-26",
    ...overrides
  });
}

describe("mergeLinkGroups：息 + 税折成一条净额行", () => {
  it("健康的一组折成 1 行，父 key 派生自利息行，净额 = 利息 + 税", () => {
    const interest = interestRow();
    const rows = mergeLinkGroups([interest, taxRow()]);

    expect(rows).toHaveLength(1);
    const merged = rows[0]!;
    expect(merged._rowKey).toBe(`merged_${interest._rowKey}`);
    expect(merged.net_amount).toBe(72); // 90 + (−18)
    expect(merged.amount).toBe(72);
    expect(merged.children).toHaveLength(2);
    expect(merged.children!.map((c: any) => c.op_type)).toEqual([
      "dividend_cash",
      "tax"
    ]);
    expect(merged.op_type_label).toBe("利息收入");
    expect(merged.is_merged).toBe(true);
  });

  it("notes 写明税前 / 扣税 / 实收，且都是两位小数", () => {
    const merged = mergeLinkGroups([interestRow(), taxRow()])[0]!;

    expect(merged.notes).toContain("税前90.00元");
    expect(merged.notes).toContain("扣税18.00元");
    expect(merged.notes).toContain("实收72.00元");
  });

  it("组内任一行有修正问题就不合并，两行原样保留且顺序不变", () => {
    const interest = interestRow({ error: "交易日期无法解析" });
    const tax = taxRow();
    const rows = mergeLinkGroups([interest, tax]);

    expect(rows).toHaveLength(2);
    expect(rows.some(r => r.is_merged)).toBe(false);
    expect(rows[0]).toBe(interest);
    expect(rows[1]).toBe(tax);
  });

  it("没有 link_group_id 的行直通（引用不变，不做拷贝）", () => {
    const plain = baseRow({ link_group_id: null });
    const rows = mergeLinkGroups([plain]);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toBe(plain);
  });

  it("同组只处理一次：组不为 2 行时既不合并也不重复 push", () => {
    const group = "bond_interest_tax:SH113649:2026-06-26";
    const rows = mergeLinkGroups([
      interestRow({ link_group_id: group }),
      taxRow({ link_group_id: group }),
      interestRow({ link_group_id: group })
    ]);

    // 3 行同组 → groupRows.length !== 2 → 不合并；每行恰好出现一次
    expect(rows).toHaveLength(3);
    expect(rows.every(r => !r.is_merged)).toBe(true);
  });
});

describe("countByCategory：按显示单元计数", () => {
  it("先合并再分类：一组息 + 税只算 complete 1 条（不是 2 条）", () => {
    const counts = countByCategory([interestRow(), taxRow()]);

    expect(counts).toEqual({ complete: 1, duplicate: 0, fix: 0 });
  });

  it("三个键恒存在（空输入也不缺键，概览条直接取用）", () => {
    expect(Object.keys(countByCategory([])).sort()).toEqual([
      "complete",
      "duplicate",
      "fix"
    ]);
  });
});

describe("bucketFixSections / sectionCountsOf：四分区互斥完备", () => {
  const errorRow = () => baseRow({ error: "交易日期无法解析" });
  const missingCodeRow = () => baseRow({ symbol: "" });
  const missingQtyPriceRow = () =>
    baseRow({ quantity: 0, price: 0, amount: 0 });
  const mismatchRow = () =>
    baseRow({ quantity: 100, price: 10, amount: 995, fee: 0 });

  it("四桶互斥，并集恰好是全部 fix 行；duplicate / 转账行不入任何桶", () => {
    const fixRows = [
      errorRow(),
      missingCodeRow(),
      missingQtyPriceRow(),
      mismatchRow()
    ];
    const excluded = [
      baseRow({ is_duplicate: true, error: "重复且解析错" }),
      baseRow({ is_cash_transfer: true, error: "转账失败" })
    ];
    const buckets = bucketFixSections([...fixRows, ...excluded]);
    const all = [
      ...buckets.error,
      ...buckets.missingCode,
      ...buckets.missingQtyPrice,
      ...buckets.mismatch
    ];

    expect(all).toHaveLength(4);
    expect(new Set(all.map(r => r._rowKey)).size).toBe(4);
    expect(new Set(all.map(r => r._rowKey))).toEqual(
      new Set(fixRows.map(r => r._rowKey))
    );
    // 每行只落一个桶
    expect(buckets.error).toHaveLength(1);
    expect(buckets.missingCode).toHaveLength(1);
    expect(buckets.missingQtyPrice).toHaveLength(1);
    expect(buckets.mismatch).toHaveLength(1);
  });

  it("四桶之和恒等于 countByCategory 的 fix 条数", () => {
    const rows = [
      errorRow(),
      missingCodeRow(),
      missingQtyPriceRow(),
      mismatchRow(),
      baseRow(),
      baseRow({ is_duplicate: true }),
      baseRow({ is_cash_transfer: true })
    ];
    const counts = sectionCountsOf(bucketFixSections(rows));
    const sum =
      counts.error +
      counts.missingCode +
      counts.missingQtyPrice +
      counts.mismatch;

    expect(sum).toBe(4);
    expect(sum).toBe(countByCategory(rows).fix);
  });
});

describe("countPendingFix：「暂不导入」的判据是默认不选，不是不能勾", () => {
  it("疑似重复行计入（#2836：它默认不选但用户可手动勾），转账与已忽略行不计入", () => {
    const rows = [
      baseRow(), // 默认可选 → 不计
      baseRow({ is_duplicate: true }), // 默认不选、但允许勾 → 计
      baseRow({ error: "解析失败" }), // 计
      baseRow({ is_cash_transfer: true, quantity: 0, price: 0 }), // 转账不计
      baseRow({ _ignored: true }) // 用户主动忽略不计
    ];

    expect(countPendingFix(rows)).toBe(2);
  });
});

describe("countHiddenSelectedDuplicates：显隐与勾选分离（#2274）", () => {
  it("duplicatesHandled 为 false 时恒为 0（重复行还显示着，谈不上「已隐藏」）", () => {
    const rows = [baseRow({ is_duplicate: true, _duplicateHandled: true })];
    const selected = new Set([rows[0]!._rowKey]);

    expect(countHiddenSelectedDuplicates(rows, selected, false)).toBe(0);
  });

  it("重复行被隐藏且仍被勾选时计入；非重复行与未勾选行不计", () => {
    const dup = baseRow({ is_duplicate: true, _duplicateHandled: true });
    const notHandled = baseRow({ is_duplicate: true });
    const plain = baseRow();
    const rows = [dup, notHandled, plain];
    const selected = new Set([dup._rowKey, notHandled._rowKey, plain._rowKey]);

    expect(countHiddenSelectedDuplicates(rows, selected, true)).toBe(1);
  });
});

describe("shouldShowPriceUpdateTip：选中的持仓行才会用到净值", () => {
  it("importedCount 为 0 时恒 false（没有导入就没有净值回填）", () => {
    const stock = baseRow({ type: "stock" });
    expect(shouldShowPriceUpdateTip([stock], new Set([stock._rowKey]), 0)).toBe(
      false
    );
  });

  it("未勾选的行不参与；勾选的持仓类型才触发", () => {
    const stock = baseRow({ type: "stock" });
    const cash = baseRow({ type: "cash" });

    expect(shouldShowPriceUpdateTip([stock], new Set(), 3)).toBe(false);
    expect(
      shouldShowPriceUpdateTip([stock, cash], new Set([cash._rowKey]), 3)
    ).toBe(false);
    expect(
      shouldShowPriceUpdateTip([stock, cash], new Set([stock._rowKey]), 3)
    ).toBe(true);
  });
});

describe("groupAllocationByType：分配方式分组", () => {
  it("排除手动改过的大类、重复行、错误行、转账行与被拦截行；同类型按首行取值", () => {
    const rows = [
      baseRow({ type: "stock", allocation: "shortterm" }),
      baseRow({ type: "stock", allocation: "longterm" }), // 同组，不覆盖首行
      baseRow({ type: "bond", allocation: "" }), // 空 → longterm
      baseRow({
        type: "fund",
        allocation: "shortterm",
        _allocationManual: true
      }),
      baseRow({ type: "fund", is_duplicate: true, allocation: "shortterm" }),
      baseRow({ type: "fund", error: "解析失败", allocation: "shortterm" })
    ];
    const groups = groupAllocationByType(rows);

    expect(groups).toEqual([
      {
        type: "stock",
        label: "股票",
        count: 2,
        currentAllocation: "shortterm"
      },
      { type: "bond", label: "可转债", count: 1, currentAllocation: "longterm" }
    ]);
  });

  it("数量/价格缺失的待补全行不参与分配（否则会导出一个用户没确认过的比例）", () => {
    const groups = groupAllocationByType([
      baseRow({ quantity: 0, price: 0, amount: 0, allocation: "shortterm" })
    ]);

    expect(groups).toEqual([]);
  });
});

describe("summarizeErrors：解析错误按原因汇总", () => {
  it("同一原因归一组，名称缺失回退 symbol，再缺回退 --", () => {
    const groups = summarizeErrors([
      { error: "金额无法解析", name: "海大集团" },
      { error: "金额无法解析", symbol: "002311" },
      { error: null, name: "无代码行" }
    ]);

    expect(groups).toEqual([
      { reason: "金额无法解析", count: 2, items: ["海大集团", "002311"] },
      { reason: "未知错误", count: 1, items: ["无代码行"] }
    ]);
  });
});

describe("pick* 三件套", () => {
  it("pickReverseRepoRows 只挑 type === reverse_repo 的行", () => {
    const repo = baseRow({ type: "reverse_repo" });
    const rows = pickReverseRepoRows([repo, baseRow({ type: "stock" })]);

    expect(rows).toEqual([repo]);
  });

  it("pickAutoFillableRows 只收「只缺数量或只缺价格、且金额在」的行", () => {
    const onlyQtyMissing = baseRow({ quantity: 0, price: 10, amount: 1000 });
    const onlyPriceMissing = baseRow({ quantity: 100, price: 0, amount: 1000 });
    const bothMissing = baseRow({ quantity: 0, price: 0, amount: 1000 });
    const noAmount = baseRow({ quantity: 0, price: 10, amount: 0 });
    const rows = pickAutoFillableRows(
      bucketFixSections([
        onlyQtyMissing,
        onlyPriceMissing,
        bothMissing,
        noAmount
      ]).missingQtyPrice
    );

    expect(rows).toEqual([onlyQtyMissing, onlyPriceMissing]);
  });

  it("入参就是 missingQtyPrice 桶：结果是被推算式挑中的子集，桶内其余行原样保留", () => {
    const all = [
      baseRow({ quantity: 0, price: 10, amount: 1000 }), // 可推算
      baseRow({ quantity: 0, price: 0, amount: 1000 }), // 桶内但两个都缺
      baseRow({ symbol: "" }), // 别的分区（missingCode）
      baseRow({ error: "解析失败" }) // 别的分区（error）
    ];
    const bucket = bucketFixSections(all).missingQtyPrice;
    const picked = pickAutoFillableRows(bucket);

    // 行数关系：子集，且严格小于桶（桶里还躺着「两个都缺」的那条）
    expect(bucket).toHaveLength(2);
    expect(picked).toHaveLength(1);
    expect(bucket.length).toBeGreaterThan(picked.length);
    expect(new Set(bucket.map(r => r._rowKey))).toEqual(
      new Set(all.slice(0, 2).map(r => r._rowKey))
    );
  });

  it("pickFilledRows 只收 _autoFilled 非空的行", () => {
    const filled = baseRow({ _autoFilled: ["price"] });
    const rows = pickFilledRows([
      filled,
      baseRow(),
      baseRow({ _autoFilled: [] })
    ]);

    expect(rows).toEqual([filled]);
  });
});

describe("countBlockedRows / countSelectedTransfers / countCompleteTransfers", () => {
  it("待补全行只数「非重复、非错误、非转账」的那批", () => {
    const rows = [
      baseRow({ quantity: 0, price: 0, amount: 0 }), // 计
      baseRow({ quantity: 0, price: 0, amount: 0, is_duplicate: true }),
      baseRow({ quantity: 0, price: 0, amount: 0, error: "解析失败" }),
      baseRow({ quantity: 0, price: 0, amount: 0, is_cash_transfer: true })
    ];

    expect(countBlockedRows(rows)).toBe(1);
  });

  it("已选行里的转账条数只数转账，且必须已被勾选", () => {
    const picked = baseRow({ is_cash_transfer: true });
    const notPicked = baseRow({ is_cash_transfer: true });
    const stock = baseRow();
    const rows = [picked, notPicked, stock];

    expect(
      countSelectedTransfers(rows, new Set([picked._rowKey, stock._rowKey]))
    ).toBe(1);
  });

  it("转账行数量按 categorizeRow 口径取子集（重复的转账不计入完整）", () => {
    const rows = [
      baseRow({ is_cash_transfer: true }),
      baseRow({ is_cash_transfer: true, is_duplicate: true }),
      baseRow()
    ];

    expect(countCompleteTransfers(rows)).toBe(1);
  });
});

describe("applyRowFilters：五键过滤管线（#2876 增量 4b）", () => {
  /** 全空过滤器 = 「无任何过滤键命中」，调参方便 */
  const NO_FILTER = {
    tableStatusFilter: "",
    activeCategoryFilter: "",
    showProblemOnly: false,
    tableFilterKeyword: "",
    tableTypeFilter: []
  };
  const f = (over: Partial<typeof NO_FILTER> = {}) => ({
    ...NO_FILTER,
    ...over
  });

  /** 待补全行（isRowBlocked 命中：qty=0 且不在豁免清单） */
  const blockedRow = (over: Record<string, any> = {}) =>
    baseRow({ quantity: 0, price: 0, amount: 0, ...over });
  /** 金额对不上的行：|100×10 − 500| = 500，fee=0 解释不掉 → mismatch */
  const mismatchRow = (over: Record<string, any> = {}) =>
    baseRow({ amount: 500, ...over });
  /** 代码未匹配的行 */
  const noCodeRow = (over: Record<string, any> = {}) =>
    baseRow({ symbol: "", ...over });
  const healthyRow = (over: Record<string, any> = {}) => baseRow(over);

  it("status=blocked：只留「待补全且不是重复/错误/转账」的行", () => {
    const rows = [
      blockedRow(),
      blockedRow({ is_duplicate: true }),
      blockedRow({ error: "解析失败" }),
      blockedRow({ is_cash_transfer: true }),
      healthyRow()
    ];
    const out = applyRowFilters(rows, f({ tableStatusFilter: "blocked" }));
    expect(out.map(r => r._rowKey)).toEqual([rows[0]._rowKey]);
  });

  it("status=complete/duplicate/fix：三卡状态键与 categorizeRow 同谓词", () => {
    const rows = [healthyRow(), baseRow({ is_duplicate: true }), noCodeRow()];
    const pick = (status: string) =>
      applyRowFilters(rows, f({ tableStatusFilter: status })).length;

    expect(pick("complete")).toBe(1);
    expect(pick("duplicate")).toBe(1);
    expect(pick("fix")).toBe(1);
  });

  it("status=空串：不做状态过滤（死键 normal/problem 已随胶囊移除）", () => {
    const rows = [healthyRow(), blockedRow()];
    expect(applyRowFilters(rows, f()).length).toBe(2);
    // 未知的旧键也不该命中任何分支（不会误伤成全空）
    expect(
      applyRowFilters(rows, f({ tableStatusFilter: "normal" })).length
    ).toBe(2);
  });

  it("activeCategoryFilter=missingCode：缺代码且不沾重复/错误/转账；cash 类天然放行", () => {
    const rows = [
      noCodeRow(),
      noCodeRow({ is_duplicate: true }),
      noCodeRow({ error: "解析失败" }),
      noCodeRow({ is_cash_transfer: true }),
      baseRow({ type: "cash", symbol: "" }), // 现金类不写 symbol 是常态，不是缺代码
      healthyRow()
    ];
    const out = applyRowFilters(
      rows,
      f({ activeCategoryFilter: "missingCode" })
    );
    expect(out.map(r => r._rowKey)).toEqual([rows[0]._rowKey]);
  });

  it("activeCategoryFilter=mismatch：金额差超出手续费解释范围的行", () => {
    const rows = [
      mismatchRow(),
      healthyRow(), // 差额 0，不命中
      baseRow({ amount: 1050, fee: 50 }), // 差 50 被 fee 解释 → 不命中
      mismatchRow({ is_duplicate: true }),
      mismatchRow({ error: "解析失败" }),
      mismatchRow({ is_cash_transfer: true })
    ];
    const out = applyRowFilters(rows, f({ activeCategoryFilter: "mismatch" }));
    expect(out.map(r => r._rowKey)).toEqual([rows[0]._rowKey]);
  });

  it("activeCategoryFilter=error：有解析错误且不沾重复/转账", () => {
    const rows = [
      baseRow({ error: "解析失败" }),
      baseRow({ error: "解析失败", is_duplicate: true }),
      baseRow({ error: "解析失败", is_cash_transfer: true }),
      healthyRow()
    ];
    const out = applyRowFilters(rows, f({ activeCategoryFilter: "error" }));
    expect(out.map(r => r._rowKey)).toEqual([rows[0]._rowKey]);
  });

  it("showProblemOnly：fix 全留、未处理重复留、已处理重复丢、编辑中行留下（#2836 教训）", () => {
    const rows = [
      noCodeRow(), // fix（missingCode）
      mismatchRow(), // fix（mismatch）
      blockedRow(), // fix（缺数量价格）
      baseRow({ error: "解析失败" }), // fix（error）
      baseRow({ is_duplicate: true }), // 未处理重复 → 留
      baseRow({ is_duplicate: true, _duplicateHandled: true }), // 已处理 → 丢
      healthyRow({ isEditingQty: true }), // 编辑中，即使数据已好也留原地
      healthyRow() // 干净且不在编辑 → 丢
    ];
    const out = applyRowFilters(rows, f({ showProblemOnly: true }));
    expect(out.map(r => r._rowKey)).toEqual([
      rows[0]._rowKey,
      rows[1]._rowKey,
      rows[2]._rowKey,
      rows[3]._rowKey,
      rows[4]._rowKey,
      rows[6]._rowKey
    ]);
  });

  it("showProblemOnly 的 fix 判据走 categorizeRow，不再手写「缺字段||错误||重复」副本", () => {
    // #2836 的原始事故：手写副本漏掉「代码未匹配」——这里钉住它必须被留下
    const rows = [noCodeRow(), healthyRow()];
    const out = applyRowFilters(rows, f({ showProblemOnly: true }));
    expect(out.map(r => r._rowKey)).toEqual([rows[0]._rowKey]);
  });

  it("关键词：symbol 或 name 不分大小写命中", () => {
    const rows = [
      healthyRow(), // 002311 / 海大集团
      baseRow({ symbol: "600000", name: "浦发银行" }),
      baseRow({ symbol: "", name: "HEIN集团" })
    ];
    const out = applyRowFilters(rows, f({ tableFilterKeyword: "600000" }));
    expect(out.map(r => r._rowKey)).toEqual([rows[1]._rowKey]);

    const byName = applyRowFilters(rows, f({ tableFilterKeyword: "hein" }));
    expect(byName.map(r => r._rowKey)).toEqual([rows[2]._rowKey]);
  });

  it("类型过滤：type 在清单内才留；空数组不过滤", () => {
    const rows = [
      healthyRow(), // stock
      baseRow({ type: "fund" })
    ];
    const out = applyRowFilters(rows, f({ tableTypeFilter: ["stock"] }));
    expect(out.map(r => r._rowKey)).toEqual([rows[0]._rowKey]);

    expect(applyRowFilters(rows, f({ tableTypeFilter: [] })).length).toBe(2);
  });

  it("多键叠加：status=fix + showProblemOnly + 关键词逐层收缩", () => {
    const rows = [
      noCodeRow({ name: "海大A" }), // fix + 命中关键词
      noCodeRow({ name: "别的B" }), // fix 但关键词不命中
      healthyRow({ name: "海大C" }) // 关键词命中但不是 fix
    ];
    const out = applyRowFilters(
      rows,
      f({
        tableStatusFilter: "fix",
        showProblemOnly: true,
        tableFilterKeyword: "海大"
      })
    );
    expect(out.map(r => r._rowKey)).toEqual([rows[0]._rowKey]);
  });

  it("无过滤键命中时返回入参同一引用（历史行为，不补 slice）", () => {
    const rows = [healthyRow()];
    expect(applyRowFilters(rows, f())).toBe(rows);
  });
});
