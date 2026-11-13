/**
 * 「挂错标的」合并进口域 F 快照的回归网（2026-11-13）。
 *
 * 钉住一件容易被读成「小事」的事：合并 groups **必须同时把计数加上**。
 * 否则界面列出了这几笔、分诊卡条数里却没有它们 —— 正是本卡要消灭的
 * 「数据不可见却宣称清理干净」的另一种形态。
 */
import { describe, expect, it } from "vitest";

import type {
  DanglingRefGroup,
  DanglingRefList,
  MislinkedRefList
} from "@/api/reconciliation";
import { mergeDanglingLists } from "../danglingRefMerge";

function group(over: Partial<DanglingRefGroup> = {}): DanglingRefGroup {
  return {
    key: "20|001982",
    ledger_id: 20,
    symbol: "001982",
    txn_count: 7,
    dangling_position_ids: [25],
    net_units: 71.68,
    live_position: null,
    candidates: [],
    batch_id: 1,
    batch_label: "2026-06-07 18:33",
    flags: [],
    fixable: true,
    block_reason: null,
    transactions: [],
    ...over
  };
}

const dangling: DanglingRefList = {
  total: 7,
  group_count: 1,
  batch_count: 1,
  null_symbol: 2,
  null_trade_date: 3,
  fixable_count: 7,
  groups: [group()],
  batches: [
    {
      id: 1,
      label: "2026-06-07 18:33",
      txn_count: 7,
      ledger_ids: [20],
      symbol_count: 1
    }
  ]
};

const mislinked: MislinkedRefList = {
  total: 2,
  group_count: 2,
  fixable_count: 1,
  groups: [
    group({
      key: "mislink|12|SZ127041",
      symbol: "SZ127041",
      txn_count: 1,
      batch_id: null,
      batch_label: "",
      mislinked: true,
      fix_mode: "rebuild",
      wrong_positions: []
    }),
    group({
      key: "mislink|12|SH601058",
      symbol: "SH601058",
      txn_count: 1,
      fixable: false,
      batch_id: null,
      batch_label: "",
      mislinked: true,
      fix_mode: "rebuild",
      wrong_positions: []
    })
  ]
};

describe("mergeDanglingLists", () => {
  it("把错挂组并进 groups，并按条数/组数/可修条数同步加计数", () => {
    const merged = mergeDanglingLists(dangling, mislinked)!;

    expect(merged.groups).toHaveLength(3);
    expect(merged.total).toBe(9);
    expect(merged.group_count).toBe(3);
    // 只有 fixable 的那一组算进「可直接处理」，blocked 组不冒充可修
    expect(merged.fixable_count).toBe(8);
  });

  it("悬空口径的计数与批次不被错挂组污染", () => {
    const merged = mergeDanglingLists(dangling, mislinked)!;

    expect(merged.null_symbol).toBe(dangling.null_symbol);
    expect(merged.null_trade_date).toBe(dangling.null_trade_date);
    expect(merged.batch_count).toBe(dangling.batch_count);
    expect(merged.batches).toEqual(dangling.batches);
  });

  it("没有错挂组 → 原样返回（不新建对象，避免无意义重渲染）", () => {
    expect(mergeDanglingLists(dangling, null)).toBe(dangling);
    expect(
      mergeDanglingLists(dangling, {
        total: 0,
        group_count: 0,
        fixable_count: 0,
        groups: []
      })
    ).toBe(dangling);
  });

  it("悬空接口没数据 → 返回 null（不凭错挂数据伪造一份悬空快照）", () => {
    expect(mergeDanglingLists(null, mislinked)).toBeNull();
    expect(mergeDanglingLists(undefined, undefined)).toBeNull();
  });
});
