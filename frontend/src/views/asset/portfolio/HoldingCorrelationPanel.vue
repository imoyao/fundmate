<template>
  <!--
    组合内基金持仓相关性（#2686 第二交付）：重叠度看「重仓股是否重复」，相关性看
    「涨跌是否同步」——两只基金完全可以零重仓股重叠、却因同赛道同风格而高度同步。

    本文件只做面板骨架（取数四态 + 分档汇总 + 矩阵 + 口径），铺格与文案在
    `holdingCorrelationMatrix.ts`（纯函数，可单测），矩阵渲染在
    `HoldingCorrelationMatrix.vue`。
  -->
  <div class="correlation-panel">
    <SectionHeader
      title="持仓相关性"
      info="按近 1 年日收益计算组合内两只基金的皮尔逊相关系数（同期交易日不少于 60 天）。ρ 越高说明一起涨一起跌、分散效果越差；负相关是天然对冲。成员与「持仓重叠度」矩阵一致（同一份裁剪规则），可对照着看。"
      info-label="持仓相关性口径说明"
    />

    <CardBlock>
      <p v-if="loading" class="correlation-panel__hint" role="status">
        相关性计算中…
      </p>

      <!-- 失败态不渲染空矩阵：空白格会被读成「不相关」，与「没算出来」是两件事 -->
      <div v-else-if="error" class="correlation-panel__error" role="alert">
        <span class="correlation-panel__error-text">相关性数据加载失败</span>
        <el-button text size="small" @click="load">重试</el-button>
      </div>

      <!-- 三种「没有值」分开渲染（后端 degraded / fund_count / cells 各管一种） -->
      <p v-else-if="degraded" class="correlation-panel__hint">
        相关性暂时取不到（上游持仓聚合失败），稍后重试
      </p>
      <p v-else-if="fundCount < 2" class="correlation-panel__hint">
        可比较的持仓基金不足 2 只，算不出相关性
      </p>
      <p v-else-if="!matrix" class="correlation-panel__hint">
        暂无可展示的相关性数据
      </p>

      <template v-else>
        <!-- 分档用数字并排：一眼分出「要处理的 N 对同步基金」与「算不出的 K 对」 -->
        <ul
          class="correlation-panel__tally"
          role="status"
          aria-label="相关性分档汇总"
        >
          <li
            v-for="chip in chips"
            :key="chip.key"
            class="correlation-panel__tally-item"
          >
            <span
              class="correlation-panel__tally-count"
              :class="`is-${chip.tone}`"
            >
              {{ chip.count }}
            </span>
            <span class="correlation-panel__tally-label">{{ chip.label }}</span>
          </li>
        </ul>

        <HoldingCorrelationMatrix :matrix="matrix" />

        <!-- 口径声明必须与结论同屏：截断范围、窗口敏感性、相关性固有失真 -->
        <ul v-if="caveats.length" class="correlation-panel__caveats">
          <li v-for="(text, index) in caveats" :key="index">{{ text }}</li>
        </ul>
      </template>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  getHoldingCorrelation,
  type HoldingCorrelationData
} from "@/api/holdingOverlap";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import HoldingCorrelationMatrix from "./HoldingCorrelationMatrix.vue";
import {
  buildCorrelationMatrix,
  tallyCorrelation
} from "./holdingCorrelationMatrix";

defineOptions({ name: "HoldingCorrelationPanel" });

const data = ref<HoldingCorrelationData | null>(null);
const loading = ref(false);
const error = ref(false);

const degraded = computed(() => data.value?.degraded === true);
const fundCount = computed(() => data.value?.fund_count ?? 0);
const caveats = computed(() => data.value?.caveats ?? []);
const matrix = computed(() =>
  data.value ? buildCorrelationMatrix(data.value) : null
);

const tally = computed(() => tallyCorrelation(data.value?.cells ?? []));
const chips = computed(() => [
  { key: "ok", count: tally.value.ok, label: "可算出（对）", tone: "ok" },
  {
    key: "high",
    count: tally.value.high,
    label: "ρ≥0.8 几乎同步",
    tone: "high"
  },
  {
    key: "negative",
    count: tally.value.negative,
    label: "ρ<−0.3 反向",
    tone: "negative"
  },
  {
    key: "unavailable",
    count: tally.value.unavailable,
    label: "算不出",
    tone: "muted"
  }
]);

async function load() {
  loading.value = true;
  error.value = false;
  try {
    const resp = await getHoldingCorrelation();
    data.value = resp.data ?? null;
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.correlation-panel {
  &__hint,
  &__error-text {
    margin: 0;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  &__error {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  &__tally {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-standard);
    padding: 0;
    margin: 0 0 var(--space-standard);
    list-style: none;
  }

  &__tally-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  &__tally-count {
    font-size: var(--text-num-strong);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);

    &.is-high {
      color: var(--color-danger-ink);
    }

    &.is-negative {
      color: var(--color-success-ink);
    }

    &.is-muted {
      color: var(--text-tertiary-ink);
    }
  }

  &__tally-label {
    font-size: var(--text-small);
    color: var(--text-tertiary-ink);
  }

  &__caveats {
    padding-left: 1.2em;
    margin: var(--space-standard) 0 0;
    font-size: var(--text-small);
    line-height: 1.7;
    color: var(--text-tertiary-ink);
  }
}
</style>
