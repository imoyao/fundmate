<template>
  <!-- 行为反推总览：先给一句「你实际在怎么做」，再看逐标的细节 -->
  <div
    v-if="behavior?.summary?.symbol_count > 0"
    class="diagnosis-card__overview"
  >
    <span class="diagnosis-card__overview-label">实际行为</span>
    <span class="diagnosis-card__overview-value">{{
      behavior.summary.dominant_label
    }}</span>
    <span class="diagnosis-card__overview-meta">
      平均持有 {{ formatNullable(behavior.summary.avg_hold_days, "天") }}
      · 追涨买入占比
      {{ formatNullable(behavior.summary.avg_chase_buy_ratio, "%") }}
      · 提前卖出机会成本
      {{ formatSignedMoney(behavior.summary.total_early_exit_cost) }}
    </span>
  </div>

  <ul class="diagnosis-card__list">
    <li
      v-for="item in diagnosis.items"
      :key="item.symbol"
      class="diagnosis-card__item"
    >
      <div class="diagnosis-card__head">
        <span class="diagnosis-card__name">{{ item.name || item.symbol }}</span>
        <span class="diagnosis-card__symbol">{{ item.symbol }}</span>
        <!-- 样本不足要明示，而不是显示一串 0（#2224：数据不足 → WATCH 而非硬算） -->
        <span
          v-if="!item.data_sufficient"
          class="diagnosis-card__pill diagnosis-card__pill--insufficient"
          >样本不足</span
        >
      </div>

      <ul
        v-if="item.data_sufficient && item.signals.length > 0"
        class="diagnosis-card__signals"
      >
        <li
          v-for="signal in item.signals"
          :key="signal.strategy_code"
          class="diagnosis-card__signal"
        >
          <span class="diagnosis-card__strategy">
            {{ strategyName(strategies, signal.strategy_code) }}
          </span>
          <span
            class="diagnosis-card__pill"
            :class="`diagnosis-card__pill--${signal.action}`"
            >{{ actionLabel(signal.action) }}</span
          >
          <span class="diagnosis-card__reason">{{ signal.reason }}</span>
        </li>
      </ul>
      <p v-else class="diagnosis-card__insufficient">
        行情样本不足（{{ item.sample_size }} 个数据点），暂不给结论。
      </p>

      <!-- 行为反推：只陈述用户自己的历史事实 -->
      <p v-if="profileOf(item.symbol)" class="diagnosis-card__behavior">
        <span class="diagnosis-card__behavior-label">
          {{ profileOf(item.symbol)?.classified_label }}
        </span>
        <span class="diagnosis-card__behavior-meta">
          {{ profileOf(item.symbol)?.trade_count }} 笔交易 · 平均持有
          {{ formatNullable(profileOf(item.symbol)?.avg_hold_days, "天") }}
          · 追涨买入占比
          {{ formatNullable(profileOf(item.symbol)?.chase_buy_ratio, "%") }}
          · 提前卖出机会成本
          {{ formatSignedMoney(profileOf(item.symbol)?.early_exit_cost) }}
        </span>
      </p>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type {
  BehaviorData,
  BehaviorProfile,
  DiagnosisData,
  EngineStrategyMeta
} from "@/api/strategyEngine";
import {
  actionLabel,
  buildProfileMap,
  formatNullable,
  formatSignedMoney,
  strategyName
} from "./diagnosisModel";

/**
 * 策略诊断卡的信号列表与行为总览（#980 拆分自 `StrategyDiagnosisCard.vue`）。
 *
 * 只渲染「后端说的事实」：策略名、区间状态词、reason、样本量与行为画像。
 * 这里不构造任何倾向性措辞，也不对 null 值做 0 兜底（null = 数据不足，显示「—」）。
 */
defineOptions({ name: "DiagnosisSignalList" });

const props = withDefaults(
  defineProps<{
    diagnosis?: DiagnosisData | null;
    behavior?: BehaviorData | null;
    /** `GET /api/strategy/engine/strategies/` 的列表，用于把 code 翻成策略名 */
    strategies?: EngineStrategyMeta[];
  }>(),
  { diagnosis: null, behavior: null, strategies: () => [] }
);

const profileMap = computed(() => buildProfileMap(props.behavior ?? null));

function profileOf(symbol: string): BehaviorProfile | undefined {
  return profileMap.value[symbol];
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 逐标的事实块的次级文本：与总览横条共用同一套层级 */
.diagnosis-card__insufficient,
.diagnosis-card__behavior-meta,
.diagnosis-card__overview-meta {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

/* 行为总览：一条浅底横条，把「你实际在怎么做」与下面的逐标的事实分开 */
.diagnosis-card__overview {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-3);
  background: var(--bg-soft);
  border-radius: var(--radius-sm);

  /* 窄屏：逐标的的事实块改竖排，reason 独占一行后不再折行挤压。
     媒体查询贴着被它覆盖的规则放（同特异性下源序即优先级） */
  @include bp.below("md") {
    flex-direction: column;
    gap: var(--space-1);
  }
}

.diagnosis-card__overview-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.diagnosis-card__overview-value {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.diagnosis-card__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-height: 320px;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  list-style: none;
}

.diagnosis-card__item {
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-light);

  &:last-child {
    padding-bottom: 0;
    border-bottom: none;
  }
}

.diagnosis-card__head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.diagnosis-card__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.diagnosis-card__symbol {
  font-family: var(--font-mono);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.diagnosis-card__signals {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: 0;
  margin: var(--space-2) 0 0;
  list-style: none;
}

.diagnosis-card__signal {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;

  /* 窄屏：策略名 / 状态胶囊 / reason 之间的间距收紧。
     媒体查询贴着被它覆盖的规则放（同特异性下源序即优先级） */
  @include bp.below("md") {
    gap: var(--space-1);
  }
}

.diagnosis-card__strategy {
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-secondary);
}

/* 后端保证 reason 是客观陈述，这里只负责排版（不截断、不加前缀） */
.diagnosis-card__reason {
  flex: 1 1 100%;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.diagnosis-card__behavior {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  margin: var(--space-2) 0 0;
}

.diagnosis-card__behavior-label {
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--brand-ink);
}

/* 状态胶囊：中性底色 + 文字级语义色，靠色相区分「落在哪个区间」
   ——刻意不用涨跌红绿，避免被读成盈亏 */
.diagnosis-card__pill {
  padding: 0 var(--space-2);
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-secondary);
  background: var(--bg-muted);
  border-radius: var(--radius-pill);

  &--buy {
    color: var(--color-info-ink);
    background: var(--color-primary-20);
  }

  &--hold {
    color: var(--text-secondary);
    background: var(--bg-muted);
  }

  &--reduce {
    color: var(--color-warning-ink);
    background: var(--color-warning-20);
  }

  &--sell {
    color: var(--color-danger-ink);
    background: var(--color-danger-20);
  }

  &--watch {
    color: var(--text-tertiary-ink);
    background: var(--bg-soft);
  }

  /* 样本不足：与「观望」区分开——前者是数据问题，后者是规则结论 */
  &--insufficient {
    color: var(--text-tertiary-ink);
    background: var(--bg-soft);
  }
}
</style>
