import { describe, it, expect } from "vitest";
import {
  classifyFixMode,
  snapshotRows,
  restoreRows,
  SINGLE_FIX_THRESHOLD,
  SECTION_BATCHABLE,
  UNDO_STACK_LIMIT,
  UNDO_FIELDS,
  type SectionCounts
} from "../batchFixLogic";

/** 以全零分区为底，只传有值的键 */
const counts = (partial: Partial<SectionCounts>): SectionCounts => ({
  error: 0,
  missingCode: 0,
  missingQtyPrice: 0,
  mismatch: 0,
  ...partial
});

describe("classifyFixMode：#783 §4 阈值形态切换", () => {
  it("无问题行 → none", () => {
    expect(classifyFixMode(counts({}))).toBe("none");
  });

  it("≤10 且混合类型 → single（卡片式逐条修正）", () => {
    // 6 条（1 错误 + 2 未匹配 + 3 不一致）
    const mode = classifyFixMode(
      counts({ error: 1, missingCode: 2, mismatch: 3 })
    );
    expect(mode).toBe("single");
  });

  it("阈值边界：合计恰 10 → single，11 → batch", () => {
    expect(
      classifyFixMode(
        counts({ missingCode: 4, missingQtyPrice: 4, mismatch: 2 })
      )
    ).toBe("single");
    expect(
      classifyFixMode(
        counts({ missingCode: 4, missingQtyPrice: 4, mismatch: 3 })
      )
    ).toBe("batch");
  });

  it(">10 混合且均可批量 → batch（§4 第 2 条）", () => {
    expect(classifyFixMode(counts({ missingCode: 6, mismatch: 7 }))).toBe(
      "batch"
    );
  });

  it("同一可批量分区即使 ≤10 也固定走 batch（§4 第 3 条）", () => {
    expect(classifyFixMode(counts({ missingCode: 5 }))).toBe("batch");
    expect(classifyFixMode(counts({ missingQtyPrice: 1 }))).toBe("batch");
    expect(classifyFixMode(counts({ mismatch: 10 }))).toBe("batch");
  });

  it("混合含解析错误且 ≤10 → single（错误行以卡片承载跳过）", () => {
    expect(classifyFixMode(counts({ error: 2, mismatch: 3 }))).toBe("single");
  });

  it("混合含解析错误且 >10 → batch（错误部分由面板提示条承接 §4 第 4 条）", () => {
    expect(classifyFixMode(counts({ error: 2, missingCode: 10 }))).toBe(
      "batch"
    );
  });

  it("纯解析错误（不可批量）→ table（引导完整表格 + 跳过）", () => {
    expect(classifyFixMode(counts({ error: 3 }))).toBe("table");
    expect(classifyFixMode(counts({ error: 40 }))).toBe("table");
  });

  it("结构约束：error 不可批量、其余三区可批量、阈值 10、栈上限 ≥1", () => {
    expect(SECTION_BATCHABLE.error).toBe(false);
    expect(SECTION_BATCHABLE.missingCode).toBe(true);
    expect(SECTION_BATCHABLE.missingQtyPrice).toBe(true);
    expect(SECTION_BATCHABLE.mismatch).toBe(true);
    expect(SINGLE_FIX_THRESHOLD).toBe(10);
    expect(UNDO_STACK_LIMIT).toBeGreaterThanOrEqual(1);
  });
});

describe("snapshotRows / restoreRows：撤销回滚语义", () => {
  const makeRow = () => ({
    _rowKey: "row-1",
    symbol: "600000",
    name: "浦发银行",
    type: "stock",
    quantity: 100,
    price: 10.5,
    amount: 1050,
    allocation: "liquid",
    is_calculated: false,
    _dataMissing: undefined as string | undefined,
    _autoFilled: undefined as string[] | undefined,
    fee: 5.2 // 不在快照清单内
  });

  it("批量变更后回滚：全部快照字段恢复到变更前", () => {
    const row = makeRow();
    const snapshots = snapshotRows([row]);

    // 模拟批量修正写入
    row.symbol = "UNKNOWN";
    row.quantity = 0;
    row.price = 0;
    row.amount = 999;
    row.allocation = "longterm";
    row.is_calculated = true;
    row._autoFilled = ["quantity", "price"];

    restoreRows([row], snapshots);

    expect(row.symbol).toBe("600000");
    expect(row.name).toBe("浦发银行");
    expect(row.type).toBe("stock");
    expect(row.quantity).toBe(100);
    expect(row.price).toBe(10.5);
    expect(row.amount).toBe(1050);
    expect(row.allocation).toBe("liquid");
    expect(row.is_calculated).toBe(false);
    expect(row._autoFilled).toBeUndefined();
    expect(row._dataMissing).toBeUndefined();
  });

  it("回滚只写快照清单内字段：清单外的后续变更不受影响", () => {
    const row = makeRow();
    const snapshots = snapshotRows([row]);

    row.fee = 88; // fee 不在 UNDO_FIELDS
    restoreRows([row], snapshots);

    expect(row.fee).toBe(88);
    expect(UNDO_FIELDS).not.toContain("fee");
  });

  it("_autoFilled 有值→回滚后清除；无值→快照与恢复保持 undefined", () => {
    const filled = makeRow();
    filled._autoFilled = ["quantity"];
    const snapshots = snapshotRows([filled]);
    filled._autoFilled = ["quantity", "price"];
    restoreRows([filled], snapshots);
    expect(filled._autoFilled).toEqual(["quantity"]);

    const clean = makeRow();
    const cleanSnap = snapshotRows([clean]);
    clean._autoFilled = ["price"];
    restoreRows([clean], cleanSnap);
    expect(clean._autoFilled).toBeUndefined();
  });

  it("目标行已被移除时安全跳过，不抛错", () => {
    const kept = makeRow();
    const gone = { ...makeRow(), _rowKey: "row-2" };
    const snapshots = snapshotRows([kept, gone]);

    expect(() => restoreRows([kept], snapshots)).not.toThrow();
    expect(kept.symbol).toBe("600000");
  });

  it("多行快照：互不串扰地恢复各自的值", () => {
    const a = { ...makeRow(), _rowKey: "a", symbol: "600000" };
    const b = { ...makeRow(), _rowKey: "b", symbol: "000001" };
    const snapshots = snapshotRows([a, b]);

    a.symbol = "111111";
    b.symbol = "222222";
    restoreRows([a, b], snapshots);

    expect(a.symbol).toBe("600000");
    expect(b.symbol).toBe("000001");
  });
});
