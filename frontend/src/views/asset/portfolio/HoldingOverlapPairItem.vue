<template>
  <!--
    一对基金的重叠条目（从 HoldingOverlapPanel 拆出：单文件 649 行破了 400 行页面规模门禁）。
    两种形态共用一个组件而不是抄两遍模板：
      - primary：主列表，卡片底 + 彩色档位徽标 + 默认露前 5 只共同重仓股；
      - weak：弱提醒折叠区，压掉卡片底只留分隔线 + 描边徽标 + 默认收起明细。
  -->
  <li :class="['overlap-panel__pair', { 'overlap-panel__pair--weak': isWeak }]">
    <div class="overlap-panel__head">
      <span
        :class="[
          'overlap-panel__funds',
          { 'overlap-panel__funds--weak': isWeak }
        ]"
      >
        {{ pair.fund_name_a }}
        <span class="overlap-panel__vs">↔</span>
        {{ pair.fund_name_b }}
      </span>
      <span
        :class="[
          'overlap-panel__value',
          { 'overlap-panel__value--weak': isWeak }
        ]"
      >
        {{ formatWeightedOverlap(pair.weighted_overlap) }}
      </span>
    </div>

    <p v-if="isWeak" class="overlap-panel__verdict">
      <span class="overlap-panel__weak-badge">弱提醒</span>
      <span class="overlap-panel__reason">{{ describeWeakReason(pair) }}</span>
    </p>
    <p v-else-if="badge || pair.overlap_reason" class="overlap-panel__verdict">
      <!-- 中性档（同一基金份额）用描边徽标而不是 el-tag：EP 的 info 标签
           文字 #909399 在浅底上只有 2.8:1，过不了 AA；而彩色档位继续用
           el-tag——「要处置的」有颜色、「只是说明的」只有描边，层级正好 -->
      <span v-if="badge?.tone === 'info'" class="overlap-panel__neutral-badge">
        {{ badge.label }}
      </span>
      <el-tag v-else-if="badge" :type="badge.tone" size="small" effect="light">
        {{ badge.label }}
      </el-tag>
      <span v-if="pair.overlap_reason" class="overlap-panel__reason">
        {{ pair.overlap_reason }}
      </span>
    </p>

    <p class="overlap-panel__meta">
      集合口径 {{ formatJaccard(pair.jaccard) }} · 重复投入
      {{ formatAmountCents(pair.overlap_amount_cents) }} ·
      {{ describeBasis(pair.holding_basis) }}
      <el-button
        v-if="isWeak"
        text
        size="small"
        class="overlap-panel__detail-toggle"
        :aria-expanded="detailOpen"
        @click="detailOpen = !detailOpen"
      >
        {{ detailOpen ? "收起明细" : "查看明细" }}
      </el-button>
    </p>

    <template v-if="showStocks">
      <p v-if="describePeriodMismatch(pair)" class="overlap-panel__warn">
        {{ describePeriodMismatch(pair) }}
      </p>
      <ul class="overlap-panel__stocks">
        <li
          v-for="stock in visibleStocks"
          :key="stock.stock_code"
          class="overlap-panel__stock"
        >
          <span class="overlap-panel__stock-name">{{ stock.stock_name }}</span>
          <span class="overlap-panel__stock-ratio">
            {{ stock.ratio_a.toFixed(1) }}% / {{ stock.ratio_b.toFixed(1) }}%
          </span>
        </li>
        <li
          v-if="hiddenStockCount > 0"
          class="overlap-panel__stock overlap-panel__stock--more"
        >
          还有 {{ hiddenStockCount }} 只共同重仓股
        </li>
      </ul>
    </template>
  </li>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import {
  describeBasis,
  describeOverlapLevel,
  describePeriodMismatch,
  describeWeakReason,
  formatAmountCents,
  formatJaccard,
  formatWeightedOverlap
} from "./holdingOverlapModel";
import type { OverlapPair } from "./holdingOverlapModel";

