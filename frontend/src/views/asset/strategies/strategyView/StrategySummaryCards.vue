<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";

/**
 * 顶部四张汇总卡：总持仓 / 标签数 / 总市值 / 总盈亏。
 *
 * 「总市值 / 总盈亏」取的是**原始持仓**（每只一份），不是分组结果——
 * 一只持仓可带多个标签、会同时出现在多个组里，用分组结果求和会重复计算。
 */
defineOptions({ name: "StrategySummaryCards" });

defineProps<{
  totalHoldings: number;
  tagCount: number;
  totalMarketValue: number;
  totalPnl: number;
}>();
</script>

<template>
  <div class="flex gap-4">
    <el-card shadow="never" class="summary-card">
      <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
        总持仓
      </p>
      <p
        class="text-xl font-bold"
        :style="{ color: 'var(--color-primary-ink)' }"
      >
        {{ totalHoldings }} 项
      </p>
    </el-card>
    <el-card shadow="never" class="summary-card">
      <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
        标签数
      </p>
      <p
        class="text-xl font-bold"
        :style="{ color: 'var(--color-primary-ink)' }"
      >
        {{ tagCount }} 个
      </p>
    </el-card>
    <el-card shadow="never" class="summary-card">
      <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
        总市值
      </p>
      <p
        class="text-xl font-bold"
        :style="{ color: 'var(--color-primary-ink)' }"
      >
        <MoneyDisplay
          :value="totalMarketValue"
          :show-sign="false"
          :auto-color="false"
        />
      </p>
    </el-card>
    <el-card shadow="never" class="summary-card">
      <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
        总盈亏
      </p>
      <p class="text-xl font-bold">
        <MoneyDisplay :value="totalPnl" />
      </p>
    </el-card>
  </div>
</template>

<style scoped>
/* 汇总卡片 */
.summary-card {
  min-width: 120px;
  padding: 8px 16px;
  border-radius: 12px;
}
</style>
