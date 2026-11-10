<script setup lang="ts">
// 累计盈亏指标（账户详情概览，2026-11-10）：= 持仓盈亏 + 已实现 − 买入费。
//
// 单独成组件不是因为「好看」，而是 `LedgerDetailOverview.vue` 已贴着 400 行硬闸
// （scripts/check_vue_size.mjs --mode fail），再塞这十几行会把整页判红。
//
// 渲染判据放在组件内部（`value == null` 即整格不出）：bank / property 后端不下发这个
// 字段，画成 0 元会被读成「真的不赚不亏」。调用方直接传可选值即可，不必先判空——
// 先判空再传值会让 vue-tsc 在可选链上做一次没必要的窄化博弈。
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";

defineProps<{
  /** 累计盈亏（元）；`null` / `undefined` = 该账户没有这个口径，整格不渲染 */
  value?: number | null;
}>();
</script>

<template>
  <div v-if="value != null" class="flex flex-col">
    <span class="text-xs mb-1" :style="{ color: 'var(--text-tertiary-ink)' }"
      >累计盈亏</span
    >
    <MoneyDisplay :value="value" size="lg" />
    <span class="text-xs mt-1" :style="{ color: 'var(--text-tertiary-ink)' }"
      >持仓浮盈 + 已实现 − 买入费</span
    >
  </div>
</template>
