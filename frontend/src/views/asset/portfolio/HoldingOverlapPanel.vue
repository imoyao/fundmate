<template>
  <!--
    组合内基金持仓重叠度（#2604）：两只基金重仓同一批股票 = 看着分散、实际同涨同跌。
    与「持仓穿透」的分工：穿透看「钱压在哪些行业/个股」，本面板看「我的基金之间有多重合」。

    本文件只做面板骨架（取数四态 + 分档汇总 + 主列表 + 尾部口径）。条目与弱提醒区
    分别拆到 HoldingOverlapPairItem / HoldingOverlapWeakList —— 三者各自控制在
    400 行以内（#980 页面规模门禁只减不增，单文件 649 行会被判红）。
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
        <!-- 汇总用分档计数而不是一句话：四个数字并排，一眼能分出「要处理的 10 对」
             和「可以先不管的 1817 对」；一句话在窄屏会折成三行，像免责声明 -->
        <div
          v-if="tallyChips.length"
          class="overlap-panel__tally-bar"
          role="status"
          aria-label="重叠度分档汇总"
        >
          <ul class="overlap-panel__tally">
            <li
              v-for="chip in tallyChips"
              :key="chip.key"
              class="overlap-panel__tally-item"
            >
              <span
                class="overlap-panel__tally-count"
                :class="`is-${chip.tone}`"
              >
                {{ chip.count }}
              </span>
              <span class="overlap-panel__tally-label">{{ chip.label }}</span>
            </li>
          </ul>
        </div>

        <ul class="overlap-panel__list">
          <HoldingOverlapPairItem
            v-for="pair in primaryPairs"
            :key="pairKey(pair)"
            :pair="pair"
          />
        </ul>

        <HoldingOverlapWeakList
          v-if="weakPairs.length"
          :pairs="weakPairs"
          :gate-text="gateText"
        />

        <p class="overlap-panel__meta">{{ coverageText }}</p>
        <p v-if="skippedText" class="overlap-panel__warn">{{ skippedText }}</p>

        <!-- 口径声明必须与结论同屏：字数不多，但决定了这些百分比能被信到什么程度 -->
        <ul v-if="caveatList.length" class="overlap-panel__caveats">
          <li v-for="(text, index) in caveatList" :key="index">{{ text }}</li>
        </ul>
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
import HoldingOverlapPairItem from "./HoldingOverlapPairItem.vue";
import HoldingOverlapWeakList from "./HoldingOverlapWeakList.vue";
import {
  describeCaveats,
  describeCoverage,
  describeOverlapTally,
  describeSkipped,
  formatAmountCents,
  pairKey,
  resolveOverlapPanelState,
  splitOverlapPairs
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
const caveatList = computed(() => describeCaveats(data.value));
const tallyChips = computed(() => describeOverlapTally(data.value));

const pairSplit = computed(() => splitOverlapPairs(data.value));
const primaryPairs = computed(() => pairSplit.value.primary);
const weakPairs = computed(() => pairSplit.value.weak);

/** 分档线文案（后端下发，不在前端另写一个数） */
const gateText = computed(() =>
  formatAmountCents(data.value?.min_overlap_amount_cents)
);

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
    color: var(--text-tertiary-ink);
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

  /* 分档计数：四个数字并排，比一句话更快分辨「要处理的」与「可不管的」 */
  &__tally {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__tally-bar {
    margin-bottom: var(--space-standard);
  }

  &__tally-item {
    display: inline-flex;
    gap: 6px;
    align-items: baseline;
    padding: 4px 10px;
    background: var(--bg-card);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-button);
  }

  &__tally-count {
    font-size: var(--text-body);
    font-weight: 600;
    font-variant-numeric: tabular-nums;

    &.is-danger {
      color: var(--color-danger-ink);
    }

    &.is-warning {
      color: var(--color-warning-ink);
    }

    &.is-info {
      color: var(--color-info-ink);
    }

    &.is-muted {
      color: var(--text-secondary);
    }
  }

  &__tally-label {
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

  &__caveats {
    padding-left: 1em;
    margin: var(--space-standard) 0 0;
    font-size: var(--text-small);
    line-height: 1.6;
    color: var(--text-tertiary-ink);
  }
}
</style>
