<template>
  <!-- 买入价格（#2990 拆自 BuyForm.vue）。
       拆出来的理由有两个：① BuyForm.vue 已顶在 400 行页面上限（issue #980），
       这个框连同注释会把它推过门槛；② 它与 BuyAmountField / BuyFeeField 同属
       「一个表单项 + 一句口径提示」，形态一致，留在父层反而破坏结构对称。

       这个框不是为了「多给一个输入」，而是唯一能让成交价与当日收盘价不同的入口：
       选中标的时 useBuySecuritySelection 会把当日收盘价回填进 form.price，
       而此前该值在界面上不可见、也不可改 —— 于是金额与份额被收盘价锁死，
       500 股必然等于 500×收盘价，打新中签价（发行价）根本填不进去。
       状态仍住父层——份额联动与提交都要读 form.price。 -->
  <el-form-item v-if="visible" :label="TRADE_FIELD_LABELS.price" prop="price">
    <el-input-number
      v-model="priceModel"
      style="width: 100%"
      class="w-full"
      :controls="false"
      :min="0"
      :step="0.01"
      :precision="2"
    />
    <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
      默认填入当日收盘价，可按实际成交价修改（打新中签请填中签价）
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { TRADE_FIELD_LABELS } from "@/constants";

const props = defineProps<{
  price: number | undefined;
  /** 已选标的的类型；未选标的时为 undefined */
  securityType?: string;
}>();
const emit = defineEmits<{
  "update:price": [value: number | undefined];
}>();

const priceModel = computed({
  get: () => props.price,
  set: val => emit("update:price", val)
});

// 可手填价格的品种：股票 / ETF / 可转债。基金的价格是净值（由 useBuyNavSync 回填，
// 手填会与净值回填互相覆盖）；投顾组合没有份额与价格概念（D70）。
// 未选标的不显示——与 showFeeField 同一模式，避免空表单多一个必填感字段。
const visible = computed(() => {
  const type = props.securityType;
  return Boolean(type) && type !== "fund" && type !== "portfolio";
});
</script>
