/**
 * 卖出提交载荷单测（#980 拆分时新增）。
 *
 * 与买入不同，卖出的三个字段最容易错的地方是「谁留空」：确认日只有基金留空
 * （T+1 由后端净值链路算），股票/ETF 必须当日确认；金额是「数量 × 成交价」原值，
 * 不能扣手续费（手续费单列，扣两次会让净回款少算一笔）。
 */
import { describe, it, expect } from "vitest";
import { buildSellPayload } from "../sellFormPayload";
import { defaultSellForm, type SellFormModel } from "../sellFormModel";

function mkForm(overrides: Partial<SellFormModel> = {}): SellFormModel {
  return {
    ...defaultSellForm(),
    ledger_id: 3,
    positionId: 88,
    symbol: "110011",
    name: "易方达中小盘",
    market: "CN_A",
    type: "fund",
    quantity: 100,
    price: 3.5,
    fee: 1.2,
    trade_date: "2026-10-23",
    ...overrides
  };
}

describe("buildSellPayload", () => {
  it("基金：确认日留空（null）交给后端算 T+1", () => {
    const body = buildSellPayload({
      form: mkForm(),
      accountName: "天天基金",
      quantity: 100
    });
    expect(body.confirm_date).toBeNull();
  });

  it("股票：确认日等于交易日", () => {
    const body = buildSellPayload({
      form: mkForm({ type: "stock", positionId: 9 }),
      accountName: "华泰",
      quantity: 200
    });
    expect(body.confirm_date).toBe("2026-10-23");
  });

  it("金额 = 数量 × 成交价（不扣手续费）", () => {
    const body = buildSellPayload({
      form: mkForm({ price: 3.5, fee: 1.2 }),
      accountName: "",
      quantity: 100
    });
    expect(body.amount).toBeCloseTo(350, 6);
    expect(body.fee).toBe(1.2);
  });

  it("手续费缺失按 0、配置目标固定 null、position_id 透传", () => {
    const body = buildSellPayload({
      form: mkForm({ fee: undefined }),
      accountName: "",
      quantity: 10
    });
    expect(body.fee).toBe(0);
    expect(body.allocation).toBeNull();
    expect(body.position_id).toBe(88);
    expect(body.op_type).toBe("sell");
  });

  it("market 缺失回退 CN_A", () => {
    const body = buildSellPayload({
      form: mkForm({ market: "" }),
      accountName: "",
      quantity: 10
    });
    expect(body.market).toBe("CN_A");
  });
});
