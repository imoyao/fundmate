<!--
  LedgerTodayPnlMetric · 账户详情概览里的「当日收益」指标（D92）

  单独成组件有两个理由：
  1. 详情页概览 `LedgerDetailOverview.vue` 已 385 行，逼近 400 行门禁；
     插入一块完整模板会顶破阈值，故逻辑与样式随组件走，父页只留一行挂载。
  2. 「估 / 确认」徽标必须与首页、账户卡片同一实现，收在一处才不会分叉。

  口径：`/summary/today-pnl/?ledger_id=…` 的 `total_pnl`，只覆盖该账户里
  有当日估值口径的持仓（股票 / 基金）。银行理财、贵金属等无价资产不进这个数，
  显示 `—`；与「货基今日收益」是两套口径，并列展示但**不相加**，也不画 0。
-->
<template>
  <div class="flex flex-col">
    <span class="text-xs mb-1" :style="{ color: 'var(--text-tertiary-ink)' }"
      >当日收益</span
    >
    <span
      class="text-lg font-semibold"
      :style="{ color: 'var(--text-primary)' }"
    >
      <template v-if="data?.total_pnl != null">
        <!-- 中性色：这一排已有多个涨跌色数字，再添一个会互相抢注意力 -->
        <MoneyDisplay :value="data.total_pnl" size="md" :auto-color="false" />
        <ValuationSourceBadge
          v-if="data.status === 'estimated'"
          :status="data.status"
          size="sm"
          tip="当日价含基金收盘估值，官方净值公布后自动更新为确认值"
        />
      </template>
      <template v-else>—</template>
    </span>
  </div>
</template>

<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ValuationSourceBadge from "@/components/ValuationSourceBadge/index.vue";
import type { TodayPnlData } from "@/api/summary";

defineOptions({ name: "LedgerTodayPnlMetric" });
defineProps<{ data: TodayPnlData | null }>();
</script>
