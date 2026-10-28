/**
 * 交易流水表的行口径（#2712）：日期展示、客户端排序键、类型着色。
 *
 * 这三条此前散在组件里且**四端各写一份**（日期一处只认 trade_date、一处只认
 * confirm_date），所以单测直接钉住「交易日优先、确认日兜底」与「排序键 = 展示值」。
 */
import { describe, expect, it } from "vitest";
import {
  compareTradeDate,
  formatTradeDate,
  typeClass,
  type TransactionRow
} from "../model";

const row = (over: Partial<TransactionRow> = {}) =>
  ({ id: 1, type: "buy", ...over }) as TransactionRow;

describe("formatTradeDate", () => {
  it("交易日优先、确认日兜底", () => {
    expect(
      formatTradeDate(
        row({ trade_date: "2026-06-03", confirm_date: "2026-06-04" })
      )
    ).toBe("2026-06-03");
    expect(
      formatTradeDate(row({ trade_date: null, confirm_date: "2026-06-04" }))
    ).toBe("2026-06-04");
  });

  it("两个日期都没有时给 --", () => {
    expect(formatTradeDate(row())).toBe("--");
  });

  it("接口漏出带时间的值时只印日期（#2712 的 T00:00:00）", () => {
    expect(formatTradeDate(row({ trade_date: "2026-06-03T00:00:00" }))).toBe(
      "2026-06-03"
    );
  });
});

describe("compareTradeDate", () => {
  it("比较有效交易日，而不是只看 trade_date", () => {
    const onlyConfirm = row({ trade_date: null, confirm_date: "2026-06-10" });
    const older = row({ trade_date: "2026-06-01" });
    // 后端口径是 COALESCE(trade_date, confirm_date)：只有确认日的行按确认日参与排序
    expect(compareTradeDate(onlyConfirm, older)).toBeGreaterThan(0);
    expect(compareTradeDate(older, onlyConfirm)).toBeLessThan(0);
  });

  it("同一天返回 0（交给后端 id 兜底，前端不臆造顺序）", () => {
    expect(
      compareTradeDate(
        row({ trade_date: "2026-06-03" }),
        row({ trade_date: null, confirm_date: "2026-06-03" })
      )
    ).toBe(0);
  });
});

describe("typeClass", () => {
  it("买入/存入=涨红，卖出/取出=跌绿，其余中性", () => {
    expect(typeClass("buy")).toBe("txn-type--rise");
    expect(typeClass("deposit")).toBe("txn-type--rise");
    expect(typeClass("sell")).toBe("txn-type--fall");
    expect(typeClass("withdraw")).toBe("txn-type--fall");
    expect(typeClass("dividend")).toBe("txn-type--info");
    expect(typeClass("split")).toBe("txn-type--info");
  });
});
