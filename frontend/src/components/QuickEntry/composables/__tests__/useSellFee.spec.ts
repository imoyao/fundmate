/**
 * 卖出费用计算的回归（阶段 0）。
 *
 * 钉住一条口径：**非基金（股票/ETF/债券）的 `form.fee` 不能被费率计算清掉**。
 *
 * 为什么这条值得单独测：`calculateFeeAndRate` 挂在模板的
 * `[price, quantity, trade_date, isAfter15]` watch 上。它此前对非基金无条件
 * `form.fee = 0`，于是用户填的费用会在下一次改价格/数量时被静默吃掉——
 * 即使模板上给了输入框，也等于没有。这是「股票卖出永远记不到费用」的第二个成因，
 * 只靠组件渲染测试看不出来（模板渲染正常、值却被覆盖）。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ref } from "vue";

vi.mock("element-plus", () => ({
  ElMessage: {
    info: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    success: vi.fn()
  },
  ElMessageBox: { confirm: vi.fn() }
}));

vi.mock("@/api/funds", () => ({
  estimateRedeemFee: vi.fn(),
  syncFundFees: vi.fn()
}));

import { estimateRedeemFee } from "@/api/funds";
import type { Position } from "@/api/types";
import { useSellFee } from "../useSellFee";

const mockedEstimate = vi.mocked(estimateRedeemFee);

function mkForm(overrides: Record<string, unknown> = {}) {
  return {
    type: "stock",
    trade_date: "2026-11-05",
    quantity: 200 as number | undefined,
    fee: 5.32 as number | undefined,
    ...overrides
  };
}

/**
 * 构造一条持仓：`Position` 的必填字段一次给全，避免用 `as any` 造半截对象
 * （那样连「字段名写错」都不会被发现）。
 */
function mkPosition(overrides: Partial<Position> = {}): Position {
  return {
    id: 1,
    symbol: "600519",
    name: null,
    market: "CN_A",
    type: "stock",
    account_name: "测试账户",
    quantity: 200,
    avg_price: 10,
    currency: "CNY",
    current_price: 10,
    trade_date: "2026-01-05",
    notes: null,
    created_at: "2026-01-05T00:00:00",
    updated_at: "2026-01-05T00:00:00",
    ...overrides
  };
}

describe("useSellFee.calculateFeeAndRate", () => {
  beforeEach(() => {
    mockedEstimate.mockReset();
  });

  it("股票：保留用户填写的费用，不置 0、不请求赎回费率", async () => {
    const form = mkForm();
    const selectedPosition = ref<Position | null>(
      mkPosition({ type: "stock" })
    );
    const { calculateFeeAndRate } = useSellFee({ form, selectedPosition });

    await calculateFeeAndRate();

    expect(form.fee).toBe(5.32);
    expect(mockedEstimate).not.toHaveBeenCalled();
  });

  it("股票：未填费用时保持 undefined，不被动写成 0", async () => {
    const form = mkForm({ fee: undefined });
    const selectedPosition = ref<Position | null>(
      mkPosition({ type: "stock" })
    );
    const { calculateFeeAndRate } = useSellFee({ form, selectedPosition });

    await calculateFeeAndRate();

    expect(form.fee).toBeUndefined();
  });

  it("基金：仍按后端估算覆盖费用（未被本次修复影响）", async () => {
    mockedEstimate.mockResolvedValue({
      data: { total_fee: 12.5, holdings: [], sell: [] },
      message: "ok"
    });
    const form = mkForm({ type: "fund", fee: 0 });
    const selectedPosition = ref<Position | null>(
      mkPosition({ id: 2, type: "fund", confirm_date: "2026-01-05" })
    );
    const { calculateFeeAndRate } = useSellFee({ form, selectedPosition });

    await calculateFeeAndRate();

    expect(form.fee).toBe(12.5);
    expect(mockedEstimate).toHaveBeenCalledTimes(1);
  });
});
