<template>
  <div
    class="style-dist rounded-2xl p-6 mb-4"
    :style="{
      backgroundColor: 'var(--bg-card)',
      boxShadow: 'var(--shadow-raised)',
      border: '1px solid var(--border-light)'
    }"
  >
    <div class="mb-4 flex flex-wrap items-baseline justify-between gap-2">
      <div class="flex items-baseline gap-3">
        <h3 class="font-semibold" :style="{ color: 'var(--text-primary)' }">
          基金风格分布
        </h3>
        <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
          按持仓市值加权 · 箱体时点 {{ periodText || "—" }}
        </span>
      </div>
      <span
        v-if="!empty"
        class="text-xs tabular-nums"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        覆盖率 {{ coverageText }}（{{ data.fund_count }} 只基金）
      </span>
    </div>

    <!-- 加载中 -->
    <div
      v-if="loading"
      class="py-10 text-center text-sm"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      加载中…
    </div>

    <!-- 算不出来：styles 为空数组 ≠ 全部为 0（后端契约） -->
    <div v-else-if="empty" class="py-8 text-sm">
      <p :style="{ color: 'var(--text-secondary)' }">
        {{ errorText || "暂无基金风格数据" }}
      </p>
      <p class="mt-1 text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
        风格箱按月更新，只有同步过风格的基金才计入；其余持仓见下方「未覆盖」清单
      </p>
    </div>

    <!-- 有数据 -->
    <template v-else>
      <ul class="flex flex-col gap-2">
        <li v-for="bar in bars" :key="bar.name" class="flex items-center gap-3">
          <span
            class="w-20 shrink-0 text-sm"
            :style="{ color: 'var(--text-secondary)' }"
          >
            {{ bar.name }}
          </span>
          <span
            class="relative h-2 flex-1 overflow-hidden rounded-full"
            :style="{ backgroundColor: 'var(--bg-subtle)' }"
          >
            <span
              class="absolute inset-y-0 left-0 rounded-full"
              :style="{
                width: `${bar.widthPct}%`,
                backgroundColor: 'var(--brand-ink)',
                opacity: bar.isLead ? 1 : 0.28
              }"
            />
          </span>
          <span
            class="w-14 shrink-0 text-right text-sm font-semibold tabular-nums"
            :style="{
              color: bar.isLead ? 'var(--brand-ink)' : 'var(--text-secondary)'
            }"
          >
            {{ bar.value.toFixed(1) }}%
          </span>
        </li>
      </ul>

      <!-- 未覆盖清单：不补 0、不藏起来 -->
      <div
        v-if="data.uncovered.length"
        class="mt-4 pt-3 text-xs"
        :style="{
          borderTop: '1px solid var(--border-light)',
          color: 'var(--text-tertiary-ink)'
        }"
      >
        <p>
          未覆盖 {{ data.uncovered.length }} 只（ {{ coveredAmountText }} /
          {{ totalAmountText }} 计入了加权）：
          <span :style="{ color: 'var(--text-secondary)' }">
            {{ uncoveredText }}
          </span>
          <el-button
            v-if="uncoveredRestCount > 0"
            text
            size="small"
            class="ml-1"
            @click="expanded = !expanded"
          >
            {{ expanded ? "收起" : `展开全部 ${data.uncovered.length} 只` }}
          </el-button>
        </p>
      </div>

      <p
        v-if="data.has_qdii"
        class="mt-2 text-xs"
        :style="{ color: 'var(--color-warning-ink)' }"
      >
        注：持仓含 QDII，其风格分类为上游原值（海外资产映射口径存疑），未做修正
      </p>
      <p class="mt-2 text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
        数据来源：{{ sourceText }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getPortfolioStyle } from "@/api/funds";
import type { PortfolioStyleExposure } from "@/api/funds";
import { formatAmount } from "@/utils/currency";
import {
  NO_ELIGIBLE_COVERAGE_TEXT,
  coverageScopeHint,
  effectiveCoveragePct
} from "@/utils/styleCoverage";
import {
  buildStyleBars,
  formatCoverage,
  isStyleEmpty,
  periodLabel,
  uncoveredSummary
} from "./styleDistributionModel";

/**
 * 家庭级基金风格分布（#2628）。
 *
 * 自取数据而非由父页传入：资产总览的 `fetchData` 已经串了 4 个请求，
 * 风格数据是**可选增强**（失败只影响本卡），塞进去会让首屏一起被它拖慢。
 */
const data = ref<PortfolioStyleExposure | null>(null);
const loading = ref(true);
const expanded = ref(false);

const DEFAULT_DATA: PortfolioStyleExposure = {
  styles: [],
  fund_count: 0,
  covered_market_value_cents: 0,
  total_market_value_cents: 0,
  coverage_pct: 0,
  eligible_market_value_cents: 0,
  eligible_coverage_pct: null,
  period_from: null,
  period_to: null,
  uncovered: [],
  has_qdii: false,
  source: "jiucaishuo_style"
};

const empty = computed(() => isStyleEmpty(data.value));
const bars = computed(() => buildStyleBars(data.value?.styles));
/**
 * 覆盖率主数字用**可覆盖口径**（#2628）：全量口径的分母含永远无箱体的货基/现金，
 * 数字有天花板（实测 8.35%），直接展示会被读成「同步没在跑」。
 * 两个口径不同时把全量值作为括号提示带上，避免用户对不上「未覆盖清单」里的货基。
 */
const coverageText = computed(() => {
  const pct = effectiveCoveragePct(data.value);
  if (pct === null) return NO_ELIGIBLE_COVERAGE_TEXT;
  const main = formatCoverage(pct);
  const hint = coverageScopeHint(data.value);
  return hint ? `${main}（${hint}）` : main;
});
const periodText = computed(() => periodLabel(data.value));

const toYuan = (cents: number) => `¥${formatAmount((cents || 0) / 100, 0)}`;
const coveredAmountText = computed(() =>
  toYuan(data.value?.covered_market_value_cents ?? 0)
);
const totalAmountText = computed(() =>
  toYuan(data.value?.total_market_value_cents ?? 0)
);

const uncoveredList = computed(() => data.value?.uncovered ?? []);
const uncoveredRestCount = computed(
  () => uncoveredSummary(uncoveredList.value, 5).restCount
);
const uncoveredText = computed(() => {
  const limit = expanded.value ? uncoveredList.value.length : 5;
  const { shown } = uncoveredSummary(uncoveredList.value, limit);
  return (
    shown
      .map(item => `${item.name}（${toYuan(item.market_value_cents)}）`)
      .join("、") + (uncoveredRestCount.value > 0 && !expanded.value ? "…" : "")
  );
});

/** 来源标记 → 人话。后端只透出稳定枚举，别在前端拼技术串 */
const SOURCE_LABELS: Record<string, string> = {
  jiucaishuo_style: "韭圈儿（晨星式 8 分类，月度）"
};
const sourceText = computed(
  () => SOURCE_LABELS[data.value?.source ?? ""] ?? data.value?.source ?? "—"
);

const errorText = ref("");

onMounted(async () => {
  try {
    const res = await getPortfolioStyle();
    data.value = res.data ?? DEFAULT_DATA;
  } catch (e) {
    // 风格分布是增强信息：失败不打断资产总览，只把本卡降级成一句说明
    data.value = DEFAULT_DATA;
    errorText.value = "风格数据暂不可用";
    console.warn("[style-distribution] 加载失败:", e);
  } finally {
    loading.value = false;
  }
});
</script>
