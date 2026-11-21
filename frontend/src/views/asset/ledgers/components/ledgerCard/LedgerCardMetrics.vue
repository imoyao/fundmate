<script setup lang="ts">
// 账户卡片的核心指标区：总资产（上方大数字锚点）+ 明细行（当日盈亏 / 持仓盈亏 /
// 累计盈亏，label 左、数值右）+ 关联负债页脚。
//
// 为什么从「左右两列 flex」改成「上一下三行」：
// 原布局左边一列只有总资产、右边一列 2~3 项，右列项数随账户类型浮动 ⇒ 银行账户
// 卡下半部留一大块空、投资账户卡又挤成三行小字，同一排卡片的重心各不相同。
// 改成纵向清单后，2 项与 3 项只差一行高度（网格 stretch 会拉齐），label 与数值
// 各自成列、跨卡片对齐，金额再长也只会把行撑宽，不会顶到旁边的指标。
//
// 多根片段（`div.ledger-metrics` + 条件渲染的 `div.ledger-liability`），不包 wrapper——
// 它们在 `.ledger-card` 里本来就是并列的直接子元素，包一层会让卡片内边距多作用一级。
import type { LedgerLike } from "../ledgerTypes";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ValuationSourceBadge from "@/components/ValuationSourceBadge/index.vue";
import type { TodayPnlGroup } from "@/api/summary";
import {
  hasLinkedLiability,
  pnlLabelOf,
  pnlMetricKindOf
} from "./ledgerCardModel";

defineProps<{
  ledger: LedgerLike;
  /** 当日估值（`dimension=ledger` 的分组行）；null = 该账户无可估值持仓 */
  todayPnl?: TodayPnlGroup | null;
}>();
</script>

<template>
  <div class="ledger-metrics">
    <div class="ledger-metrics__total">
      <span class="metric-label">总资产</span>
      <span class="metric-total">
        <MoneyDisplay
          :value="ledger.total_market_value || 0"
          :show-sign="false"
          :auto-color="false"
          size="lg"
        />
      </span>
    </div>

    <div class="ledger-metrics__rows">
      <!-- 当日盈亏：通用估值接口 `dimension=ledger` 按账户下发的分组行。
           pnl 为 null（无当日报价 / 该账户只有理财、贵金属等无估值口径资产）
           一律显示「—」，不画 0.00——0 会把「不知道」说成「今天没赚没亏」。 -->
      <div class="ledger-metric-row">
        <span class="metric-label">当日盈亏</span>
        <span class="metric-value">
          <template v-if="todayPnl?.pnl != null">
            <MoneyDisplay :value="todayPnl.pnl" size="sm" />
            <ValuationSourceBadge
              v-if="todayPnl.status === 'estimated'"
              :status="todayPnl.status"
              size="sm"
              tip="当日价含基金收盘估值，官方净值公布后自动更新为确认值"
            />
          </template>
          <span v-else class="metric-empty">—</span>
        </span>
      </div>

      <!-- 持仓盈亏：银行显示活期余额、实物显示估值项数 -->
      <div class="ledger-metric-row">
        <span class="metric-label">{{ pnlLabelOf(ledger.ledger_type) }}</span>
        <span
          v-if="pnlMetricKindOf(ledger) === 'cash'"
          class="metric-value metric-value--neutral"
        >
          <MoneyDisplay
            :value="ledger.cash_balance"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </span>
        <span
          v-else-if="pnlMetricKindOf(ledger) === 'count'"
          class="metric-value metric-value--neutral"
        >
          {{ ledger.position_count || 0 }} 项
        </span>
        <span v-else class="metric-value">
          <!-- 盈亏数字走 MoneyDisplay 自动涨红跌绿 -->
          <MoneyDisplay :value="ledger.pnl || 0" size="sm" />
        </span>
      </div>

      <!-- 累计盈亏（2026-11-10）：= 持仓浮盈 + 已实现 − 买入费。
           后端只对投资类账户下发，字段缺失（bank / property）即整项不渲染——
           写 0 会被读成「不赚不亏」，比不显示更误导。 -->
      <div
        v-if="ledger.total_pnl != null"
        class="ledger-metric-row"
        title="持仓浮盈 + 已实现 − 买入费"
      >
        <span class="metric-label">累计盈亏</span>
        <span class="metric-value">
          <MoneyDisplay :value="ledger.total_pnl" size="sm" />
        </span>
      </div>
    </div>
  </div>

  <!-- 关联负债（仅银行账户且存在房贷时显示；负债属中性信息，用 text-secondary） -->
  <div v-if="hasLinkedLiability(ledger)" class="ledger-liability">
    <span class="metric-label">关联负债</span>
    <span class="ledger-liability__value">
      <MoneyDisplay
        :value="-ledger.linked_liability"
        :auto-color="false"
        size="xs"
      />
    </span>
  </div>
</template>

<style scoped>
.ledger-metrics {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ledger-metrics__total {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.metric-total {
  display: block;
  line-height: 1.2;
}

/* 明细区：一条 --border-subtle 与上方总资产分开（卡片内降权分割线），
   行与行之间不再画线——三行短文本各画一道会读成表格。 */
.ledger-metrics__rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

.ledger-metric-row {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  min-width: 0;
}

.metric-label {
  display: block;
  flex: none;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}

.metric-value {
  display: flex;
  gap: 4px;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
  font-size: var(--text-small, 14px);
  font-variant-numeric: tabular-nums;
  line-height: 22px;
  white-space: nowrap;
}

/* 非盈亏口径的数值（活期余额 / 项数）用次要墨色：它们不是涨跌，不该染红绿 */
.metric-value--neutral {
  color: var(--text-secondary);
}

.metric-empty {
  color: var(--text-tertiary-ink);
}

/* 「估」徽标与数字同行：子组件根元素带父 scope，无需 :deep() */
.metric-value .val-src-badge {
  margin-left: 0;
}

.ledger-liability {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-2);
  margin-top: var(--space-3);
  font-variant-numeric: tabular-nums;
  border-top: 1px solid var(--border-subtle);
}

.ledger-liability__value {
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-secondary);
}
</style>
