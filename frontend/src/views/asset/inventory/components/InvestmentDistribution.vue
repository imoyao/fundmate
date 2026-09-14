<template>
  <div
    v-if="groups.length > 0"
    class="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4 mb-8 mt-4"
  >
    <div
      v-for="group in groups"
      :key="group.type"
      class="summary-card-item rounded-xl p-6 sm:p-8 transition-all"
      :style="{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-default)',
        boxShadow: 'var(--shadow-raised)'
      }"
    >
      <div class="flex items-center gap-3">
        <div
          class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
          :style="{ backgroundColor: getColorWithAlpha(group.color, 0.2) }"
        >
          <IconifyIconOffline
            :icon="group.icon"
            class="text-lg"
            :style="{ color: group.color }"
          />
        </div>
        <div>
          <p
            class="font-medium text-sm"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ group.label }}
          </p>
          <p class="text-xs mt-1" :style="{ color: 'var(--text-tertiary)' }">
            {{ group.count }} 项 ·<MoneyDisplay
              :value="group.total"
              :show-sign="false"
              :auto-color="false"
              size="xs"
            />
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 投资分布卡片网格（投资理财大类）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。分组口径（股票 + 可转债合并等）
 * 属业务规则，已在页面数据层 `buildInvestmentGroups` 收敛，本组件只负责渲染。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { getColorWithAlpha, type InvestmentGroup } from "../helpers";

defineProps<{
  /** 已按页面口径合并好的分组（空数组时不渲染） */
  groups: InvestmentGroup[];
}>();
</script>

<style scoped>
.summary-card-item {
  transition: all 0.2s ease;
}

.summary-card-item:hover {
  box-shadow: var(--shadow-float) !important;
  transform: translateY(-2px);
}

.summary-card-item:active {
  transform: scale(0.98);
}
</style>
