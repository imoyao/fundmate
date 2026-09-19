<template>
  <div class="grid gap-4" :class="GRID_CLASS[columns]">
    <div
      v-for="item in items"
      :key="item.key"
      class="summary-card-item rounded-xl p-5 sm:p-6 cursor-pointer transition-all"
      :style="{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-default)',
        boxShadow: 'var(--shadow-raised)'
      }"
      @click="emit('select', item.key)"
    >
      <div class="flex items-center gap-3">
        <div
          class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
          :style="{ backgroundColor: getColorWithAlpha(item.color, 0.2) }"
        >
          <IconifyIconOffline
            :icon="item.icon"
            class="text-lg"
            :style="{ color: item.color }"
          />
        </div>
        <div>
          <p
            class="font-medium text-sm"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ item.label }}
          </p>
          <p
            v-if="item.desc"
            class="text-xs mt-1"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          >
            {{ item.desc }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 快捷操作入口卡片网格（投资理财 / 其他大类共用）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。两个场景的卡片结构一致，
 * 差异只在列数与是否带副文案，因此收敛为一个组件 + `items` / `columns` 入参；
 * 点击后的跳转 / 录入编排由页面决定（本组件只抛 `select`）。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import { getColorWithAlpha } from "../helpers";
import type { QuickActionItem } from "../constants";

withDefaults(
  defineProps<{
    /** 入口卡片列表 */
    items: QuickActionItem[];
    /** 栅格列数（投资理财 3 列，其他大类 4 列） */
    columns?: 3 | 4;
  }>(),
  { columns: 4 }
);

const emit = defineEmits<{
  /** 点击某个入口，回传其 key */
  select: [key: string];
}>();

/**
 * 栅格类名查表（完整字面量）。
 * Tailwind 靠静态扫描源码收集类名，动态拼接 `grid-cols-${n}` 不会被识别，故此处必须写全。
 */
const GRID_CLASS: Record<3 | 4, string> = {
  3: "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4"
};
</script>

<style scoped>
.summary-card-item {
  transition: all 0.2s ease;
}

/* !important 不可省：卡片根节点有内联 boxShadow（--shadow-raised），
   内联样式优先级高于普通规则，不加 !important 时 hover 阴影不生效（与 InvestmentDistribution 同） */
.summary-card-item:hover {
  box-shadow: var(--shadow-float) !important;
  transform: translateY(-2px);
}

.summary-card-item:active {
  transform: scale(0.98);
}
</style>
