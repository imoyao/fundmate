import { nextTick, ref, watch, type Ref } from "vue";
import { amountFromShares, sharesFromAmount } from "@/utils/tradeAmountMath";

/** 联动读写的四个字段（用访问器而不是表单对象：各入口的字段名不同） */
export interface SharesLinkageFields {
  amount: () => number | undefined;
  setAmount: (value: number | undefined) => void;
  shares: () => number | undefined;
  setShares: (value: number | undefined) => void;
  price: () => number | undefined;
  fee: () => number | undefined;
}

/**
 * 买入金额 / 手续费 / 份额 / 净值（价格）的四者联动（#980 拆出，2026-11-15 泛化）。
 *
 * 三条 watch 的执行顺序不能乱：
 * 1. 金额变 → 算份额（净额 = 金额 − 手续费，再除净值）
 * 2. 份额变 → 反算金额（份额 × 净值 + 手续费）
 * 3. 金额 / 手续费 / 净值任一变 → 重算份额（覆盖「先填金额、后回填净值」的路径）
 *
 * `isUpdating` 是防循环锁：写份额时会把 1/3 里的写入再触发回 2，锁住直到 nextTick。
 * 净值缺失（navMissing）时一律不参与联动——无价可算，份额留给用户手填或留空。
 *
 * ## 为什么收访问器（而不是直接吃表单对象）
 *
 * 两个入口的字段名不同：记一笔是 `buyAmount / shares / price`（后端 `PositionCreate`
 * 契约），对账补录是 `quantity / avg_price`（`/reconciliation/adjustments/` 契约）。
 * 吃访问器就能共用同一份联动，不必为了「组件共用」去改任何一侧的载荷字段名——
 * 那是会静默写错库的改动，风险远大于收益。
 *
 * `enabled` 用于整块关掉联动（补录弹窗的「卖出 / 存入 / 取出」没有买入金额）。
 */
export function useSharesLinkage(deps: {
  fields: SharesLinkageFields;
  navMissing: Ref<boolean>;
  /** 关掉时三个 watcher 一律不再改写表单（默认恒开） */
  enabled?: () => boolean;
}) {
  const { fields, navMissing } = deps;
  // 是否正在更新（防死循环锁）
  const isUpdating = ref(false);

  const active = () =>
    !navMissing.value && (deps.enabled ? deps.enabled() : true);

  // 金额变化，联动计算份额
  watch(
    () => fields.amount(),
    newVal => {
      if (isUpdating.value || newVal === undefined) return;
      if (!active()) return; // 净值缺失 / 联动关闭：股份额留空或由用户手填
      const price = fields.price();
      if (!price || price <= 0) {
        fields.setShares(undefined);
        return;
      }
      isUpdating.value = true;
      fields.setShares(sharesFromAmount(newVal, price, fields.fee()));
      nextTick(() => {
        isUpdating.value = false;
      });
    }
  );

  // 份额变化，联动计算金额
  watch(
    () => fields.shares(),
    newVal => {
      if (isUpdating.value || newVal === undefined) return;
      if (!active()) return; // 净值缺失 / 联动关闭：无价可算
      const price = fields.price();
      if (!price || price <= 0) return;
      isUpdating.value = true;
      fields.setAmount(amountFromShares(newVal, price, fields.fee()));
      nextTick(() => {
        isUpdating.value = false;
      });
    }
  );

  // 统一监听【金额、手续费、净值（价格）】：三个值全了就立刻联动，绝不卡住
  watch(
    [() => fields.amount(), () => fields.fee(), () => fields.price()],
    ([amount, fee, price]) => {
      if (isUpdating.value || !active()) return;
      if (amount === undefined || amount <= 0 || !price || price <= 0) {
        if (fields.shares() !== undefined) fields.setShares(undefined);
        return;
      }
      isUpdating.value = true;
      const calculated = sharesFromAmount(amount, price, fee);
      if (fields.shares() !== calculated) {
        fields.setShares(calculated);
      }
      nextTick(() => {
        isUpdating.value = false;
      });
    }
  );

  return { isUpdating };
}
