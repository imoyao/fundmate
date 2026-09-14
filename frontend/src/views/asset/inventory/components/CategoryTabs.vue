<template>
  <div class="grid grid-cols-3 md:grid-cols-6 gap-4 mb-8">
    <div
      v-for="cat in categories"
      :key="cat.key"
      class="category-tab"
      :class="{ active: active === cat.key }"
      :style="tabStyle(cat)"
      @click="emit('update:active', cat.key)"
    >
      <span class="category-tab-label">{{ cat.label }}</span>
      <span class="category-tab-amount">
        <template v-if="Math.abs(totalOf(cat.key)) > 0">
          <MoneyDisplay
            :value="totalOf(cat.key)"
            :show-sign="true"
            :show-currency="true"
            size="sm"
          />
        </template>
        <span v-else class="text-sm" :style="{ color: 'var(--text-tertiary)' }">
          无记录
        </span>
      </span>
      <span v-if="active === cat.key" class="category-tab-arrow">
        <IconifyIconOffline icon="ep:caret-bottom" />
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 资产大类标签栏（全面盘点页顶部）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。纯展示 + 切换事件，
 * 金额口径由页面数据层通过 `totalOf` 注入（本组件不感知汇总来源）。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import type { InventoryCategory } from "../constants";

const props = defineProps<{
  /** 大类目录（顺序即展示顺序） */
  categories: InventoryCategory[];
  /** 当前选中大类 key */
  active: string;
  /** 大类 key → 该大类金额 */
  totalOf: (key: string) => number;
}>();

const emit = defineEmits<{
  "update:active": [key: string];
}>();

/** 选中态取该大类的语义配色变量（未选中不注入任何内联样式） */
function tabStyle(cat: InventoryCategory) {
  if (props.active !== cat.key) return {};
  return {
    backgroundColor: `var(${cat.bgVar})`,
    borderColor: `var(${cat.borderVar})`,
    boxShadow: "var(--shadow-raised)"
  };
}
</script>

<style scoped>
/* 分类标签栏：标准圆角，非胶囊 */
.category-tab {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  min-height: 80px;
  padding: 14px 16px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-raised);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.category-tab:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-2px);
}

.category-tab.active {
  border-width: 2px;
}

.category-tab-label {
  font-size: 14px;
  color: inherit;
}

.category-tab-amount {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.category-tab-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
  font-size: 16px;
  color: var(--text-tertiary);
}
</style>
