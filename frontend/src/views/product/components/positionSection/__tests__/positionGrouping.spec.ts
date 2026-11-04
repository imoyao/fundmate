/**
 * 持仓分组的可判定口径（#980 拆分时从 `ProductPositionSection.vue` 抽出）。
 *
 * 抽成纯函数的理由：分组键、缺省账户名、未归档兜底这三条以前埋在 `<script setup>`
 * 里，只能靠 e2e 间接覆盖，而 e2e 只跑「有账户名」那一条路径——
 * 「ledger_id 为 null」这个最容易出坏链的分支其实没人钉。
 */
import { describe, it, expect } from "vitest";
import { groupByLedger, shortDate } from "../positionGrouping";
import type { Position } from "@/api/types";

/** 只填分组用到的字段，其余给占位 */
const position = (over: Partial<Position>): Position =>
  ({
    id: 1,
    symbol: "SZ002092",
    name: "中泰化学",
    market: "CN_A",
    type: "stock",
    account_name: "同花顺——银河",
    currency: "CNY",
    current_price: 0,
    trade_date: "2026-05-12",
    notes: null,
    created_at: "2026-05-12T00:00:00",
    updated_at: "2026-05-12T00:00:00",
    quantity: 0,
    avg_price: 0,
    ...over
  }) as Position;

describe("groupByLedger：按账户聚合", () => {
  it("同一 ledger_id 的行归一组，组内金额按 sumUp 聚合", () => {
    const groups = groupByLedger([
      position({
        ledger_id: 7,
        quantity: 1000,
        avg_price: 2,
        market_value: 2400,
        pnl: 400
      }),
      position({
        ledger_id: 7,
        quantity: 500,
        avg_price: 4,
        market_value: 1800,
        pnl: -200
      })
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].rows).toHaveLength(2);
    expect(groups[0].quantity).toBe(1500);
    expect(groups[0].cost).toBe(4000);
    expect(groups[0].pnl).toBe(200);
  });

  it("不同账户各成一组，顺序 = ledger_id 首次出现的次序（不重排）", () => {
    const groups = groupByLedger([
      position({ ledger_id: 9, account_name: "账户九" }),
      position({ ledger_id: 3, account_name: "账户三" }),
      position({ ledger_id: 9, account_name: "账户九" })
    ]);

    // 若前端自己排序，用户会看到「账户三」跳到前面，与建仓先后不符
    expect(groups.map(g => g.ledgerId)).toEqual([9, 3]);
    expect(groups.map(g => g.rows.length)).toEqual([2, 1]);
  });

  it("key 由 ledger_id 生成，便于 v-for 稳定复用", () => {
    const groups = groupByLedger([position({ ledger_id: 42 })]);
    expect(groups[0].key).toBe("42");
  });

  it("缺 account_name → 退回「账户 #<id>」，不显示空白行标签", () => {
    const groups = groupByLedger([
      position({ ledger_id: 42, account_name: undefined })
    ]);
    expect(groups[0].name).toBe("账户 #42");
  });

  it("ledger_id 为 null（未归档）→ 单独一组、key=ungrouped、ledgerId 保持 null", () => {
    const groups = groupByLedger([
      position({ ledger_id: null, account_name: "未归档持仓" })
    ]);

    expect(groups[0].key).toBe("ungrouped");
    // ledgerId 必须仍是 null：模板据此**不套跳转**，有值就会链到 /asset/ledgers/null
    expect(groups[0].ledgerId).toBeNull();
    expect(groups[0].name).toBe("未归档持仓");
  });

  it("未归档与已归档同时存在时互不吞并", () => {
    const groups = groupByLedger([
      position({ ledger_id: null, account_name: "未归档持仓" }),
      position({ ledger_id: 5, account_name: "账户五" })
    ]);
    expect(groups).toHaveLength(2);
    expect(groups.map(g => g.ledgerId)).toEqual([null, 5]);
  });
});

describe("shortDate：基准日注脚（#2007）", () => {
  it("10 位 ISO 日期只留 MM-DD，年份是噪声", () => {
    expect(shortDate("2026-10-09")).toBe("10-09");
  });

  it("非 10 位原样返回，不做猜测式截断", () => {
    expect(shortDate("2026-10-09T14:00:00")).toBe("2026-10-09T14:00:00");
    expect(shortDate("")).toBe("");
  });
});
