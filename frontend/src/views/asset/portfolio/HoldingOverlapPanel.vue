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
          <li
            v-for="pair in primaryPairs"
            :key="pairKey(pair)"
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
            <p
              v-if="describeOverlapLevel(pair) || pair.overlap_reason"
              class="overlap-panel__verdict"
            >
              <!-- 中性档（同一基金份额）用描边徽标而不是 el-tag：EP 的 info 标签
                   文字 #909399 在浅底上只有 2.8:1，过不了 AA；而彩色档位继续用
                   el-tag——「要处置的」有颜色、「只是说明的」只有描边，层级正好 -->
              <span
                v-if="describeOverlapLevel(pair)?.tone === 'info'"
                class="overlap-panel__neutral-badge"
              >
                {{ describeOverlapLevel(pair)?.label }}
              </span>
              <el-tag
                v-else-if="describeOverlapLevel(pair)"
                :type="describeOverlapLevel(pair)?.tone"
                size="small"
                effect="light"
              >
                {{ describeOverlapLevel(pair)?.label }}
              </el-tag>
              <span v-if="pair.overlap_reason" class="overlap-panel__reason">
                {{ pair.overlap_reason }}
              </span>
            </p>
            <p class="overlap-panel__meta">
              集合口径 {{ formatJaccard(pair.jaccard) }} · 重复投入
              {{ formatAmountCents(pair.overlap_amount_cents) }} ·
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

        <!-- 弱提醒：小仓位不是「不提醒」，是「不占第一屏」。默认折叠、标题带条数，
             展开后可按基金筛选、逐对看共同重仓股——用户想核对时随时能看到，
             不想看时也不会被 1817 条噪音淹掉（实测金额中位数 ¥0.68） -->
        <el-collapse
          v-if="weakPairs.length"
          v-model="weakOpen"
          class="overlap-panel__weak"
        >
          <el-collapse-item name="weak">
            <template #title>
              <span class="overlap-panel__weak-head">
                <span class="overlap-panel__weak-title">
                  弱提醒 · {{ weakPairs.length }} 对
                </span>
                <span class="overlap-panel__weak-note"
                  >金额小或重合度不高，默认折叠</span
                >
              </span>
            </template>

            <p class="overlap-panel__weak-hint">{{ weakHint }}</p>

            <div class="overlap-panel__weak-tools">
              <el-input
                v-model="weakKeyword"
                class="overlap-panel__weak-search"
                size="small"
                clearable
                placeholder="按基金代码或名称筛选"
                aria-label="筛选弱提醒中的基金"
              />
              <span v-if="weakKeyword" class="overlap-panel__meta">
                筛出 {{ filteredWeak.length }} 对
              </span>
            </div>

            <p v-if="!filteredWeak.length" class="overlap-panel__meta">
              没有匹配「{{ weakKeyword }}」的基金对
            </p>

            <ul v-else class="overlap-panel__list">
              <li
                v-for="pair in weakPage.visible"
                :key="pairKey(pair)"
                class="overlap-panel__pair overlap-panel__pair--weak"
              >
                <div class="overlap-panel__head">
                  <span class="overlap-panel__funds overlap-panel__funds--weak">
                    {{ pair.fund_name_a }}
                    <span class="overlap-panel__vs">↔</span>
                    {{ pair.fund_name_b }}
                  </span>
                  <span class="overlap-panel__value overlap-panel__value--weak">
                    {{ formatWeightedOverlap(pair.weighted_overlap) }}
                  </span>
                </div>
                <p class="overlap-panel__verdict">
                  <span class="overlap-panel__weak-badge">弱提醒</span>
                  <span class="overlap-panel__reason">
                    {{ describeWeakReason(pair) }}
                  </span>
                </p>
                <p class="overlap-panel__meta">
                  集合口径 {{ formatJaccard(pair.jaccard) }} · 重复投入
                  {{ formatAmountCents(pair.overlap_amount_cents) }} ·
                  {{ describeBasis(pair.holding_basis) }}
                  <el-button
                    text
                    size="small"
                    class="overlap-panel__detail-toggle"
                    :aria-expanded="isWeakOpen(pair)"
                    @click="toggleWeakDetail(pair)"
                  >
                    {{ isWeakOpen(pair) ? "收起明细" : "查看明细" }}
                  </el-button>
                </p>
                <template v-if="isWeakOpen(pair)">
                  <p
                    v-if="describePeriodMismatch(pair)"
                    class="overlap-panel__warn"
                  >
                    {{ describePeriodMismatch(pair) }}
                  </p>
                  <ul class="overlap-panel__stocks">
                    <li
                      v-for="stock in pair.common_holdings"
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
                  </ul>
                </template>
              </li>
            </ul>

            <div v-if="weakPage.hasMore" class="overlap-panel__more">
              <el-button size="small" @click="loadMoreWeak">
                再显示 {{ nextWeakBatch }} 对（还有
                {{ weakPage.remaining }} 对）
              </el-button>
            </div>
            <p v-else-if="filteredWeak.length" class="overlap-panel__meta">
              已显示全部 {{ filteredWeak.length }} 对
            </p>
          </el-collapse-item>
        </el-collapse>

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
import { computed, onMounted, ref, watch } from "vue";
import {
  getHoldingOverlap,
  type HoldingOverlapData
} from "@/api/holdingOverlap";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  describeBasis,
  describeCaveats,
  describeCoverage,
  describeOverlapLevel,
  describeOverlapTally,
  describePeriodMismatch,
  describeSkipped,
  describeWeakHint,
  describeWeakReason,
  filterWeakPairs,
  formatAmountCents,
  formatJaccard,
  formatWeightedOverlap,
  resolveOverlapPanelState,
  sliceWeakPairs,
  splitOverlapPairs,
  WEAK_PAGE_SIZE
} from "./holdingOverlapModel";
import type { OverlapPair } from "./holdingOverlapModel";

