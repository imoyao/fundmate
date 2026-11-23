<template>
  <!-- 买入金额（#2740 拆自 BuyForm.vue）。
       为什么要拆出来：投顾组合的提示语口径与普通买入不同（没有份额与净值），
       而 BuyForm.vue 已顶在 400 行页面上限（issue #980），文案分叉不该再往里加行。
       状态仍住父层——份额联动与提交都要读 form.buyAmount。

       `derived`（股票 / ETF / 可转债）：金额由「成交数量 × 成交价格 + 手续费」
       自动算出，输入框只读。让用户改金额就会反算出碎股（A 股须整手申报），
       见 buyQuantityMeta 的模块注释。 -->
  <el-form-item label="买入金额" :prop="fieldProp">
    <div class="flex flex-col w-full">
      <el-input-number
        v-model="amountModel"
        style="width: 100%"
        class="w-full"
        :controls="false"
        :precision="2"
        :min="0"
        :disabled="derived"
        :placeholder="derived ? '由成交数量自动计算' : '输入买入金额'"
      />
      <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
        {{ hint }}
      </div>
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";

/** 普通买入：金额含费、份额由系统算（与 useSharesLinkage 的 fund 方向一致） */
const NAV_AMOUNT_HINT = "买入金额将包含手续费，系统自动计算份额";
/** 投顾组合：只记金额（balance 模式，D70 / #2740）——它没有份额与净值，别让用户找输入框 */
const PORTFOLIO_AMOUNT_HINT =
  "投顾组合按「直接余额」记账：只记金额，没有份额与净值";
/** 银行理财：同为 balance 模式（D121 / #931）——登记编码即标的名，金额即市值 */
const BANK_WEALTH_AMOUNT_HINT =
  "银行理财按「直接余额」记账：只记金额，没有份额与净值";
/** 股票 / ETF / 可转债：金额是派生量（成交数量 × 成交价格 + 手续费） */
const DERIVED_AMOUNT_HINT =
  "金额 = 成交数量 × 成交价格 + 手续费，由数量自动算出";

const props = withDefaults(
  defineProps<{
    amount: number | undefined;
    /**
     * 「只记金额」的品类。两者文案不同，故传取值而不是布尔：
     * - `portfolio` 投顾组合（D70）
     * - `bank_wealth` 银行理财（D121）
     */
    balanceKind?: "portfolio" | "bank_wealth" | null;
    /**
     * el-form-item 的 `prop`（校验字段名）。默认 `buyAmount` 对记忆一笔的表单；
     * 对账补录弹窗的字段名是 `buy_amount`（与 `/adjustments/` 载荷同一套命名），
     * 传进来即可复用本组件，不必为「字段名不同」复制一份模板。
     */
    fieldProp?: string;
    /** 金额由数量派生（非基金）：输入框只读，改由数量驱动 */
    derived?: boolean;
  }>(),
  { fieldProp: "buyAmount", derived: false, balanceKind: null }
);
const emit = defineEmits<{
  "update:amount": [value: number | undefined];
}>();

const amountModel = computed({
  get: () => props.amount,
  set: val => emit("update:amount", val)
});

const hint = computed(() => {
  if (props.derived) return DERIVED_AMOUNT_HINT;
  if (props.balanceKind === "portfolio") return PORTFOLIO_AMOUNT_HINT;
  if (props.balanceKind === "bank_wealth") return BANK_WEALTH_AMOUNT_HINT;
  return NAV_AMOUNT_HINT;
});
</script>
