/**
 * 买入「价格 / 金额 / 份额 / 手续费」四者联动口径。
 *
 * 为什么单独立测：买入价格框放开手填（打新中签、补录历史成交）之后，
 * 「改价 ⇒ 份额重算」成为一条用户真会走的路径。此前价格框不可见、不可改，
 * 这条 watch 从未在真实交互里被走到过，也就没被任何测试钉住。
 *
 * 打新的算术前提是恒等式「金额 = 份额 × 价格」（无手续费），所以下面用
 * 7.35 × 500 = 3675 这组真实形态的数字正反各验一次：
 * 任何一侧被联动改错，另一侧立刻露馅。
 */
import { describe, it, expect } from "vitest";
import { effectScope, nextTick, reactive, ref } from "vue";
import { useBuySharesLinkage } from "../useBuySharesLinkage";

function setup(init: {
  price?: number;
  buyAmount?: number;
  shares?: number;
  fee?: number;
}) {
  const form = reactive({
    price: init.price,
    buyAmount: init.buyAmount,
    shares: init.shares,
    fee: init.fee ?? 0
  });
  const navMissing = ref(false);
  // watch 在组件实例外注册需要独立作用域，否则跨用例串味（同一 tick 里互相触发）
  const scope = effectScope();
  scope.run(() => useBuySharesLinkage({ form, navMissing }));
  return { form, navMissing, stop: () => scope.stop() };
}

describe("useBuySharesLinkage", () => {
  it("填价格再填份额 ⇒ 金额 = 份额 × 价格（打新中签 500 股 @7.35 = 3675）", async () => {
    const s = setup({});
    s.form.price = 7.35;
    await nextTick();
    s.form.shares = 500;
    await nextTick();
    expect(s.form.buyAmount).toBe(3675);
    s.stop();
  });

  it("填价格再填金额 ⇒ 份额 = 金额 ÷ 价格（3675 ÷ 7.35 = 500）", async () => {
    const s = setup({});
    s.form.price = 7.35;
    await nextTick();
    s.form.buyAmount = 3675;
    await nextTick();
    expect(s.form.shares).toBe(500);
    s.stop();
  });

  it("改价格 ⇒ 按新价重算份额（收盘价 15 换成中签价 7.35，245 股变 500 股）", async () => {
    // 还原真实交互：选股回填收盘价 15 → 用户填缴款金额 3675 → 份额 245
    const s = setup({ price: 15 });
    await nextTick();
    s.form.buyAmount = 3675;
    await nextTick();
    expect(s.form.shares).toBe(245);

    // 用户在新增的价格框里改成中签价
    s.form.price = 7.35;
    await nextTick();
    expect(s.form.shares).toBe(500);
    s.stop();
  });

  it("手续费从金额里净扣后重算份额（3675 含 5 元费 ⇒ 份额变少）", async () => {
    // 金额是用户输入的主量（含费），改手续费只让净额与份额变，不反向改金额——
    // 这是既有口径，与「份额 × 价格 + 手续费」的互逆式不同，故在此显式钉住。
    const s = setup({ price: 7.35 });
    await nextTick();
    s.form.buyAmount = 3675;
    await nextTick();
    expect(s.form.shares).toBe(500);

    s.form.fee = 5;
    await nextTick();
    // (3675 - 5) / 7.35 = 499.3197...
    expect(s.form.shares).toBe(499.3197);
    expect(s.form.buyAmount).toBe(3675);
    s.stop();
  });

  it("净值缺失时不联动：价格与份额都留给用户手填，不被系统改写", async () => {
    const s = setup({});
    s.navMissing.value = true;
    s.form.price = 1.2345;
    s.form.buyAmount = 1000;
    await nextTick();
    expect(s.form.shares).toBeUndefined();
    s.stop();
  });

  it("价格为 0 / 空时不联动，避免除零算出 Infinity", async () => {
    const s = setup({});
    s.form.price = 0;
    await nextTick();
    s.form.buyAmount = 3675;
    await nextTick();
    expect(s.form.shares).toBeUndefined();
    s.stop();
  });
});