defineOptions({ name: "HoldingOverlapPanel" });

const data = ref<HoldingOverlapData | null>(null);
const loading = ref(false);
const error = ref(false);

/** 弱提醒区：默认折叠（空数组 = 收起）；用户展开过就记住 */
const weakOpen = ref<string[]>([]);
/** 弱提醒筛选关键词（1817 对里找一个特定基金，靠滚动不现实） */
const weakKeyword = ref("");
/** 已加载的弱提醒条数（分页而非一次渲染 1817 条） */
const weakLoaded = ref(WEAK_PAGE_SIZE);
/** 逐对展开「查看明细」的 key 集合 */
const openWeakDetails = ref<string[]>([]);

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
const weakHint = computed(() => describeWeakHint(gateText.value));

const filteredWeak = computed(() =>
  filterWeakPairs(weakPairs.value, weakKeyword.value)
);
const weakPage = computed(() =>
  sliceWeakPairs(filteredWeak.value, weakLoaded.value)
);
const nextWeakBatch = computed(() =>
  Math.min(WEAK_PAGE_SIZE, weakPage.value.remaining)
);

/** 换了关键词就回到第一页，否则「筛出 3 对」却还挂着上次翻到的 150 条 */
watch(weakKeyword, () => {
  weakLoaded.value = WEAK_PAGE_SIZE;
});

const pairKey = (pair: OverlapPair) =>
  `${pair.fund_code_a}-${pair.fund_code_b}`;
const isWeakOpen = (pair: OverlapPair) =>
  openWeakDetails.value.includes(pairKey(pair));
const toggleWeakDetail = (pair: OverlapPair) => {
  const key = pairKey(pair);
  openWeakDetails.value = isWeakOpen(pair)
    ? openWeakDetails.value.filter(item => item !== key)
    : [...openWeakDetails.value, key];
};
const loadMoreWeak = () => {
  weakLoaded.value += WEAK_PAGE_SIZE;
};

const load = async () => {
  loading.value = true;
  error.value = false;
  try {
    const res = await getHoldingOverlap();
    data.value = res.data;
    // 换一批数据就重置展开/筛选状态：否则旧 key 会残留在新列表里
    weakOpen.value = [];
    weakKeyword.value = "";
    weakLoaded.value = WEAK_PAGE_SIZE;
    openWeakDetails.value = [];
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

  &__caveats {
    padding-left: 1em;
    margin: var(--space-standard) 0 0;
    font-size: var(--text-small);
    line-height: 1.6;
    color: var(--text-tertiary-ink);
  }

  /* 白底 + 描边而不是灰底：灰底上 --color-danger 只有 4.42:1，
     刚好卡在 AA 线下方（#d4364a on #f5f7fa）；白底 4.74 才过 */
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

  /* ── 弱提醒区 ─────────────────────────────────────────────── */
  &__weak {
    margin-top: var(--space-standard);
    border-top: 1px solid var(--divider-default);
    border-bottom: none;

    :deep(.el-collapse-item__header) {
      height: auto;
      padding: 10px 0;
      line-height: 1.5;
      background: transparent;
      border-bottom: none;
    }

    :deep(.el-collapse-item__wrap) {
      background: transparent;
      border-bottom: none;
    }

    :deep(.el-collapse-item__content) {
      padding-bottom: 4px;
    }
  }

  &__weak-head {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: baseline;
  }

  &__weak-title {
    font-size: var(--text-body);
    color: var(--text-secondary);
  }

  &__weak-note {
    font-size: var(--text-small);
    color: var(--text-tertiary-ink);
  }

  &__weak-hint {
    margin: 0 0 8px;
    font-size: var(--text-small);
    line-height: 1.6;
    color: var(--text-secondary);
  }

  &__weak-tools {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: var(--space-standard);
  }

  &__weak-search {
    max-width: 260px;
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

  &__more {
    margin-top: var(--space-standard);
    text-align: center;
  }
}
</style>
