/**
 * 交易流水表的行口径（#2712 + 流水页重设计 §三）：日期展示、客户端排序键、类型着色、
 * 持仓三态、代码位、状态声量。
 *
 * 前半段此前散在组件里且**四端各写一份**（日期一处只认 trade_date、一处只认
 * confirm_date），所以单测直接钉住「交易日优先、确认日兜底」与「排序键 = 展示值」。
 *
 * 后半段是重设计引入的四条判据，每一条都对应一种「页面不报错、只是慢慢说谎」的失败：
 * 已清仓判据（#2343 清仓不删行后按 position_id 判会几乎永不命中）、字段缺失被当成
 * 某个值、内部占位码漏到界面、成功标签满屏染色。
 */
import { describe, expect, it } from "vitest";
import {
  assetCodeText,
  CLEARED_BADGE_TITLE,
  compareTradeDate,
  formatTradeDate,
  isAccountLevel,
  isInternalSymbol,
  positionStateOf,
  statusTone,
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

describe("positionStateOf", () => {
  it("读后端下发的三态", () => {
    expect(positionStateOf(row({ position_state: "held" }))).toBe("held");
    expect(positionStateOf(row({ position_state: "cleared" }))).toBe("cleared");
    expect(positionStateOf(row({ position_state: "account" }))).toBe("account");
  });

  it("字段缺失 / 未知值 → unknown，**不**按 position_id 猜", () => {
    // 旧缓存或未升级接口：宁可不出胶囊，也不赌一个可能错的结论。
    // 按 position_id === null 判「已清仓」在 #2343「清仓不删行」之后会让胶囊
    // 几乎永不出现（已清仓的流水 position_id 仍有值）。
    expect(positionStateOf(row({ position_id: null }))).toBe("unknown");
    expect(positionStateOf(row({ position_id: 12 }))).toBe("unknown");
    expect(positionStateOf(row({ position_state: "weird" }))).toBe("unknown");
    expect(positionStateOf(row({ position_state: null }))).toBe("unknown");
  });
});

describe("assetCodeText", () => {
  it("普通持仓给出代码", () => {
    expect(
      assetCodeText(row({ position_state: "held", symbol: "SZ000001" }))
    ).toBe("SZ000001");
  });

  it("内部占位码不显示（写进库是为了对齐字段，不该上屏）", () => {
    expect(
      assetCodeText(row({ position_state: "account", symbol: "__CASH__" }))
    ).toBeNull();
    expect(isInternalSymbol("_CASH_")).toBe(true);
    expect(isInternalSymbol("004369")).toBe(false);
    expect(isInternalSymbol(null)).toBe(false);
  });

  it("资金流水没有代码，不印占位符", () => {
    expect(
      assetCodeText(row({ position_state: "account", symbol: null }))
    ).toBeNull();
    // 即使带了代码（历史数据），账户级流水也不把代码当标的展示
    expect(
      assetCodeText(row({ position_state: "account", symbol: "004369" }))
    ).toBeNull();
  });

  it("空串 / 纯空格视作没有代码", () => {
    expect(
      assetCodeText(row({ position_state: "held", symbol: "   " }))
    ).toBeNull();
    expect(
      assetCodeText(row({ position_state: "held", symbol: null }))
    ).toBeNull();
  });
});

describe("isAccountLevel", () => {
  it("只有 account 态算资金流水；unknown 不算（不知道就别下结论）", () => {
    expect(isAccountLevel(row({ position_state: "account" }))).toBe(true);
    expect(isAccountLevel(row({ position_state: "cleared" }))).toBe(false);
    expect(isAccountLevel(row({ position_state: "held" }))).toBe(false);
    expect(isAccountLevel(row({ position_id: null }))).toBe(false);
  });
});

describe("statusTone", () => {
  it("成功与缺失都静默（常态不染色）", () => {
    expect(statusTone("success")).toBe("silent");
    expect(statusTone(null)).toBe("silent");
    expect(statusTone(undefined)).toBe("silent");
  });

  it("只有异常态出声，且各有各的声量", () => {
    expect(statusTone("failed")).toBe("danger");
    expect(statusTone("pending")).toBe("warning");
    expect(statusTone("cancelled")).toBe("outline");
  });

  it("未知状态也静默：不认识的值不该抢注意力", () => {
    expect(statusTone("weird")).toBe("silent");
  });
});

describe("CLEARED_BADGE_TITLE", () => {
  it("说明为什么保留而不是删除（用户看到胶囊会问这句）", () => {
    expect(CLEARED_BADGE_TITLE).toContain("清仓");
    expect(CLEARED_BADGE_TITLE).toContain("保留");
  });
});
