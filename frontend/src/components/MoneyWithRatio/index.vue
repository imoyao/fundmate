<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";

interface Props {
  /** 主数值（金额），单位：元 */
  value?: number | string | null;
  /** 辅比例（百分比数值，如 3.21 表示 +3.21%），为 null/undefined 时不展示比例行 */
  ratio?: number | string | null;
  /** 主金额是否带正负号，默认 true */
  showSign?: boolean;
  /** 主金额是否显示货币符号，默认 true */
  showCurrency?: boolean;
  /** 主金额字号，默认 md（明显大于比例，体现主次） */
  moneySize?: "sm" | "md" | "lg";
  /** 主金额是否按正负自动着色，默认 true */
  autoColor?: boolean;
  /** 比例是否显示正负号，默认 true */
  showRatioSign?: boolean;
  /** 比例小数位，默认 2 */
  ratioPrecision?: number;
  /** 比例后缀，默认 % */
  ratioSuffix?: string;
  /** 比例是否按正负自动着色，默认 true */
  ratioAutoColor?: boolean;
  /** 整体右对齐（表格列常用），默认 true */
  alignRight?: boolean;
  /** 主金额无数据时的占位，默认 -- */
  emptyText?: string;
}

const props = withDefaults(defineProps<Props>(), {
  value: null,
  ratio: null,
  showSign: true,
  showCurrency: true,
  moneySize: "md",
  autoColor: true,
  showRatioSign: true,
  ratioPrecision: 2,
  ratioSuffix: "%",
  ratioAutoColor: true,
  alignRight: true,
  emptyText: "--"
});
</script>

<template>
  <div class="money-with-ratio" :class="{ 'is-right': alignRight }">
    <MoneyDisplay
      :value="value"
      :show-sign="showSign"
      :show-currency="showCurrency"
      :size="moneySize"
      :auto-color="autoColor"
      :empty-text="emptyText"
    />
    <RiseFallText
      v-if="ratio !== null && ratio !== undefined && ratio !== ''"
      class="money-with-ratio__ratio"
      :value="ratio"
      :show-sign="showRatioSign"
      :precision="ratioPrecision"
      :suffix="ratioSuffix"
      :auto-color="ratioAutoColor"
      size="sm"
    />
  </div>
</template>

<style scoped>
.money-with-ratio {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.money-with-ratio.is-right {
  align-items: flex-end;
  text-align: right;
}

/* 比例为辅：明显小于主金额并弱化，形成主次之分 */
.money-with-ratio__ratio {
  margin-top: 2px;
  font-size: 12px;
  opacity: 0.72;
}
</style>
