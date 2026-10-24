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
