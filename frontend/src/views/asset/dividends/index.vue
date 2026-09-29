<!--
  分红与股息（Dividends）· 页面编排层（#872）

  数据源只有一个：`GET /api/dividends/summary/`（后端 `services/dividend_service.py` 是
  「分红收益」口径的唯一出口）。本页只负责取数、分段切换与状态呈现：

  - 总览（金额 / 股息率 / 股息目标 / 逐年）→ `./components/DividendOverviewPanel.vue`
  - 逐持仓股息率 → `./components/DividendHoldingTable.vue`
-->
<template>
  <div
    class="dividends-home min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <PageHeaderBar
      title="分红与股息"
      subtitle="分红累计、股息率与目标达成度"
      :updated-at="summary?.as_of"
    >
      <template #action>
        <el-button :loading="loading" @click="load">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
        </el-button>
      </template>
    </PageHeaderBar>

    <div class="dividends-shell">
      <PageSkeleton
        v-if="showSkeleton"
        :cards="4"
        :chart-cols="0"
        :table-rows="6"
      />

      <template v-else>
        <p v-if="errorMsg" class="dividends-hint">
          {{ errorMsg }}
          <el-button text size="small" type="primary" @click="load">
            重试
          </el-button>
        </p>

        <template v-else-if="summary">
          <SegmentedControl
            v-model="view"
            :options="viewOptions"
            aria-label="分红视图切换"
          />

          <DividendOverviewPanel
            v-if="view === 'overview'"
            :summary="summary"
            @saved="load"
          />
          <DividendHoldingTable
            v-else
            :holdings="summary.holdings"
            :portfolio="summary.portfolio"
            :months="summary.period.months"
          />
        </template>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { getDividendSummary, type DividendSummary } from "@/api/dividends";
import DividendOverviewPanel from "./components/DividendOverviewPanel.vue";
import DividendHoldingTable from "./components/DividendHoldingTable.vue";

// 与路由 `router/modules/home.ts` 的 name 一致，保证 keep-alive 命中
defineOptions({ name: "Dividends" });

/** 股息率固定走 TTM 口径（12 个月）；逐年汇总回溯 5 年 —— 两者都是后端入参的默认值 */
const PERIOD_MONTHS = 12;
const BY_YEAR_SPAN = 5;
/** 骨架屏阈值：请求 ≤200ms 直接出内容，避免闪屏（组件约定，见 docs/design/components.md） */
const SKELETON_DELAY_MS = 200;

type DividendsView = "overview" | "holdings";

const view = ref<DividendsView>("overview");
const summary = ref<DividendSummary | null>(null);
const loading = ref(false);
const showSkeleton = ref(false);
const errorMsg = ref("");
let skeletonTimer: ReturnType<typeof setTimeout> | null = null;

const viewOptions: { label: string; value: DividendsView }[] = [
  { label: "总览", value: "overview" },
  { label: "逐持仓", value: "holdings" }
];

async function load() {
  loading.value = true;
  errorMsg.value = "";
  if (skeletonTimer) clearTimeout(skeletonTimer);
  skeletonTimer = setTimeout(() => {
    showSkeleton.value = true;
  }, SKELETON_DELAY_MS);
  try {
    const res = await getDividendSummary({
      months: PERIOD_MONTHS,
      years: BY_YEAR_SPAN
    });
    summary.value = res?.data ?? null;
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : "分红数据加载失败";
  } finally {
    if (skeletonTimer) {
      clearTimeout(skeletonTimer);
      skeletonTimer = null;
    }
    showSkeleton.value = false;
    loading.value = false;
  }
}

onMounted(load);

onUnmounted(() => {
  if (skeletonTimer) clearTimeout(skeletonTimer);
});
</script>

<style scoped>
/* 页面底部留白：页头自带 --space-section 下边距，这里补一个对称的底部 */
.dividends-home {
  padding-bottom: var(--space-section);
}

/* 内容区与 PageHeaderBar 同宽同内边距（--layout-content-width / --space-standard），
   保证页头与内容左边缘严格对齐；与 inventory / profile 等同值（#1501 / #1506）。 */
.dividends-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-section);
  max-width: var(--layout-content-width);
  padding: 0 var(--space-standard);
  margin: 0 auto;
}

.dividends-hint {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
