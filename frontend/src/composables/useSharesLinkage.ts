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
 * 联动方向：
 * - `fund`（默认，基金）：金额是主量 —— 申购时净值未知，只能是「填金额 → 算份额」；
 *   四条 watch 里份额也仍可反算金额（官方确认份额可能不同，用户会手改）。
 * - `trade`（股票 / ETF / 可转债）：数量是主量 —— 金额恒为
 *   `数量 × 成交价 + 手续费`，表格里金额由数量派生且只读。
 *   反向（金额 → 份额）必须关掉：A 股买入须整手，按金额除价格会算出碎股，
 *   后端 `validate_buy` 会拒绝（2026-11-16 用户报「股票买入怎么按份额算」）。
 */
export type SharesLinkageMode = "fund" | "trade";

/**
 * 买入金额 / 手续费 / 份额 / 净值（价格）的联动（#980 拆出，2026-11-15 泛化）。
 *
 * ## fund 模式的三条 watch，执行顺序不能乱
 * 1. 金额变 → 算份额（净额 = 金额 − 手续费，再除净值）
 * 2. 份额变 → 反算金额（份额 × 净值 + 手续费）
 * 3. 金额 / 手续费 / 净值任一变 → 重算份额（覆盖「先填金额、后回填净值」的路径）
 *
 * ## trade 模式的额外一条
 * 4. 份额 / 净值（价格）/ 手续费任一变 → 重算金额；1 与 3 跳过，
 *    否则金额一变就把用户刚敲的数量改写成碎股。
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
  /** 关掉时所有 watcher 一律不再改写表单（默认恒开） */
  enabled?: () => boolean;
  /** 联动方向（默认 fund）；用 getter 是为了品种切换后同一实例生效 */
  mode?: () => SharesLinkageMode;
}) {
  const { fields, navMissing } = deps;
  // 是否正在更新（防死循环锁）
  const isUpdating = ref(false);

  const active = () =>
    !navMissing.value && (deps.enabled ? deps.enabled() : true);
  const mode = () => deps.mode?.() ?? "fund";

  // 金额变化，联动计算份额（仅 fund 模式：trade 模式金额是派生量，不可反算）
  watch(
    () => fields.amount(),
    newVal => {
      if (isUpdating.value || newVal === undefined) return;
      if (!active()) return; // 净值缺失 / 联动关闭：股份额留空或由用户手填
      if (mode() === "trade") return;
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
      if (mode() === "trade") return;
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

  // trade 模式：数量 / 价格 / 手续费 → 金额（金额是派生量，改了它也不反算数量）
  watch(
    [() => fields.shares(), () => fields.price(), () => fields.fee()],
    ([shares, price, fee]) => {
      if (isUpdating.value || !active()) return;
      if (mode() !== "trade") return;
      if (shares === undefined || shares <= 0 || !price || price <= 0) {
        if (fields.amount() !== undefined) fields.setAmount(undefined);
        return;
      }
      isUpdating.value = true;
      const calculated = amountFromShares(shares, price, fee);
      if (fields.amount() !== calculated) fields.setAmount(calculated);
      nextTick(() => {
        isUpdating.value = false;
      });
    }
  );

  return { isUpdating };
}
