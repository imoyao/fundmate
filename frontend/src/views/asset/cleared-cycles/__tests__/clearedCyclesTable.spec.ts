// src/views/asset/cleared-cycles/__tests__/clearedCyclesTable.spec.ts
/**
 * 清仓周期表「客户端排序 + 分页」单测（2026-11-27）。
 *
 * 三条铁律各有用例：缺值恒末尾（升降序都不许把 `--` 顶到第一行）、稳定排序
 * （同值不来回跳）、数值按数值比（102.5 不能排在 99.9 前面）。
 * 分页另测「切范围后页码越界」——夹回才不至于给用户一张空表。
 */
import { describe, expect, it } from "vitest";
import { DEFAULT_PAGE_SIZE, paginate, sortCycles } from "../clearedCyclesTable";
import type { ClearedCycle } from "@/api/summary";

const cycle = (over: Partial<ClearedCycle> = {}): ClearedCycle => ({
  symbol: "000001",
  name: "华夏成长",
  cycle_number: 1,
  first_buy_date: "2026-01-01",
  last_sell_date: "2026-02-01",
  buy_count: 1,
  sell_count: 1,
  trade_count: 2,
  total_buy_amount: 1000,
  total_sell_amount: 1050,
  realized_pnl: 50,
  pnl_pct: 5,
  avg_holding_days: 31,
  dividend_total: null,
  ledger_names: ["账户A"],
  pnl_known: true,
  caveats: [],
  ...over
});

const names = (rows: ClearedCycle[]) => rows.map(r => r.name);

describe("sortCycles", () => {
  it("缺值恒末尾：升序与降序都把 -- 留在最后", () => {
    const rows = [
      cycle({ name: "A", pnl_pct: null }),
      cycle({ name: "B", pnl_pct: 5 }),
      cycle({ name: "C", pnl_pct: -3 })
    ];
    expect(names(sortCycles(rows, "pnl_pct", "asc"))).toEqual(["C", "B", "A"]);
    expect(names(sortCycles(rows, "pnl_pct", "desc"))).toEqual(["B", "C", "A"]);
  });

  it("数值按数值比，不按字符串比（102.5 > 99.9）", () => {
    const rows = [
      cycle({ name: "小", realized_pnl: 99.9 }),
      cycle({ name: "大", realized_pnl: 102.5 })
    ];
    expect(names(sortCycles(rows, "realized_pnl", "desc"))).toEqual([
      "大",
      "小"
    ]);
  });

  it("稳定排序：同值时保持原始顺序", () => {
    const rows = [
      cycle({ name: "第一", realized_pnl: 50 }),
      cycle({ name: "第二", realized_pnl: 50 }),
      cycle({ name: "第三", realized_pnl: 50 })
    ];
    expect(names(sortCycles(rows, "realized_pnl", "desc"))).toEqual([
      "第一",
      "第二",
      "第三"
    ]);
  });

  it("账户按首个名字排序：多账户只比第一个，空账户落末尾", () => {
    // 用 ASCII 名字：与运行环境的 ICU 中文排序规则无关，断言只验证「取首个」
    const rows = [
      cycle({ name: "无账户", ledger_names: [] }),
      cycle({ name: "B", ledger_names: ["B-account"] }),
      cycle({ name: "A", ledger_names: ["A-account", "C-account"] })
    ];
    expect(names(sortCycles(rows, "ledger_names", "asc"))).toEqual([
      "A",
      "B",
      "无账户"
    ]);
  });

  it("日期按字符串序即可（ISO 日期），空日期同样落末尾", () => {
    const rows = [
      cycle({ name: "早", last_sell_date: "2026-01-05" }),
      cycle({ name: "空", last_sell_date: null }),
      cycle({ name: "晚", last_sell_date: "2026-09-30" })
    ];
    expect(names(sortCycles(rows, "last_sell_date", "asc"))).toEqual([
      "早",
      "晚",
      "空"
    ]);
  });

  it("不改入参（返回新数组）", () => {
    const rows = [cycle({ name: "A" }), cycle({ name: "B" })];
    const sorted = sortCycles(rows, "name", "asc");
    expect(sorted).not.toBe(rows);
    expect(names(rows)).toEqual(["A", "B"]);
  });
});

describe("paginate", () => {
  const rows = Array.from({ length: 45 }, (_, i) => cycle({ name: `第${i}` }));

  it("默认每页 20 条，共 3 页", () => {
    const p = paginate(rows, 1, DEFAULT_PAGE_SIZE);
    expect(p.total).toBe(45);
    expect(p.pages).toBe(3);
    expect(p.rows).toHaveLength(20);
  });

  it("页码越界夹回有效区间（切范围后停在旧页不留空表）", () => {
    const p = paginate(rows, 9, 20);
    expect(p.current).toBe(3);
    expect(p.rows).toHaveLength(5);
  });

  it("末页返回剩余行；空数据恒为第 1 页 0 行", () => {
    expect(paginate(rows, 3, 20).rows).toHaveLength(5);
    const empty = paginate<ClearedCycle>([], 4, 20);
    expect(empty.pages).toBe(1);
    expect(empty.current).toBe(1);
    expect(empty.rows).toHaveLength(0);
  });
});
