<template>
  <!-- 买入金额（#2740 拆自 BuyForm.vue）。
       为什么要拆出来：投顾组合的提示语口径与普通买入不同（没有份额与净值），
       而 BuyForm.vue 已顶在 400 行页面上限（issue #980），文案分叉不该再往里加行。
       状态仍住父层——份额联动与提交都要读 form.buyAmount。 -->
  <el-form-item label="买入金额" :prop="fieldProp">
    <div class="flex flex-col w-full">
      <el-input-number
        v-model="amountModel"
        style="width: 100%"
        class="w-full"
        :controls="false"
        :precision="2"
        :min="0"
        placeholder="输入买入金额"
      />
      <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
        {{ isPortfolio ? PORTFOLIO_AMOUNT_HINT : NAV_AMOUNT_HINT }}
      </div>
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";

/** 普通买入：金额含费、份额由系统算（与 useBuySharesLinkage 的实际行为一致） */
const NAV_AMOUNT_HINT = "买入金额将包含手续费，系统自动计算份额";
/** 投顾组合：只记金额（balance 模式，D70 / #2740）——它没有份额与净值，别让用户找输入框 */
const PORTFOLIO_AMOUNT_HINT =
  "投顾组合按「直接余额」记账：只记金额，没有份额与净值";

const props = withDefaults(
  defineProps<{
    amount: number | undefined;
    /** 选中标的是否为投顾组合（type === 'portfolio'） */
    isPortfolio: boolean;
    /**
     * el-form-item 的 `prop`（校验字段名）。默认 `buyAmount` 对记忆一笔的表单；
     * 对账补录弹窗的字段名是 `buy_amount`（与 `/adjustments/` 载荷同一套命名），
     * 传进来即可复用本组件，不必为「字段名不同」复制一份模板。
     */
    fieldProp?: string;
  }>(),
  { fieldProp: "buyAmount" }
);
const emit = defineEmits<{
  "update:amount": [value: number | undefined];
}>();

const amountModel = computed({
  get: () => props.amount,
  set: val => emit("update:amount", val)
});
</script>
