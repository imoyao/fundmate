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

// tag 模式：稍深一点的背景，更有存在感
const tagStyle = computed(() => ({
  backgroundColor: baseColor.value + "20", // 约 12.5% 透明度
  color: baseColor.value,
  border: "none",
  lineHeight: "1.4"
}));

// light 模式：极浅背景，轻盈通透
const lightStyle = computed(() => ({
  backgroundColor: baseColor.value + "18", // 约 9% 透明度
  color: baseColor.value,
  border: "none",
  lineHeight: "1.4"
}));
</script>

<style scoped>
/* 轻量模式（span） */
.asset-type-badge--light {
  font-size: 12px;
  padding: 1px 6px; /* 左右稍微多一点空间 */
  border-radius: 8px; /* 更圆的胶囊 */
  white-space: nowrap;
  font-weight: 500;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* 标签模式（el-tag）保持 Element Plus 原生结构，仅调整内部样式 */
.asset-type-badge--tag {
  font-size: 12px;
  padding: 1px 6px !important;
  border-radius: 8px !important;
  line-height: 1.4 !important;
}
</style>
