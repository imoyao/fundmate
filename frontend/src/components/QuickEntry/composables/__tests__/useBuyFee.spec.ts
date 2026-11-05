/**
 * 买入手续费预设口径（股票/ETF 开放费用输入后新增）。
 *
 * 钉住两件事，二者都在「从基金切到股票」这条常见路径上出过错：
 * 1. **单位归一**：股票只有金额口径，残留的 `feeMode='rate'` 必须归位 ——
 *    留着它会让 5 元被当成 5% 换算，差 100 倍。
 * 2. **基金不被误伤**：基金仍按「申购费 × 折扣」预设，费率模式可继续用。
 */
import { describe, it, expect } from "vitest";
import { computed, ref } from "vue";
import { useBuyFee } from "../useBuyFee";
import type { SecurityOption } from "../useSecuritySearch";
import type { LedgerItem } from "@/api/ledger";

function setup(input: {
  ledgerType: string;
  feeConfig?: unknown;
  target: Partial<SecurityOption>;
}) {
  const form = { fee: 0 as number | undefined, buyAmount: 10000 };
  const ledger = {
    id: 1,
    name: "测试账户",
    ledger_type: input.ledgerType,
    fee_config: input.feeConfig
  } as unknown as LedgerItem;
  const api = useBuyFee({
    form,
    currentLedger: computed(() => ledger),
    selectedSecurityOption: ref<SecurityOption | null>({
      symbol: "600519",
      name: "贵州茅台",
      market: "CN_A",
      type: "stock",
      ...input.target
    })
  });
  return { form, ...api };
}

describe("applyFeePreset 股票/ETF：只有金额口径", () => {
  it("残留的费率模式被归位为金额模式", () => {
    const { feeMode, applyFeePreset } = setup({
      ledgerType: "stock",
      target: { type: "stock" }
    });
    feeMode.value = "rate";
    applyFeePreset();
    expect(feeMode.value).toBe("amount");
  });

  it("按账户佣金率预设金额（10000 × 0.03% = 3 元）", () => {
    const { form, applyFeePreset } = setup({
      ledgerType: "stock",
      feeConfig: { commission: { rate: 0.0003, min: null } },
      target: { type: "stock" }
    });
    applyFeePreset();
    expect(form.fee).toBeCloseTo(3, 6);
  });

  it("ETF 与股票同口径（同样只填金额）", () => {
    const { feeMode, applyFeePreset } = setup({
      ledgerType: "stock",
      target: { type: "etf" }
    });
    feeMode.value = "rate";
    applyFeePreset();
    expect(feeMode.value).toBe("amount");
  });
});

describe("applyFeePreset 基金：费率模式保留，不被上一条误伤", () => {
  it("基金标的切换账户后仍是费率模式", () => {
    const { feeMode, applyFeePreset } = setup({
      ledgerType: "fund",
      target: { type: "fund", subscription_rate: 0.015 }
    });
    feeMode.value = "rate";
    applyFeePreset();
    expect(feeMode.value).toBe("rate");
  });

  it("按申购费 × 折扣预设金额（10000 × 1.5% × 1折 = 15 元）", () => {
    const { form, applyFeePreset } = setup({
      ledgerType: "fund",
      feeConfig: { subscription_discount: 0.1 },
      target: { type: "fund", subscription_rate: 0.015 }
    });
    applyFeePreset();
    expect(form.fee).toBeCloseTo(15, 6);
  });
});
