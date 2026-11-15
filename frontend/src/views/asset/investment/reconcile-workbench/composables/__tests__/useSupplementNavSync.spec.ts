/**
 * 补录弹窗的「交易日期 → 确认净值」联动。
 *
 * 这里钉的是两条会静默记错成本价的边界：
 * 1. 净值查不到 ⇒ 清掉**系统填的**净值，并置 navMissing（联动据此停手，份额留给用户）；
 * 2. 用户手改过净值 ⇒ 之后拉不到净值也不许把它清掉（那是用户照账单填的数）。
 */
import { describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, reactive, ref } from "vue";
import { useSupplementNavSync } from "../useSupplementNavSync";

function flush(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 0));
}

function setup(options: {
  assetType?: string;
  nav?: number | null;
  date?: string;
}) {
  const form = reactive({
    op_type: "buy",
    confirm_date: "",
    avg_price: undefined as number | undefined,
    buy_amount: undefined as number | undefined
  });
  const assetType = ref(options.assetType ?? "fund");
  const calcConfirmAndNav = vi.fn(async () => {
    if (options.nav == null) return null;
    return {
      actualNavDate: options.date ?? "2022-01-05",
      confirmDate: options.date ?? "2022-01-06",
      nav: options.nav
    };
  });
  const scope = effectScope();
  const api = scope.run(() =>
    useSupplementNavSync({
      form,
      assetType,
      symbol: () => "013883",
      calcConfirmAndNav
    })
  )!;
  return {
    form,
    assetType,
    calcConfirmAndNav,
    ...api,
    stop: () => scope.stop()
  };
}

describe("useSupplementNavSync", () => {
  it("场外基金买入：选了日期就回填当日净值，并说明来源", async () => {
    const s = setup({ nav: 1.2345 });
    s.form.confirm_date = "2022-01-05";
    await nextTick();
    await flush();
    expect(s.calcConfirmAndNav).toHaveBeenCalledOnce();
    expect(s.form.avg_price).toBe(1.2345);
    expect(s.navMissing.value).toBe(false);
    expect(s.navHint.value).toContain("2022-01-05");
    s.stop();
  });

  it("净值查不到：置 navMissing 并清掉自动值，提示手填", async () => {
    const s = setup({ nav: null });
    s.form.confirm_date = "2022-01-05";
    await nextTick();
    await flush();
    expect(s.form.avg_price).toBeUndefined();
    expect(s.navMissing.value).toBe(true);
    expect(s.navHint.value).toContain("查不到");
    s.stop();
  });

  it("用户手改过的净值不会被系统清掉（只有自动填的值才清）", async () => {
    const s = setup({ nav: 1.2345 });
    s.form.confirm_date = "2022-01-05";
    await nextTick();
    await flush();
    expect(s.form.avg_price).toBe(1.2345);

    // 用户照对账单改成实际确认净值
    s.form.avg_price = 1.3;
    await nextTick();

    // 换一天，这天没有净值
    s.calcConfirmAndNav.mockResolvedValueOnce(null);
    s.form.confirm_date = "2022-01-06";
    await nextTick();
    await flush();
    expect(s.navMissing.value).toBe(true);
    expect(s.form.avg_price).toBe(1.3);
    s.stop();
  });

  it("股票 / ETF 不拉净值（没有当日净值这回事）", async () => {
    const s = setup({ assetType: "stock", nav: 1.2345 });
    s.form.confirm_date = "2022-01-05";
    await nextTick();
    await flush();
    expect(s.calcConfirmAndNav).not.toHaveBeenCalled();
    expect(s.form.avg_price).toBeUndefined();
    expect(s.navHint.value).toBe("");
    s.stop();
  });

  it("卖出档不拉净值（卖出填的是账单上的份额）", async () => {
    const s = setup({ nav: 1.2345 });
    s.form.op_type = "sell";
    s.form.confirm_date = "2022-01-05";
    await nextTick();
    await flush();
    expect(s.calcConfirmAndNav).not.toHaveBeenCalled();
    s.stop();
  });
});
