/**
 * 实时行情取数闸门单测（#2338）。
 *
 * 分三层，缺一层这卡就不算闭环：
 *
 * 1. **纯函数**（`marketHours`）：时段边界 + 交易日/日历失败的保守分支。
 *    这是「休市日一律不取数」的判据本体，此前内联在 composable 里，
 *    vitest 是 node 环境（无 jsdom），测不了依赖 http/localStorage 的 composable，
 *    故抽出纯函数才有得测。
 * 2. **接线守卫**（源码断言）：三个取数入口必须都过 `canFetch()`，且
 *    `useRealtimeQuotes` 里**不得再出现内联的 `getHours()` 时段判断**——
 *    #2338 的根因就是四条入口各写一份判断、其中三份写歪。
 * 3. **置灰守卫**：休市/收盘时刷新控件必须禁用，否则用户点了没反应，
 *    正是本卡验收第 5 条要避免的「看着像数据坏了」。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  isWithinTradingWindow,
  shouldFetchRealtimeQuotes,
  TRADING_WINDOW_START_MINUTE,
  TRADING_WINDOW_END_MINUTE
} from "../marketHours";

/** 本地时区构造时刻：2026-10-19（周一）仅作载体，时段判定不看日期 */
const at = (hour: number, minute: number) =>
  new Date(2026, 9, 19, hour, minute);

const readSrc = (relative: string) =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

describe("窗口常量", () => {
  it("9:30 开盘 / 15:00 收盘（自 00:00 起的分钟数）", () => {
    expect(TRADING_WINDOW_START_MINUTE).toBe(570);
    expect(TRADING_WINDOW_END_MINUTE).toBe(900);
  });
});

describe("isWithinTradingWindow（只看时钟）", () => {
  const cases: Array<[string, number, number, boolean]> = [
    ["开盘前 1 分钟", 9, 29, false],
    ["开盘整点", 9, 30, true],
    ["早盘", 10, 15, true],
    ["午休（既有口径：仍取数，见模块注释）", 12, 0, true],
    ["尾盘", 14, 59, true],
    ["收盘整点", 15, 0, true],
    ["收盘后 1 分钟", 15, 1, false],
    ["清晨", 8, 0, false],
    ["深夜", 22, 30, false]
  ];

  it.each(cases)("%s（%d:%02d）→ %s", (_name, h, m, expected) => {
    expect(isWithinTradingWindow(at(h, m))).toBe(expected);
  });
});

describe("shouldFetchRealtimeQuotes（时钟 + 交易日）", () => {
  it("交易日 + 盘中 → 取", () => {
    expect(
      shouldFetchRealtimeQuotes({ now: at(10, 30), isTradingDay: true })
    ).toBe(true);
  });

  it("交易日 + 盘后 → 不取", () => {
    expect(
      shouldFetchRealtimeQuotes({ now: at(18, 0), isTradingDay: true })
    ).toBe(false);
  });

  it("非交易日（周末）即使盘中也不取", () => {
    expect(
      shouldFetchRealtimeQuotes({ now: at(10, 30), isTradingDay: false })
    ).toBe(false);
  });

  it("非交易日（工作日法定假日）盘中也不取 —— #2338 用户反馈的主场景", () => {
    // 2026-10-01 国庆：getDay() 是周四，旧逻辑只看星期就会整段轮询
    const nationalDay = new Date(2026, 9, 1, 10, 30);
    expect(nationalDay.getDay()).toBe(4); // 前置断言：确是工作日
    expect(
      shouldFetchRealtimeQuotes({ now: nationalDay, isTradingDay: false })
    ).toBe(false);
  });

  it("交易日历接口失败（保守 false）→ 盘中也不取", () => {
    // 宁可盘中少一轮估值，也不把休市日误判成交易日空跑
    expect(
      shouldFetchRealtimeQuotes({ now: at(10, 30), isTradingDay: false })
    ).toBe(false);
  });
});

describe("接线守卫：取数入口必须统一过 canFetch（源码断言）", () => {
  const quotesSrc = readSrc("../../composables/useRealtimeQuotes.ts");

  it("canFetch 被三处入口调用（start / manualRefresh / 轮询 tick）", () => {
    const calls = quotesSrc.match(/await canFetch\(\)/g) ?? [];
    // 定义处不消耗一次调用，故 ≥3 才是「三条入口都过闸」
    expect(calls.length).toBeGreaterThanOrEqual(3);
  });

  it("canFetch 走 utils/marketHours 的纯函数，不自己算时段", () => {
    expect(quotesSrc).toContain('from "@/utils/marketHours"');
    expect(quotesSrc).toContain("shouldFetchRealtimeQuotes(");
  });

  it("不得残留内联的 getHours() / hour < 9 时段判断（#2338 回潮）", () => {
    expect(quotesSrc).not.toMatch(/getHours\(\)/);
    expect(quotesSrc).not.toMatch(/hour\s*<\s*9/);
  });

  it("交易日历查不到时保守返回 false（不把工作日当交易日）", () => {
    // 失败分支：catch 里不写缓存、返回 false
    expect(quotesSrc).toMatch(/catch[\s\S]{0,200}?return false/);
  });
});

describe("置灰守卫：休市时刷新控件必须禁用（源码断言）", () => {
  const barSrc = readSrc("../../views/asset/watchlist/WatchlistSummaryBar.vue");

  it("按 status === closed 推导 marketClosed", () => {
    expect(barSrc).toMatch(
      /marketClosed\s*=\s*computed\([\s\S]{0,120}?"closed"/
    );
  });

  it('刷新档位与手动刷新都带 :disabled="marketClosed"', () => {
    const disabled = barSrc.match(/:disabled="marketClosed"/g) ?? [];
    expect(disabled.length).toBeGreaterThanOrEqual(2);
  });

  it("给出置灰原因（tooltip + aria-label 同源文案），不是静默置灰", () => {
    expect(barSrc).toContain("closedHint");
    expect(barSrc).toContain("休市不抓取");
  });
});
