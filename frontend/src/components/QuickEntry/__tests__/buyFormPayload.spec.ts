/**
 * 买入提交载荷单测（#980 拆分时新增）。
 *
 * 为什么值得单测：`handleSubmit` 里三处口径原先只能靠「跑一遍真实记账」验证——
 * 而这三处正是历史上出过事的地方：
 * 1. **确认日**：基金取净值链路的 confirmDate，空串必须视为缺失（否则后端收到 ""）；
 *    股票必须等于交易日。两者混用会让 T+1 确认算错。
 * 2. **手续费单位**：费率模式下用户填的是百分比，提交前必须换算成元。少乘这一步，
 *    后端收到 0.15 元而不是 1.5 元，成本静默偏移。
 * 3. **净值缺失三件套**：nav_pending / nav_date / shares_manual 缺一个，回填任务就会
 *    覆盖用户手填的份额，或按错日期回填。
 */
import { describe, it, expect } from "vitest";
import { buildBuyPayload, type BuyPayloadForm } from "../buyFormPayload";

function mkForm(overrides: Partial<BuyPayloadForm> = {}): BuyPayloadForm {
  return {
    symbol: "110011",
    name: "易方达中小盘",
    market: "CN_A",
    type: "fund",
    ledger_id: 7,
    price: 3.5,
    buyAmount: 1000,
    fee: 1.5,
    currency: "CNY",
    trade_date: "2026-10-23",
    notes: "",
    allocation: "longterm",
    isAfter15: false,
    ...overrides
  };
}

const base = {
  accountName: "天天基金",
  quantity: 285.2857,
  confirmDate: "2026-10-24",
  navPending: false,
  navDate: "2026-10-23",
  feeMode: "amount" as const
};

describe("buildBuyPayload 确认日口径", () => {
  it("基金：确认日取净值链路给出的 confirmDate", () => {
    const body = buildBuyPayload({ ...base, form: mkForm() });
    expect(body.confirm_date).toBe("2026-10-24");
  });

  it("基金：confirmDate 为空串时提交 null（不能传空串）", () => {
    const body = buildBuyPayload({ ...base, confirmDate: "", form: mkForm() });
    expect(body.confirm_date).toBeNull();
  });

  it("基金：confirmDate 只有空白字符同样视为缺失", () => {
    const body = buildBuyPayload({
      ...base,
      confirmDate: "   ",
      form: mkForm()
    });
    expect(body.confirm_date).toBeNull();
  });

  it("股票：确认日永远等于交易日，忽略 confirmDate", () => {
    const body = buildBuyPayload({
      ...base,
      confirmDate: "2026-10-24",
      form: mkForm({ type: "stock", price: 12.34 })
    });
    expect(body.confirm_date).toBe("2026-10-23");
  });
});

describe("buildBuyPayload 手续费换算", () => {
  it("费率模式：百分比换成元", () => {
    const body = buildBuyPayload({
      ...base,
      feeMode: "rate",
      form: mkForm({ fee: 0.15, buyAmount: 1000 })
    });
    expect(body.fee).toBeCloseTo(1.5, 6);
  });

  it("金额模式：原样提交", () => {
    const body = buildBuyPayload({ ...base, form: mkForm({ fee: 2.5 }) });
    expect(body.fee).toBe(2.5);
  });

  it("手续费缺失时按 0 提交", () => {
    const body = buildBuyPayload({ ...base, form: mkForm({ fee: undefined }) });
    expect(body.fee).toBe(0);
  });

  it("股票/ETF 残留费率模式时，仍按金额原样提交", () => {
    // 只有基金有费率口径（`BuyFeeField` 的 simple 模式隐藏了模式切换）。
    // feeMode 若残留 rate，这里再乘一次会把 5 元当成 5% ⇒ 500 元。
    const body = buildBuyPayload({
      ...base,
      feeMode: "rate",
      form: mkForm({ type: "stock", price: 12.34, fee: 5, buyAmount: 10000 })
    });
    expect(body.fee).toBe(5);
  });

  it("股票/ETF 金额模式下也原样提交", () => {
    const body = buildBuyPayload({
      ...base,
      form: mkForm({ type: "etf", price: 3.2, fee: 2.5, buyAmount: 10000 })
    });
    expect(body.fee).toBe(2.5);
  });
});

