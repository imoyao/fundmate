<template>
  <!--
    组合内基金持仓重叠度（#2604）：两只基金重仓同一批股票 = 看着分散、实际同涨同跌。
    与「持仓穿透」的分工：穿透看「钱压在哪些行业/个股」，本面板看「我的基金之间有多重合」。
  -->
  <div class="overlap-panel">
    <SectionHeader
      title="持仓重叠度"
      info="按季报/半年报披露的重仓股，比较组合内两只基金的重合程度。加权口径按共同持仓的较小占净值比例求和；披露口径不同（半年报全量 vs 季报前十大）的基金对不比较——混算会低估重叠。"
      info-label="持仓重叠度口径说明"
    />

    <CardBlock>
      <p v-if="loading" class="overlap-panel__hint" role="status">
        重叠度计算中…
      </p>

      <!-- 失败态不渲染空列表：空列表会被读成「没有重合」，与「没算出来」是两件事 -->
      <div v-else-if="error" class="overlap-panel__error" role="alert">
        <span class="overlap-panel__error-text">重叠度数据加载失败</span>
        <el-button text size="small" @click="load">重试</el-button>
      </div>

      <!-- 三种「没有重叠」必须分开，不能一律渲染成「重叠 0%」 -->
      <p v-else-if="state === 'degraded'" class="overlap-panel__hint">
        重叠度暂时取不到（上游持仓明细读取失败），稍后重试
      </p>
      <p v-else-if="state === 'not-computable'" class="overlap-panel__hint">
        可比较的持仓基金不足 2 只，算不出重叠度
      </p>
      <p v-else-if="state === 'no-overlap'" class="overlap-panel__hint">
        已比较 {{ fundCount }} 只持仓基金，它们之间没有共同重仓股
      </p>

      <template v-else>
        <ul class="overlap-panel__list">
          <li
            v-for="pair in data?.pairs ?? []"
            :key="`${pair.fund_code_a}-${pair.fund_code_b}`"
            class="overlap-panel__pair"
          >
            <div class="overlap-panel__head">
              <span class="overlap-panel__funds">
                {{ pair.fund_name_a }}
                <span class="overlap-panel__vs">↔</span>
                {{ pair.fund_name_b }}
              </span>
              <span class="overlap-panel__value">
                {{ formatWeightedOverlap(pair.weighted_overlap) }}
              </span>
            </div>
            <p class="overlap-panel__meta">
              集合口径 {{ formatJaccard(pair.jaccard) }} ·
              {{ describeBasis(pair.holding_basis) }}
            </p>
            <p v-if="describePeriodMismatch(pair)" class="overlap-panel__warn">
              {{ describePeriodMismatch(pair) }}
            </p>
            <ul class="overlap-panel__stocks">
              <li
                v-for="stock in pair.common_holdings.slice(0, 5)"
                :key="stock.stock_code"
                class="overlap-panel__stock"
              >
                <span class="overlap-panel__stock-name">{{
                  stock.stock_name
                }}</span>
                <span class="overlap-panel__stock-ratio">
                  {{ stock.ratio_a.toFixed(1) }}% /
                  {{ stock.ratio_b.toFixed(1) }}%
                </span>
              </li>
              <li
                v-if="pair.common_holdings.length > 5"
                class="overlap-panel__stock overlap-panel__stock--more"
              >
                还有 {{ pair.common_holdings.length - 5 }} 只共同重仓股
              </li>
            </ul>
          </li>
        </ul>

        <p class="overlap-panel__meta">{{ coverageText }}</p>
        <p v-if="skippedText" class="overlap-panel__warn">{{ skippedText }}</p>
      </template>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  getHoldingOverlap,
  type HoldingOverlapData
} from "@/api/holdingOverlap";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  describeBasis,
  describeCoverage,
  describePeriodMismatch,
  describeSkipped,
  formatJaccard,
  formatWeightedOverlap,
  resolveOverlapPanelState
} from "./holdingOverlapModel";

defineOptions({ name: "HoldingOverlapPanel" });

const data = ref<HoldingOverlapData | null>(null);
const loading = ref(false);
const error = ref(false);

/** 四态：取不到 / 算不出 / 确实不重叠 / 有重叠 */
const state = computed(() => resolveOverlapPanelState(data.value));
const fundCount = computed(() => data.value?.fund_count ?? 0);
const coverageText = computed(() => describeCoverage(data.value));
const skippedText = computed(() => describeSkipped(data.value));

const load = async () => {
  loading.value = true;
  error.value = false;
  try {
    const res = await getHoldingOverlap();
    data.value = res.data;
  } catch (e) {
    console.error("[holding-overlap] 重叠度数据加载失败", e);
    error.value = true;
  } finally {
    loading.value = false;
  }
};

onMounted(load);
</script>

<style scoped lang="scss">
.overlap-panel {
  &__hint {
    padding: 12px 0;
    margin: 0;
    font-size: var(--text-small);
    color: var(--text-tertiary);
  }

  &__error {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 8px 0;
  }

  &__error-text {
    font-size: var(--text-small);
    color: var(--text-secondary);
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: var(--space-standard);
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__pair {
    padding: var(--space-standard);
    background: var(--bg-muted);
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
    color: var(--text-tertiary);
  }

  &__value {
    font-size: var(--text-body);
    font-variant-numeric: tabular-nums;
    color: var(--color-danger);
  }

  &__meta {
    margin: 4px 0 0;
    font-size: var(--text-small);
    color: var(--text-tertiary);
  }

  &__warn {
    margin: 4px 0 0;
    font-size: var(--text-small);
    line-height: 1.55;
    color: var(--color-warning-fill);
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
    color: var(--text-tertiary);
  }
}
</style>
