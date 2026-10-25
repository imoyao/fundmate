<template>
  <!--
    组合风格构成（#2603）：持仓按市值加权后的 8 分类风格暴露。
    与「持仓小贴士」的分工：贴士说「哪条规则此刻成立」，本面板给出「风格构成的事实」，
    两者读同一个后端口径（组合风格暴露），不会各说各话。
  -->
  <div class="style-panel">
    <SectionHeader
      title="组合风格构成"
      info="按持仓市值加权后的 8 分类风格暴露（晨星式分类，来自基金定期披露的风格箱）。覆盖率不足时结论仅供参考；含 QDII 持仓时其风格分类口径存疑。"
      info-label="组合风格口径说明"
    />

    <CardBlock>
      <p v-if="loading" class="style-panel__hint" role="status">
        风格数据加载中…
      </p>

      <!-- 失败态不渲染空列表：空列表会被读成「风格很均衡」，与「没算出来」是两件事 -->
      <div v-else-if="error" class="style-panel__error" role="alert">
        <span class="style-panel__error-text">风格数据加载失败</span>
        <el-button text size="small" @click="load">重试</el-button>
      </div>

      <p v-else-if="state === 'empty'" class="style-panel__hint">
        {{ emptyText }}
      </p>

      <template v-else>
        <ul class="style-panel__list">
          <li
            v-for="item in data?.styles ?? []"
            :key="item.style_name"
            class="style-panel__row"
          >
            <span class="style-panel__name">{{ item.style_name }}</span>
            <span class="style-panel__track" aria-hidden="true">
              <span
                class="style-panel__bar"
                :style="{ width: styleBarWidth(item.value) }"
              />
            </span>
            <span class="style-panel__value">
              {{ formatStyleValue(item.value) }}
            </span>
          </li>
        </ul>

        <p class="style-panel__meta">{{ coverageText }}</p>

        <p v-if="state === 'low-coverage'" class="style-panel__warn">
          覆盖率不足 {{ STYLE_COVERAGE_FLOOR }}%，上面的风格占比只代表部分持仓
        </p>
        <p v-if="uncoveredText" class="style-panel__warn">
          {{ uncoveredText }}
        </p>
        <p v-if="qdiiText" class="style-panel__warn">{{ qdiiText }}</p>
      </template>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getPortfolioStyle, type PortfolioStyleExposure } from "@/api/funds";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  STYLE_COVERAGE_FLOOR,
  describeQdiiCaveat,
  describeStyleCoverage,
  describeUncovered,
  formatStyleValue,
  resolveStylePanelState,
  styleBarWidth
} from "./portfolioStyleModel";

defineOptions({ name: "PortfolioStylePanel" });

const data = ref<PortfolioStyleExposure | null>(null);
const loading = ref(false);
const error = ref(false);

/** 三态：算不出来 / 算得不全 / 算得全 */
const state = computed(() => resolveStylePanelState(data.value));
const coverageText = computed(() => describeStyleCoverage(data.value));
const uncoveredText = computed(() => describeUncovered(data.value));
const qdiiText = computed(() => describeQdiiCaveat(data.value));

/** 空态文案必须区分「没有持仓」与「有持仓但算不出风格」 */
const emptyText = computed(() => {
  const total = data.value?.total_market_value_cents ?? 0;
  if (!total) return "还没有投资持仓，暂无可展示的风格构成。";
  return "持仓基金暂无可用的风格箱数据，算不出风格构成（不等于「全部为 0」）。";
});

const load = async () => {
  loading.value = true;
  error.value = false;
  try {
    const res = await getPortfolioStyle();
    data.value = res.data;
  } catch (e) {
    console.error("[portfolio-style] 风格数据加载失败", e);
    error.value = true;
  } finally {
    loading.value = false;
  }
};

onMounted(load);
</script>

<style scoped lang="scss">
.style-panel {
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
    gap: var(--space-compact);
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__row {
    display: flex;
    gap: var(--space-standard);
    align-items: center;
  }

  &__name {
    flex: 0 0 72px;
    font-size: var(--text-small);
    color: var(--text-secondary);
  }

  &__track {
    flex: 1 1 auto;
    height: 8px;
    overflow: hidden;
    background: var(--bg-muted);
    border-radius: var(--radius-button);
  }

  &__bar {
    display: block;
    height: 100%;
    background: var(--color-primary);
    border-radius: var(--radius-button);
  }

  &__value {
    flex: 0 0 56px;
    font-size: var(--text-small);
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
    text-align: right;
  }

  &__meta {
    margin: var(--space-standard) 0 0;
    font-size: var(--text-small);
    color: var(--text-tertiary);
  }

  &__warn {
    margin: 4px 0 0;
    font-size: var(--text-small);
    line-height: 1.55;
    color: var(--color-warning-fill);
  }
}
</style>
