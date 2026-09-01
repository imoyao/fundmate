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
  /**
   * 内联单行模式：金额与比例同行展示（如 `¥109,600.00 +3.21%`）。
   * 用于数据密集表格（自选）：两行堆叠会让行内容达 ~35px、加单元格 padding 后约 51px，
   * 超出 design.md「数据表格强制紧凑原则」锁定的 40–44px；内联后行内容降至 20px，
   * 行高回落至 40px 基线，单屏可见行数翻倍（issue #1281）。
   * 默认 false（两行主次布局），保持非密集场景的阅读层次。
   */
  inline?: boolean;
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
  emptyText: "--",
  inline: false
});
</script>

<template>
  <div
    class="money-with-ratio"
    :class="{ 'is-right': alignRight, 'is-inline': inline }"
  >
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

/* ── 内联单行模式（数据密集表格，issue #1281）──
   金额与比例同行，行内容高度 20px（两行堆叠约 35px 会把行高顶到 ~51px，
   超出 design.md 锁定的 40–44px）。基线对齐保证两种字号的文本底部齐平；
   右对齐列改由 justify-content 收尾，避免与 baseline 冲突。 */
.money-with-ratio.is-inline {
  flex-direction: row;
  gap: 6px;
  align-items: baseline;
  line-height: 20px;
  white-space: nowrap;
}

.money-with-ratio.is-inline.is-right {
  align-items: baseline;
  justify-content: flex-end;
}

.money-with-ratio.is-inline .money-with-ratio__ratio {
  margin-top: 0;
}
</style>
