import { describe, expect, it } from "vitest";
import type {
  DanglingRefGroup,
  DanglingRefList,
  DiscrepancyItem
} from "@/api/reconciliation";
import {
  discrepancyKey,
  isRebuildOnlyDiscrepancy,
  rebuildCoveredKeys,
  withoutRebuildOnly
} from "../rebuildOnly";

function group(over: Partial<DanglingRefGroup> = {}): DanglingRefGroup {
  return {
    key: "12|SZ159767",
    ledger_id: 12,
    symbol: "SZ159767",
    txn_count: 5,
    dangling_position_ids: [808],
    net_units: 12000,
    live_position: null,
    candidates: [],
    batch_id: null,
    batch_label: "",
    flags: [],
    fixable: true,
    block_reason: null,
    transactions: [],
    ...over
  };
}

function danglingList(groups: DanglingRefGroup[]): DanglingRefList {
  return {
    total: groups.reduce((sum, g) => sum + g.txn_count, 0),
    group_count: groups.length,
    batch_count: 0,
    null_symbol: 0,
    null_trade_date: 0,
    fixable_count: 0,
    groups,
    batches: []
  };
}

function row(over: Partial<DiscrepancyItem> = {}): DiscrepancyItem {
  return {
    id: 1,
    domain: "B",
    ledger_id: 12,
    symbol: "SZ159767",
    discrepancy_type: "orphan",
    expected_value: 12000,
    actual_value: 0,
    diff: -12000,
    status: "pending",
    is_permanent: false,
    first_detected_at: null,
    updated_at: null,
    ...over
  };
}

describe("rebuildOnly：唯一入口判据", () => {
  it("键与后端分组键同口径：ledger_id|symbol，不归一化代码", () => {
    expect(discrepancyKey({ ledger_id: 12, symbol: "SZ159767" })).toBe(
      "12|SZ159767"
    );
    // 缺标的的悬空组 symbol 为空串，与差异行不会误配
    expect(discrepancyKey({ ledger_id: 12, symbol: "" })).toBe("12|");
    expect(discrepancyKey({ ledger_id: null, symbol: null })).toBe("|");
  });

  it("覆盖集合来自域 F 分组；拿不到输入时是空集合（不抛错）", () => {
    expect(rebuildCoveredKeys(null).size).toBe(0);
    expect(
      rebuildCoveredKeys({
        ...danglingList([]),
        groups: undefined as unknown as DanglingRefGroup[]
      }).size
    ).toBe(0);
    expect([...rebuildCoveredKeys(danglingList([group()]))]).toEqual([
      "12|SZ159767"
    ]);
  });

  it("被覆盖的 orphan 差异判为「只能去修正数据」", () => {
    const covered = rebuildCoveredKeys(danglingList([group()]));
    expect(isRebuildOnlyDiscrepancy(row(), covered)).toBe(true);
  });

  it("域 F 没覆盖的 orphan 保留：持仓行还在、只是份额归零（真库 8 条）", () => {
    const covered = rebuildCoveredKeys(danglingList([group()]));
    expect(isRebuildOnlyDiscrepancy(row({ symbol: "SH600103" }), covered)).toBe(
      false
    );
  });

  it("数量差异即便同键也不剔除：它的修法本来就在核对差异里", () => {
    const covered = rebuildCoveredKeys(danglingList([group()]));
    expect(
      isRebuildOnlyDiscrepancy(
        row({ discrepancy_type: "quantity", actual_value: 100, diff: -11900 }),
        covered
      )
    ).toBe(false);
  });

  it("不同账本同标的不是同一笔：ledger_id 参与判据", () => {
    const covered = rebuildCoveredKeys(danglingList([group()]));
    expect(isRebuildOnlyDiscrepancy(row({ ledger_id: 13 }), covered)).toBe(
      false
    );
  });

  it("withoutRebuildOnly 只摘掉被覆盖的 orphan，其余顺序不变", () => {
    const rows = [
      row({ id: 1, symbol: "SZ159767" }),
      row({ id: 2, symbol: "SH600103" }),
      row({ id: 3, discrepancy_type: "quantity" })
    ];
    const kept = withoutRebuildOnly(rows, danglingList([group()]));
    expect(kept.map(r => r.id)).toEqual([2, 3]);
    // 没有域 F 数据时原样返回（不清空、不重排）
    expect(withoutRebuildOnly(rows, null)).toBe(rows);
  });
});
