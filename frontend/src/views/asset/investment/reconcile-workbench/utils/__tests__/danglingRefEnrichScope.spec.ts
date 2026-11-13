/**
 * 「补全信息」弹窗静态缺口判断的单测（2026-11-13）。
 *
 * 钉住两件会让这个弹窗重新变成「看不懂」的事：
 *   ① 缺口算错 ⇒ 给有代码的组继续显示「标的代码」输入框（填了永远 0 条）；
 *   ② 变化过滤失效 ⇒ 预览把未变化的行也列成「变更」，与统计行的
 *      「无需改动 N 条」自相矛盾。
 */
import { describe, expect, it } from "vitest";
import {
  changeActuallyWrites,
  inspectGroupNeeds,
  pickChangedRows
} from "../danglingRefEnrichScope";

describe("inspectGroupNeeds：这组缺什么", () => {
  it("代码与日期都缺：两个计数都等于条数", () => {
    const needs = inspectGroupNeeds([
      { symbol: null, trade_date: null },
      { symbol: "", trade_date: null }
    ]);
    expect(needs).toEqual({
      txnCount: 2,
      needSymbol: 2,
      needDate: 2,
      symbol: null,
      complete: false
    });
  });

  it("只缺日期：代码齐了，needSymbol 为 0 并给出组内代码", () => {
    const needs = inspectGroupNeeds([
      { symbol: "SZ128021", trade_date: null },
      { symbol: "SZ128021", trade_date: null }
    ]);
    expect(needs.needSymbol).toBe(0);
    expect(needs.needDate).toBe(2);
    expect(needs.symbol).toBe("SZ128021");
    expect(needs.complete).toBe(false);
  });

  it("只缺代码：日期齐了，needDate 为 0 且不臆造代码", () => {
    const needs = inspectGroupNeeds([
      { symbol: null, trade_date: "2022-01-04" },
      { symbol: "  ", trade_date: "2022-01-05" }
    ]);
    expect(needs.needSymbol).toBe(2);
    expect(needs.needDate).toBe(0);
    expect(needs.symbol).toBeNull();
    expect(needs.complete).toBe(false);
  });

  it("纯空白的代码按缺处理，不当成已有值", () => {
    const needs = inspectGroupNeeds([{ symbol: "   ", trade_date: null }]);
    expect(needs.needSymbol).toBe(1);
    expect(needs.symbol).toBeNull();
  });

  it("全齐：complete 为 true（这一组什么都补不了）", () => {
    const needs = inspectGroupNeeds([
      { symbol: "SZ128021", trade_date: "2022-01-04" },
      { symbol: "SZ128021", trade_date: "2022-01-05" }
    ]);
    expect(needs.complete).toBe(true);
    expect(needs.needSymbol).toBe(0);
    expect(needs.needDate).toBe(0);
  });

  it("空组不算 complete：空组由 guard 的 txnCount 判据单独说明", () => {
    const needs = inspectGroupNeeds([]);
    expect(needs.txnCount).toBe(0);
    expect(needs.complete).toBe(false);
  });

  it("组内代码从首个非空值取，去首尾空白", () => {
    const needs = inspectGroupNeeds([
      { symbol: null, trade_date: null },
      { symbol: "  SZ000725 ", trade_date: null }
    ]);
    expect(needs.symbol).toBe("SZ000725");
  });
});

describe("pickChangedRows：预览只列真变化", () => {
  const unchanged = {
    symbol_before: "SZ128021",
    symbol_after: "SZ128021",
    trade_date_before: null,
    trade_date_after: null
  };

  it("事前事后一致的行走不到列表里（截图里的 `SZ128021 → SZ128021`）", () => {
    expect(changeActuallyWrites(unchanged)).toBe(false);
    expect(pickChangedRows([unchanged, unchanged])).toEqual([]);
  });

  it("代码从缺补上算变化", () => {
    expect(
      changeActuallyWrites({
        symbol_before: null,
        symbol_after: "600519",
        trade_date_before: null,
        trade_date_after: null
      })
    ).toBe(true);
  });

  it("日期从缺补上算变化", () => {
    expect(
      changeActuallyWrites({
        symbol_before: "SZ128021",
        symbol_after: "SZ128021",
        trade_date_before: null,
        trade_date_after: "2022-01-04"
      })
    ).toBe(true);
  });

  it("空白与 null 视为同一件事，不算变化", () => {
    expect(
      changeActuallyWrites({
        symbol_before: "  ",
        symbol_after: null,
        trade_date_before: "",
        trade_date_after: null
      })
    ).toBe(false);
  });

  it("保持后端顺序，只做过滤不做排序", () => {
    const changed = {
      symbol_before: null,
      symbol_after: "600519",
      trade_date_before: null,
      trade_date_after: null
    };
    expect(pickChangedRows([unchanged, changed, unchanged])).toEqual([changed]);
  });
});
