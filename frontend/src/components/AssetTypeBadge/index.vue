<template>
  <el-tag
    v-if="variant === 'tag'"
    size="small"
    class="asset-type-badge--tag"
    :style="tagStyle"
  >
    {{ displayLabel }}
  </el-tag>
  <span v-else class="asset-type-badge--light" :style="lightStyle">
    {{ displayLabel }}
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { LEDGER_TYPE_SHORT } from "@/constants";
import { getLedgerColor } from "@/utils/ledger";

const props = withDefaults(
  defineProps<{
    type: string;
    label?: string;
    variant?: "tag" | "light";
  }>(),
  {
    variant: "light"
  }
);

const displayLabel = computed(() => {
  if (props.label) return props.label;
  return LEDGER_TYPE_SHORT[props.type] || props.type;
});

const baseColor = computed(() => getLedgerColor(props.type));

/** 同色相透明底。
 *  ⚠️ #1602 修复：原实现是 `baseColor.value + "20"` 拼字符串 —— 当 getLedgerColor
 *  改为返回 `var(--x)` 后，拼出的是 `var(--x)20`，**不是合法 CSS 值**，整条
 *  backgroundColor 声明被浏览器静默丢弃（徽章背景一直是透明的，无人发现）。
 *  改用 color-mix 表达透明度，对 `var()` 与字面色值都成立。 */
const tint = (pct: number) =>
  `color-mix(in srgb, ${baseColor.value} ${pct}%, transparent)`;

// tag 模式：稍深一点的背景，更有存在感
const tagStyle = computed(() => ({
  backgroundColor: tint(12.5),
  color: baseColor.value,
  border: "none",
  lineHeight: "1.4"
}));

// light 模式：极浅背景，轻盈通透
const lightStyle = computed(() => ({
  backgroundColor: tint(9),
  color: baseColor.value,
  border: "none",
  lineHeight: "1.4"
}));
</script>

<style scoped>
/* 轻量模式（span） */
.asset-type-badge--light {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  padding: 1px 6px; /* 左右稍微多一点空间 */
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  border-radius: 8px; /* 更圆的胶囊 */
}

/* 标签模式（el-tag）保持 Element Plus 原生结构，仅调整内部样式 */
.asset-type-badge--tag {
  padding: 1px 6px !important;
  font-size: 12px;
  line-height: 1.4 !important;
  border-radius: 8px !important;
}
</style>
