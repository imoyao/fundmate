/**
 * 通用「金额 ⇄ 份额 ⇄ 净值 ⇄ 手续费」联动（2026-11-15 从记一笔的
 * `useBuySharesLinkage` 上提，对账补录也吃这一份）。
 *
 * 这里用的字段名是**对账补录**那一套（`buy_amount / quantity / avg_price`），
 * 记一笔那一套（`buyAmount / shares / price`）由
 * `components/QuickEntry/composables/__tests__/useBuySharesLinkage.spec.ts` 继续钉住——
 * 两份测试一起才说明「共用没有把任何一侧改坏」。
 */
import { describe, expect, it } from "vitest";
import { effectScope, nextTick, reactive, ref } from "vue";
import { useSharesLinkage } from "../useSharesLinkage";

interface Form {
  buy_amount?: number;
  quantity?: number;
  avg_price?: number;
  fee?: number;
}

function setup(
  init: Form = {},
  enabled = () => true,
  mode?: () => "fund" | "trade"
) {
  const form = reactive<Form>({ fee: 0, ...init });
  const navMissing = ref(false);
  const scope = effectScope();
  scope.run(() =>
    useSharesLinkage({
      navMissing,
      enabled,
      mode,
      fields: {
        amount: () => form.buy_amount,
        setAmount: value => {
          form.buy_amount = value;
        },
        shares: () => form.quantity,
        setShares: value => {
          form.quantity = value;
        },
        price: () => form.avg_price,
        fee: () => form.fee
      }
    })
  );
  return { form, navMissing, stop: () => scope.stop() };
}

describe("useSharesLinkage（对账补录字段名）", () => {
  it("先填净值再填金额 ⇒ 份额 = (金额 − 手续费) ÷ 净值", async () => {
    const s = setup({ avg_price: 1.5, fee: 1.5 });
    s.form.buy_amount = 1000;
    await nextTick();
    expect(s.form.quantity).toBe(665.6667);
    s.stop();
  });

  it("先填净值再填份额 ⇒ 金额 = 份额 × 净值 + 手续费", async () => {
    const s = setup({ avg_price: 7.35 });
    await nextTick();
    s.form.quantity = 500;
    await nextTick();
    expect(s.form.buy_amount).toBe(3675);
    s.stop();
  });

  it("改净值 ⇒ 按新净值重算份额（净值回填发生在金额之后也要联动）", async () => {
    const s = setup({ buy_amount: 1000 });
    await nextTick();
    s.form.avg_price = 2;
    await nextTick();
    expect(s.form.quantity).toBe(500);
    s.stop();
  });

  it("净值缺失（navMissing）时不联动：份额留给用户手填", async () => {
    const s = setup();
    s.navMissing.value = true;
    s.form.avg_price = 1.5;
    s.form.buy_amount = 1000;
    await nextTick();
    expect(s.form.quantity).toBeUndefined();
    s.stop();
  });

  it("enabled=false 时整块关掉（卖出 / SET 模式不许被买入联动改写）", async () => {
    const s = setup({ avg_price: 1.5 }, () => false);
    s.form.buy_amount = 1000;
    await nextTick();
    expect(s.form.quantity).toBeUndefined();
    // 用户手填的份额 / 成本价也不许被反算改写
    s.form.quantity = 300;
    await nextTick();
    expect(s.form.buy_amount).toBe(1000);
    s.stop();
  });

  it("净值缺失但价格有值时不除零：金额为 0 也不产出份额", async () => {
    const s = setup({ avg_price: 1.5 });
    s.form.buy_amount = 0;
    await nextTick();
    expect(s.form.quantity).toBeUndefined();
    s.stop();
  });
});

/**
 * trade 方向（2026-11-16）：股票 / ETF / 可转债的成交数量是主量，
 * 金额恒由「数量 × 成交价 + 手续费」派生，且**绝不**反算数量。
 *
 * 反面判据（回归网）：把 trade 方向的 1 / 3 号 watch 打开，下面第一条会立刻红
 * ——「填 5200 元 ⇒ 数量被改写成 999.7981 股」，正是后端 validate_buy 会拒的碎股。
 */
describe("useSharesLinkage（trade 方向：数量为主量）", () => {
  const trade = () => "trade" as const;

  it("填数量 ⇒ 金额 = 数量 × 价格 + 手续费（1000 × 5.20 + 1.05 = 5201.05）", async () => {
    const s = setup({ avg_price: 5.2, fee: 1.05 }, undefined, trade);
    s.form.quantity = 1000;
    await nextTick();
    expect(s.form.buy_amount).toBe(5201.05);
    expect(s.form.quantity).toBe(1000);
    s.stop();
  });

  it("改手续费 ⇒ 只重算金额，数量原样不动", async () => {
    const s = setup({ avg_price: 5.2, fee: 0 }, undefined, trade);
    s.form.quantity = 1000;
    await nextTick();
    expect(s.form.buy_amount).toBe(5200);

    s.form.fee = 5;
    await nextTick();
    expect(s.form.buy_amount).toBe(5205);
    expect(s.form.quantity).toBe(1000);
    s.stop();
  });

  it("改成交价格 ⇒ 只重算金额（打新中签价 5.20 → 7.35，数量不被改写）", async () => {
    const s = setup({ avg_price: 5.2, quantity: 1000 }, undefined, trade);
    await nextTick();
    s.form.avg_price = 7.35;
    await nextTick();
    expect(s.form.buy_amount).toBe(7350);
    expect(s.form.quantity).toBe(1000);
    s.stop();
  });

  it("金额被程序改写时不反算数量（金额是只读派生量）", async () => {
    const s = setup({ avg_price: 5.2, quantity: 1000 }, undefined, trade);
    await nextTick();
    s.form.buy_amount = 5200;
    await nextTick();
    expect(s.form.quantity).toBe(1000);
    s.stop();
  });

  it("清空数量 ⇒ 金额一并清空，不留上一次的残留值", async () => {
    const s = setup({ avg_price: 5.2 }, undefined, trade);
    s.form.quantity = 1000;
    await nextTick();
    expect(s.form.buy_amount).toBe(5200);

    s.form.quantity = undefined;
    await nextTick();
    expect(s.form.buy_amount).toBeUndefined();
    s.stop();
  });
});
