import { nextTick, ref, watch, type Ref } from "vue";

interface SharesLinkageForm {
  buyAmount: number | undefined;
  shares: number | undefined;
  fee: number | undefined;
  price: number | undefined;
}

/**
 * 买入金额 / 手续费 / 份额 / 净值的双向联动（历史最易回归的一块，单独成模块 + 单测）。
 *
 * 三条 watch 的执行顺序不能乱：
 * 1. 金额变 → 算份额（净额 = 金额 − 手续费，再除净值）
 * 2. 份额变 → 反算金额（份额 × 净值 + 手续费）
 * 3. 金额 / 手续费 / 净值任一变 → 重算份额（覆盖「先填金额、后回填净值」的路径）
 *
 * `isUpdating` 是防循环锁：写份额时会把 1/3 里的写入再触发回 2，锁住直到 nextTick。
 * 净值缺失（navMissing）时一律不参与联动——无价可算，份额留给用户手填或留空。
 */
export function useBuySharesLinkage(deps: {
  form: SharesLinkageForm;
  navMissing: Ref<boolean>;
}) {
  const { form, navMissing } = deps;
  // 是否正在更新（防死循环锁）
  const isUpdating = ref(false);

  // 金额变化，联动计算份额
  watch(
    () => form.buyAmount,
    newVal => {
      if (isUpdating.value || newVal === undefined) return;
      if (navMissing.value) return; // 净值缺失：无价可算，份额留空或由用户手填
      if (!form.price || form.price <= 0) {
        form.shares = undefined;
        return;
      }
      isUpdating.value = true;
      const fee = form.fee || 0;
      form.shares = parseFloat(((newVal - fee) / form.price).toFixed(4));
      nextTick(() => {
        isUpdating.value = false;
      });
    }
  );

  // 份额变化，联动计算金额
  watch(
    () => form.shares,
    newVal => {
      if (isUpdating.value || newVal === undefined) return;
      if (navMissing.value) return; // 净值缺失：无价可算
      if (!form.price || form.price <= 0) return;
      isUpdating.value = true;
      const fee = form.fee || 0;
      form.buyAmount = parseFloat((newVal * form.price + fee).toFixed(2));
      nextTick(() => {
        isUpdating.value = false;
      });
    }
  );

  // 统一监听【买入金额、手续费、基金净值】：三个值全了就立刻联动，绝不卡住
  watch(
    [() => form.buyAmount, () => form.fee, () => form.price],
    ([newBuy, newFee, newPrice]) => {
      if (isUpdating.value || navMissing.value) return;
      if (newBuy === undefined || newBuy <= 0 || !newPrice || newPrice <= 0) {
        if (form.shares !== undefined) form.shares = undefined;
        return;
      }
      isUpdating.value = true;
      const fee = newFee || 0;
      const calculated = parseFloat(((newBuy - fee) / newPrice).toFixed(4));
      if (form.shares !== calculated) {
        form.shares = calculated;
      }
      nextTick(() => {
        isUpdating.value = false;
      });
    }
  );

  return { isUpdating };
}
