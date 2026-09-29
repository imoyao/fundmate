<template>
  <!-- 账户信息头部 -->
  <div class="mb-6 flex items-center justify-between">
    <div>
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        {{ p.accountName }}
      </h2>
      <div class="flex items-center gap-2 mt-1">
        <el-tag size="small" type="info" round>{{ p.subTitle }}</el-tag>
        <template v-if="p.summaryData?.portfolio_name">
          <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
            · 组合: {{ p.summaryData.portfolio_name }}</span
          >
        </template>
      </div>
    </div>
  </div>

  <!-- 温柔提醒（#1133 §4）：中性信息色、拟人化、非阻断；可选「去对账/忽略」，绝不强制 -->
  <transition name="el-fade-in">
    <div
      v-if="p.visibleConsistencyItems.length > 0"
      class="soft-reconcile-banner"
      role="note"
    >
      <IconifyIconOffline
        icon="ep:info-filled"
        class="soft-reconcile-banner__icon"
      />
      <div class="soft-reconcile-banner__body">
        <p class="soft-reconcile-banner__title">
          这本账本的持仓快照截至
          {{
            p.visibleConsistencyItems[0].snapshot_date
          }}，快照日之后仍有交易记录；如与流水对不上，请去对账工作台核对是否需要补录。
        </p>
        <p class="soft-reconcile-banner__detail">
          共
          {{ p.visibleConsistencyItems.length }}
          笔持仓可能滞后，去对账工作台可统一核对。
        </p>
      </div>
      <div class="soft-reconcile-banner__actions">
        <el-button size="small" type="primary" plain @click="p.goReconcile">
          去对账
        </el-button>
        <el-button size="small" text @click="p.dismissAllConsistency">
          忽略
        </el-button>
      </div>
    </div>
  </transition>

  <!-- 账本概览（对齐「家庭资产看板」范式：SectionHeader + CardBlock，左指标 / 右资产构成） -->
  <SectionHeader title="账本概览" />
  <CardBlock class="mb-6">
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
      <!-- 左栏：核心指标（总资产 + 持仓盈亏 / 持仓与余额） -->
      <div
        :class="p.isCompositionLedger ? 'lg:col-span-7' : 'lg:col-span-12'"
        class="flex flex-col gap-5"
      >
        <!-- 总资产 -->
        <div>
          <p
            class="text-sm mb-2"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          >
            总资产
          </p>
          <div class="flex items-baseline gap-2">
            <MoneyDisplay
              :value="p.summaryData?.total_market_value || 0"
              size="hero"
              :show-sign="false"
            />
            <span
              class="text-xl font-medium"
              :style="{ color: 'var(--text-secondary)' }"
              >元</span
            >
          </div>
        </div>

        <!-- 持仓盈亏 + 持仓与余额 指标网格（分隔线对齐看板） -->
        <div
          class="grid grid-cols-2 gap-x-4 gap-y-5 pt-5"
          :style="{ borderTop: '1px solid var(--border-light)' }"
        >
          <!-- 持仓盈亏（涨红跌绿） -->
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >持仓盈亏</span
            >
            <MoneyDisplay :value="p.summaryData?.position_pnl || 0" size="lg" />
          </div>
          <!-- 持仓数量 -->
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >持仓数量</span
            >
            <span
              class="text-lg font-semibold"
              :style="{ color: 'var(--text-primary)' }"
              >{{ p.summaryData?.position_count || 0 }} 项</span
            >
          </div>
          <!-- 资金余额（中性余额，不随涨跌着色） -->
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >资金余额</span
            >
            <MoneyDisplay
              v-if="p.summaryData?.cash_balance != null"
              :value="p.summaryData.cash_balance"
              size="md"
              :show-sign="false"
              :auto-color="false"
            />
            <span
              v-else
              class="text-sm"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >--</span
            >
          </div>
          <!-- 关联负债（仅银行账户且有负债时展示） -->
          <div
            v-if="
              p.summaryData?.ledger_type === 'bank' &&
              p.summaryData?.linked_liability > 0
            "
            class="flex flex-col"
          >
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >关联负债</span
            >
            <MoneyDisplay
              :value="-p.summaryData.linked_liability"
              size="md"
              :auto-color="false"
              custom-color="var(--color-danger)"
            />
          </div>
          <!-- 货基收益（仅基金账户展示） -->
          <div
            v-if="p.summaryData?.ledger_type === 'fund'"
            class="flex flex-col"
          >
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >货基今日收益</span
            >
            <MoneyDisplay
              v-if="p.moneyFundData"
              :value="p.moneyFundData.today_income"
              size="md"
            />
            <span
              v-else
              class="text-sm"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >--</span
            >
          </div>
        </div>
      </div>

      <!-- 右栏：资产构成分布（仅股票 / 基金 / 信用账户，对齐看板饼图） -->
      <div
        v-if="p.isCompositionLedger"
        class="lg:col-span-5 flex flex-col items-center justify-center h-full"
        :style="{ borderLeft: '1px solid var(--border-light)' }"
      >
        <div class="w-full flex justify-between items-center mb-4">
          <span
            class="font-bold text-sm"
            :style="{ color: 'var(--text-secondary)' }"
            >资产构成分布</span
          >
        </div>
        <AssetAllocationDonut
          :data="p.compositionData"
          :color-map="p.compositionColorMap"
          :show-legend="true"
        />
      </div>
    </div>
  </CardBlock>

  <!-- 账户深度分析（规划中，敬请期待，详见内部工作记录 ledger-detail-info-redesign-plan-2026-08-27） -->
  <CardBlock class="mb-6">
    <div
      class="flex min-h-[160px] flex-1 items-center justify-center rounded-lg border border-dashed text-sm"
      :style="{
        borderColor: 'var(--border-subtle)',
        color: 'var(--text-tertiary-ink)'
      }"
    >
      账户深度分析（持仓集中度 / 行业分布 / 收益日历等）规划中，敬请期待
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import type { useLedgerDetailPage } from "../composables/useLedgerDetailPage";

defineOptions({ name: "LedgerDetailOverview" });

// #980 P1-C 拆分自 detail.vue：账户信息头 + 温柔提醒横幅 + 账本概览区。
// 状态单体经 page prop 注入，p. 前缀替换与拆分前的绑定表达式一一对应。
const props = defineProps<{ page: ReturnType<typeof useLedgerDetailPage> }>();
const p = reactive(props.page);
</script>

<style scoped>
/* 温柔提醒 banner（#1133 §4）：中性信息色，非涨跌色 / 非危险红；轻量、不制造心理压力 */
.soft-reconcile-banner {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: var(--space-3) var(--space-compact);
  margin-bottom: var(--space-compact);
  background: var(--bg-soft);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--el-color-info);
  border-radius: var(--radius-md);
}

.soft-reconcile-banner__icon {
  flex: none;
  margin-top: 2px;
  font-size: 18px;
  color: var(--el-color-info);
}

.soft-reconcile-banner__body {
  flex: 1;
  min-width: 0;
}

.soft-reconcile-banner__title {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-primary);
}

.soft-reconcile-banner__detail {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.soft-reconcile-banner__actions {
  display: flex;
  flex: none;
  gap: 8px;
  align-items: center;
}
</style>
