<template>
  <!--
    策略诊断卡（#2224 / #2225）：规则触发的客观状态 + 行为反推画像。
    纯展示，请求由页面数据层 `useStrategyInsight` 承担。
  -->
  <div class="diagnosis-card">
    <SectionHeader
      title="策略诊断"
      info="诊断由既定的规则对已有行情自动跑出，描述的是「哪条规则此刻成立」，不是操作建议。行为画像只统计你自己的历史交易。"
      info-label="策略诊断口径说明"
    />

    <CardBlock>
      <!-- 加载中 -->
      <p v-if="loading" class="diagnosis-card__hint" role="status">
        诊断信号加载中…
      </p>

      <!-- 失败态：不显示 0 / 空列表，避免被读成「没有信号」 -->
      <div v-else-if="error" class="diagnosis-card__error" role="alert">
        <span class="diagnosis-card__error-text">诊断信号加载失败</span>
        <el-button text size="small" @click="emit('retry')">重试</el-button>
      </div>

      <p v-else-if="!diagnosis?.items?.length" class="diagnosis-card__hint">
        还没有持仓，暂无可诊断的标的。
      </p>

      <template v-else>
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
              <span class="diagnosis-card__name">{{
                item.name || item.symbol
              }}</span>
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
                  {{ strategyName(signal.strategy_code) }}
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
                {{
                  formatNullable(profileOf(item.symbol)?.avg_hold_days, "天")
                }}
                · 追涨买入占比
                {{
                  formatNullable(profileOf(item.symbol)?.chase_buy_ratio, "%")
                }}
                · 提前卖出机会成本
                {{ formatSignedMoney(profileOf(item.symbol)?.early_exit_cost) }}
              </span>
            </p>
          </li>
        </ul>
      </template>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
/**
 * 策略诊断卡（#2224 / #2225）。
 *
 * 合规红线：后端 `contracts.py` 与 `allocation.py` 明确禁止「建议买入 / 建议卖出」措辞。
 * 本组件只做三件事——把 `strategy_code` 翻成策略名、把 `action` 翻成**状态词**
 * （买入区间 / 减仓区间 等，描述的是规则落在哪个区间，不是让人去做什么）、
 * 原样展示后端 `reason`。前端不补任何倾向性动词。
 *
 * `early_exit_cost` 可能为负（提前卖出反而躲过下跌），负数如实显示，
 * 绝不取绝对值或隐藏——那是用户行为里最有信息量的一半。
 */
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type {
  BehaviorData,
  BehaviorProfile,
  DiagnosisData,
  EngineStrategyMeta,
  SignalAction
} from "@/api/strategyEngine";

defineOptions({ name: "StrategyDiagnosisCard" });

const props = defineProps<{
  diagnosis: DiagnosisData | null;
  behavior: BehaviorData | null;
  /** `GET /api/strategy/engine/strategies/` 的列表，用于把 code 翻成策略名 */
  strategies?: EngineStrategyMeta[];
  loading?: boolean;
  error?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();

/** action → 中性状态词。描述「规则落在哪个区间」，不带任何祈使语气 */
const ACTION_LABELS: Record<SignalAction, string> = {
  buy: "买入区间",
  hold: "持有区间",
  reduce: "减仓区间",
  sell: "离场区间",
  watch: "观望"
};

function actionLabel(action: SignalAction): string {
  return ACTION_LABELS[action] || action;
}

/** 有元信息就显示策略名（人话），否则原样退回 code——不猜、不编 */
function strategyName(code: string): string {
  return props.strategies?.find(s => s.code === code)?.name || code;
}

const profileMap = computed<Record<string, BehaviorProfile>>(() => {
  const map: Record<string, BehaviorProfile> = {};
  for (const profile of props.behavior?.profiles ?? []) {
    map[profile.symbol] = profile;
  }
  return map;
});

function profileOf(symbol: string): BehaviorProfile | undefined {
  return profileMap.value[symbol];
}

/** 可为 null 的指标：null = 数据不足，显示「—」而不是 0 */
function formatNullable(
  value: number | null | undefined,
  unit: string
): string {
  return value === null || value === undefined ? "—" : `${round(value)}${unit}`;
}

/**
 * 机会成本（元）：**带符号**。
 * 正 = 提前卖出少赚的；负 = 提前卖出反而躲过下跌——负数必须原样显示。
 */
function formatSignedMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${round(value)} 元`;
}

/** 最多两位小数、去掉尾零 */
function round(value: number): number {
  return Number(value.toFixed(2));
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.diagnosis-card {
  display: flex;
  flex-direction: column;

  &__hint,
  &__insufficient,
  &__behavior-meta,
  &__overview-meta {
    margin: 0;
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-tertiary-ink);
  }

  &__error {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }

  &__error-text {
    font-size: 13px;
    color: var(--text-secondary);
  }

  /* 行为总览：一条浅底横条，把「你实际在怎么做」与下面的逐标的事实分开 */
  &__overview {
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

  &__overview-label {
    font-size: 12px;
    color: var(--text-tertiary-ink);
  }

  &__overview-value {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-height: 320px;
    padding: 0;
    margin: 0;
    overflow-y: auto;
    list-style: none;
  }

  &__item {
    padding-bottom: var(--space-3);
    border-bottom: 1px solid var(--border-light);

    &:last-child {
      padding-bottom: 0;
      border-bottom: none;
    }
  }

  &__head {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }

  &__name {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__symbol {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-tertiary-ink);
  }

  &__signals {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: 0;
    margin: var(--space-2) 0 0;
    list-style: none;
  }

  &__signal {
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

  &__strategy {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-secondary);
  }

  /* 后端保证 reason 是客观陈述，这里只负责排版（不截断、不加前缀） */
  &__reason {
    flex: 1 1 100%;
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-tertiary-ink);
  }

  &__behavior {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: baseline;
    margin: var(--space-2) 0 0;
  }

  &__behavior-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--brand-ink);
  }

  /* 状态胶囊：中性底色 + 文字级语义色，靠色相区分「落在哪个区间」
     ——刻意不用涨跌红绿，避免被读成盈亏 */
  &__pill {
    padding: 0 var(--space-2);
    font-size: 11px;
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

  /* 窄屏适配已并入 &__overview / &__signal 内部（媒体查询必须贴着它覆盖的
     规则放：同特异性下源序即优先级，见 stylelint.config.js 的 order/order 注释） */
}
</style>
