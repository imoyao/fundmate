import { describe, expect, it } from "vitest";
import type { PortfolioItem } from "@/api/portfolio";
import {
  isInheritedFromLedger,
  portfolioLabel,
  resolvePortfolioOf,
  type PortfolioLookup
} from "../portfolioAssignModel";

/**
 * D20 二期 UI：持仓「所属组合」四态解析回归。
 *
 * 本组用例钉的是**判断本身，不是渲染**。原因是这四个分支在界面上长得几乎一样——
 * 都渲染成「一个组合名」或「一句占位」——判错时页面不会报错、不会空白，
 * 只会让用户对「这条持仓到底归在哪、是我指定的还是账户带的」得出错误结论，
 * 而那个结论正是改派功能存在的理由。所以只能靠单测守住。
 *
 * 最容易写错的两处：
 * 1. `undefined`（字段没下发）被当成 `null`（继承）→ 把「不知道」谎报成「随账户」；
 * 2. 继承态没查账户默认组合，一律显示「未归属」→ 用户看不出当前实际归在哪个组合。
 */

const portfolios: PortfolioItem[] = [
  { id: 3, name: "固收+" },
  { id: 5, name: "成长策略" }
];

/** 账户 11 默认组合 = 固收+(3)；账户 12 未设默认组合 */
const lookup: PortfolioLookup = {
  portfolios,
  ledgerPortfolioMap: { 11: 3, 12: null }
};

describe("resolvePortfolioOf（归属四态）", () => {
  it("显式指派：直接取该组合名，与账户默认组合无关", () => {
    // 持仓显式指向成长策略，即使所属账户的默认组合是固收+，也必须以显式为准
    const result = resolvePortfolioOf(
      { portfolio_id: 5, ledger_id: 11 },
      lookup
    );
    expect(result).toEqual({ mode: "explicit", labelText: "成长策略" });
  });

  it("账户继承：portfolio_id 为 null 时按所属账户的默认组合归属", () => {
    const result = resolvePortfolioOf(
      { portfolio_id: null, ledger_id: 11 },
      lookup
    );
    expect(result).toEqual({ mode: "inherited", labelText: "固收+" });
  });

  it("无归属：未指派且账户也没设默认组合", () => {
    const result = resolvePortfolioOf(
      { portfolio_id: null, ledger_id: 12 },
      lookup
    );
    expect(result).toEqual({ mode: "none", labelText: null });
  });

  it("无归属：未指派且拿不到 ledger_id（未归档持仓）", () => {
    // 未归档持仓没有账户可继承，不能凭空猜一个组合
    const result = resolvePortfolioOf({ portfolio_id: null }, lookup);
    expect(result).toEqual({ mode: "none", labelText: null });
  });

  it("未知：响应里没有 portfolio_id 字段时不得当成继承态", () => {
    // 资产行（现金）与旧版接口都不下发该字段。若当成 null 会显示成「随账户」，
    // 而现金没有持仓级组合概念，那个标签本身就不该出现。
    const result = resolvePortfolioOf({ ledger_id: 11 }, lookup);
    expect(result).toEqual({ mode: "unknown", labelText: null });
    expect(result.mode).not.toBe("inherited");
  });

  it("未知：字段显式为 undefined 同样按未知处理", () => {
    const result = resolvePortfolioOf(
      { portfolio_id: undefined, ledger_id: 11 },
      lookup
    );
    expect(result.mode).toBe("unknown");
  });

  it("组合不在列表里时降级为可辨识占位，不谎报未归属", () => {
    // 组合被删 / portfolios 还没加载完：仍要显示「它指向某个 id」，
    // 显示成「未归属」会让人以为这条持仓没归类过
    const result = resolvePortfolioOf(
      { portfolio_id: 99, ledger_id: 11 },
      lookup
    );
    expect(result).toEqual({ mode: "explicit", labelText: "组合 #99" });
  });

  it("账户默认组合指向已不存在的组合时同样降级", () => {
    const result = resolvePortfolioOf(
      { portfolio_id: null, ledger_id: 13 },
      { portfolios, ledgerPortfolioMap: { 13: 88 } }
    );
    expect(result).toEqual({ mode: "inherited", labelText: "组合 #88" });
  });
});

describe("resolvePortfolioOf（不进组合 · D20 二期开口项 4）", () => {
  /**
   * 这组钉的是「能不能归」压过「归到哪」：`in_portfolio === false` 的品种
   * （货基 / 逆回购 / 现金）在盘点页照样有一行，但 `build_portfolio_holdings`
   * 会把它们滤掉——改派成功后组合页永远看不到，是静默无效的交互。
   */
  it("后端说 in_portfolio=false 时一律渲染成 excluded，不管有没有显式指派", () => {
    // 即便 portfolio_id 有值（历史数据 / 用户先改派再被标记），也不展示组合名：
    // 显示「固收+」会让用户以为它真的在固收+里
    const result = resolvePortfolioOf(
      { portfolio_id: 5, ledger_id: 11, in_portfolio: false },
      lookup
    );
    expect(result).toEqual({ mode: "excluded", labelText: null });
  });

  it("in_portfolio=false 且未指派时不得退化成继承态", () => {
    // 退化成 inherited 会显示「固收+ 随账户」，与「不进组合」直接矛盾
    const result = resolvePortfolioOf(
      { portfolio_id: null, ledger_id: 11, in_portfolio: false },
      lookup
    );
    expect(result.mode).toBe("excluded");
    expect(result.mode).not.toBe("inherited");
  });

  it("in_portfolio=true 走原有归属判断，四态不变", () => {
    expect(
      resolvePortfolioOf(
        { portfolio_id: 5, ledger_id: 11, in_portfolio: true },
        lookup
      )
    ).toEqual({ mode: "explicit", labelText: "成长策略" });
    expect(
      resolvePortfolioOf(
        { portfolio_id: null, ledger_id: 11, in_portfolio: true },
        lookup
      )
    ).toEqual({ mode: "inherited", labelText: "固收+" });
  });

  it("字段缺失不等于不进组合", () => {
    // 旧缓存 / 未升级接口的行没有该字段。把 undefined 当 false 会让**所有**持仓
    // 都渲染成「— 不进组合」，改派入口全灭——这是本卡最容易写出的反向 bug
    const result = resolvePortfolioOf(
      { portfolio_id: 5, ledger_id: 11 },
      lookup
    );
    expect(result.mode).toBe("explicit");
    expect(result.mode).not.toBe("excluded");
  });
});

describe("isInheritedFromLedger", () => {
  it("null 才是继承态", () => {
    expect(isInheritedFromLedger({ portfolio_id: null })).toBe(true);
  });

  it("显式指派不是继承态", () => {
    expect(isInheritedFromLedger({ portfolio_id: 5 })).toBe(false);
  });

  it("字段缺失（资产行）不是继承态", () => {
    // 这一条是 `!row.portfolio_id` 写法会踩的坑：undefined 为 falsy，
    // 会把每一条现金都标成「随账户」
    expect(isInheritedFromLedger({})).toBe(false);
  });
});

describe("portfolioLabel", () => {
  it("命中时返回组合名", () => {
    expect(portfolioLabel(portfolios, 3)).toBe("固收+");
  });

  it("未命中时返回带 id 的占位，不返回空串", () => {
    // 空串会让整格变成空白，被读成「没有归属」
    expect(portfolioLabel(portfolios, 77)).toBe("组合 #77");
  });
});
