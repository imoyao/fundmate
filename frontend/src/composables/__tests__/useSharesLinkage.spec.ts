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

function setup(init: Form = {}, enabled = () => true) {
  const form = reactive<Form>({ fee: 0, ...init });
  const navMissing = ref(false);
  const scope = effectScope();
  scope.run(() =>
    useSharesLinkage({
      navMissing,
      enabled,
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