const props = withDefaults(
  defineProps<{
    pair: OverlapPair;
    /** primary = 主列表卡片；weak = 弱提醒折叠区里的一行 */
    variant?: "primary" | "weak";
  }>(),
  { variant: "primary" }
);

/** 主列表最多露 5 只，弱提醒展开就全给——弱提醒的用户正是在核对细节 */
const PRIMARY_STOCK_LIMIT = 5;

const isWeak = computed(() => props.variant === "weak");
/** 弱提醒逐对展开（主列表常开，没有开关） */
const detailOpen = ref(false);

const badge = computed(() =>
  isWeak.value ? null : describeOverlapLevel(props.pair)
);

const showStocks = computed(() => !isWeak.value || detailOpen.value);
const visibleStocks = computed(() =>
  isWeak.value
    ? props.pair.common_holdings
    : props.pair.common_holdings.slice(0, PRIMARY_STOCK_LIMIT)
);
const hiddenStockCount = computed(() =>
  isWeak.value
    ? 0
    : Math.max(0, props.pair.common_holdings.length - PRIMARY_STOCK_LIMIT)
);
</script>

<style scoped lang="scss">
.overlap-panel {
  &__pair {
    padding: var(--space-standard);
    background: var(--bg-card);
    border: 1px solid var(--divider-default);
    border-radius: var(--radius-button);
  }

  &__head {
    display: flex;
    gap: var(--space-standard);
    align-items: baseline;
    justify-content: space-between;
  }

  &__funds {
    font-size: var(--text-body);
    color: var(--text-primary);
  }

  &__vs {
    margin: 0 4px;
    color: var(--text-tertiary-ink);
  }

  /* 文字级用 --color-danger-ink：暗底上 --color-danger 只有 3.36:1（axe 实测），
     -ink 是给文字用的那一档（亮 4.74 / 暗 4.9） */
  &__value {
    font-size: var(--text-body);
    font-variant-numeric: tabular-nums;
    color: var(--color-danger-ink);
  }

  &__verdict {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin: 6px 0 0;
  }

  &__reason {
    font-size: var(--text-small);
    color: var(--text-secondary);
  }

  &__meta {
    margin: 4px 0 0;
    font-size: var(--text-small);
    color: var(--text-tertiary-ink);
  }

  /* 文字级用 --color-warning-ink（白底 5.71）；--color-warning-fill 是底色级（3.57） */
  &__warn {
    margin: 4px 0 0;
    font-size: var(--text-small);
    line-height: 1.55;
    color: var(--color-warning-ink);
  }

  &__stocks {
    padding: 0;
    margin: 8px 0 0;
    list-style: none;
  }

  &__stock {
    display: flex;
    gap: var(--space-standard);
    justify-content: space-between;
    font-size: var(--text-small);
    color: var(--text-secondary);
  }

  &__stock-ratio {
    font-variant-numeric: tabular-nums;
  }

  &__stock--more {
    color: var(--text-tertiary-ink);
  }

  /* 弱提醒条目压一档：去掉卡片底与描边，只用分隔线 + 次要文字色——
     它已经在折叠区里，再套一层卡片就和「配置重复」一样重了 */
  &__pair--weak {
    padding: 10px 0;
    background: transparent;
    border: none;
    border-top: 1px solid var(--divider-default);
    border-radius: 0;
  }

  &__funds--weak {
    font-size: var(--text-small);
    color: var(--text-secondary);
  }

  &__value--weak {
    font-size: var(--text-small);
    color: var(--text-secondary);
  }

  /* 中性档自绘徽标：EP 的 info 标签文字 #909399 在浅底上只有 2.8～3.1:1（axe 实测），
     而它对 --el-tag-text-color 的层叠优先级高于组件样式，改不动。描边徽标既能过 AA，
     又天然比彩色 el-tag 轻一档。 */
  &__neutral-badge,
  &__weak-badge {
    display: inline-block;
    padding: 0 6px;
    font-size: var(--text-small);
    line-height: 1.6;
    color: var(--text-secondary);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
  }

  &__detail-toggle {
    margin-left: 4px;
    vertical-align: baseline;
  }
}
</style>