describe("buildBuyPayload 净值缺失先记账三件套", () => {
  it("navPending 打开时带 nav_pending / nav_date / shares_manual", () => {
    const body = buildBuyPayload({
      ...base,
      navPending: true,
      form: mkForm({ buyAmount: 500 })
    });
    expect(body.nav_pending).toBe(true);
    expect(body.nav_date).toBe("2026-10-23");
    expect(body.shares_manual).toBe(true);
  });

  it("navDate 缺失时 nav_date 回退交易日", () => {
    const body = buildBuyPayload({
      ...base,
      navPending: true,
      navDate: "",
      form: mkForm()
    });
    expect(body.nav_date).toBe("2026-10-23");
  });

  it("份额留空时不标 shares_manual（回填可自由写份额）", () => {
    const body = buildBuyPayload({
      ...base,
      navPending: true,
      quantity: 0,
      form: mkForm()
    });
    expect(body.shares_manual).toBe(false);
  });

  it("非 navPending 时不出现 nav_pending 字段", () => {
    const body = buildBuyPayload({ ...base, form: mkForm() });
    expect("nav_pending" in body).toBe(false);
    expect("shares_manual" in body).toBe(false);
  });
});

describe("buildBuyPayload 投顾组合（D70 / #2740）", () => {
  const portfolioForm = (overrides: Partial<BuyPayloadForm> = {}) =>
    mkForm({
      type: "portfolio",
      symbol: "ZH123456",
      price: undefined,
      ...overrides
    });

  it("必须显式带 valuation_mode='balance'", () => {
    const body = buildBuyPayload({
      ...base,
      form: portfolioForm(),
      quantity: 0
    });
    expect(body.valuation_mode).toBe("balance");
  });

  it("普通标的不得带 valuation_mode：不传由后端按默认 nav 处理", () => {
    const body = buildBuyPayload({ ...base, form: mkForm() });
    expect("valuation_mode" in body).toBe(false);
  });

  it("份额与均价恒为 0：组合没有份额、也没有单价", () => {
    const body = buildBuyPayload({
      ...base,
      form: portfolioForm(),
      quantity: 285.2857
    });
    expect(body.quantity).toBe(0);
    expect(body.avg_price).toBe(0);
  });

  it("手续费恒为 0：费率模式下也不按申购费率换算", () => {
    // applyFeePreset 仍会为账户填上一个费率，用户看不到该字段 → 必须归零，
    // 否则一笔 10 万买入会静默记进 150 元手续费。
    const body = buildBuyPayload({
      ...base,
      feeMode: "rate",
      form: portfolioForm({ fee: 0.15, buyAmount: 100000 })
    });
    expect(body.fee).toBe(0);
  });

  it("金额原样提交：balance 模式靠 amount 记账", () => {
    const body = buildBuyPayload({
      ...base,
      form: portfolioForm({ buyAmount: 8000 })
    });
    expect(body.amount).toBe(8000);
  });
});

describe("buildBuyPayload 其余字段", () => {
  it("market 缺失回退 CN_A，price 缺失回退 0", () => {
    const body = buildBuyPayload({
      ...base,
      form: mkForm({ market: "", price: undefined })
    });
    expect(body.market).toBe("CN_A");
    expect(body.avg_price).toBe(0);
  });

  it("金额、账户名、配置目标、15:00 标记原样透传", () => {
    const body = buildBuyPayload({
      ...base,
      form: mkForm({ isAfter15: true, notes: "定投" })
    });
    expect(body.amount).toBe(1000);
    expect(body.account_name).toBe("天天基金");
    expect(body.allocation).toBe("longterm");
    expect(body.isAfter15).toBe(true);
    expect(body.notes).toBe("定投");
    expect(body.op_type).toBe("buy");
    expect(body.quantity).toBe(285.2857);
  });
});

describe("buildBuyPayload 打新中签（D95：买入价格可手填）", () => {
  it("成交价不同于当日收盘价时，照实提交中签价与中签数量", () => {
    // 新股中签的真实形态：发行价 7.35、中签 500 股、缴款 3675、无手续费。
    // 价格框开放前，avg_price 只能等于回填的收盘价，这组数字根本传不出去
    // （500 股必然被算成 500×收盘价），本次把这条路径钉住。
    const body = buildBuyPayload({
      ...base,
      form: mkForm({
        symbol: "603543",
        name: "模拟新材",
        type: "stock",
        price: 7.35,
        buyAmount: 3675,
        fee: 0
      }),
      quantity: 500,
      confirmDate: "2024-03-02"
    });
    expect(body.avg_price).toBe(7.35);
    expect(body.quantity).toBe(500);
    expect(body.amount).toBe(3675);
    // 股票确认日仍等于交易日，不取 confirmDate（既有口径，勿随价格改动一起漂移）
    expect(body.confirm_date).toBe("2026-10-23");
  });
});
