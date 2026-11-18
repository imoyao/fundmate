<template>
  <!-- 买入数量（#980 拆自 BuyForm.vue）。
       标签/精度/步进/提示语全部来自 buyQuantityMeta（品种口径单一出口）：
       基金「确认份额」（2 位、金额为主量），股票/ETF/可转债「成交数量」
       （0 位、一手为步进、数量为主量）。此前两者共用「确认份额」，
       股票买入被迫按金额反算碎股（2026-11-16 用户反馈）。 -->
  <el-form-item v-if="meta.mode !== 'none'" :label="meta.label" prop="shares">
    <el-input-number
      v-model="sharesModel"
      style="width: 100%"
      class="w-full font-bold text-lg"
      :controls="false"
      :precision="meta.precision"
      :min="meta.min"
      :step="meta.step || undefined"
      :placeholder="meta.placeholder"
    />
    <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
      {{ meta.hint }}
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { buyQuantityMeta, type BuyQuantityMeta } from "../buyQuantityMeta";

const props = defineProps<{
  shares: number | undefined;
  /** 已选标的类型；未选标的时为空 */
  type?: string;
  /** 账户类型（未选标的时兜底口径） */
  ledgerType?: string;
  market?: string;
  symbol?: string;
}>();
const emit = defineEmits<{
  "update:shares": [value: number | undefined];
}>();

const sharesModel = computed({
  get: () => props.shares,
  set: val => emit("update:shares", val)
});

const meta = computed<BuyQuantityMeta>(() =>
  buyQuantityMeta({
    type: props.type,
    ledgerType: props.ledgerType,
    market: props.market,
    symbol: props.symbol
  })
);
</script>
