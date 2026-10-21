<!-- frontend/src/views/product/components/ProductStyleSection.vue -->
<!--
  详情页「投资风格」区块（#2478 · 韭圈儿 get-style-history，月度，job 落库）。

  数据契约（backend/app/services/fund_style_service.py，契约留档
  docs/working-notes/fund-style-api-contract-2026-10-21.md）：
  · 风格箱只覆盖基金与 ETF，股票持仓不在口径内——详情页仅 fund 品类渲染；
  · 8 分类固定展示序（晨星式 大/中/小盘 × 成长/价值 + 港股风格 + 固收风格），
    同一点曝光合计应为 100；null=该时点该风格缺失，渲染「—」不补 0；
  · QDII 上游映射存疑（270042 纳指100 实测「固收风格 81.28」），后端原样透出，
    本区块脚注提示「QDII 口径仅供参考」；
  · 主导风格漂移信号由后端算好（dominant_changed）透出，前端不下结论；
  · 历史走势为月度序列（wide 转 long），最多取 60 点（≈5 年），降序即时间倒序。

  配色：8 分类上色走全站图表色令牌 --chart-01..08（design.md 红线，禁硬编码）；
  历史折线同理（echarts 渲到 canvas，必须用 getCssVar 读出的解析色值）。
-->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import VChart from "vue-echarts";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  getFundStyleLatest,
  getFundStyleHistory,
  type FundStyleBox,
  type FundStyleHistory
} from "@/api/funds";
import { getCssVar, useThemeTick } from "@/composables/echarts/theme";
import {
  hasStyleData,
  orderedStyles,
  styleDrift,
  driftText,
  styleColorVar,
  formatStyleValue,
  buildStyleHistoryOption
} from "./styleSectionMetrics";

const props = defineProps<{
  /** 标准化 symbol（如 SH000001）或裸码均可——后端按裸码匹配 */
  symbol: string;
}>();

const loading = ref(false);
const box = ref<FundStyleBox | null>(null);
const history = ref<FundStyleHistory | null>(null);

/** 区块脚注：口径黑盒 + 来源注明 + QDII 提示（契约要求展示层标注） */
const INFO_TEXT =
  "投资风格按韭圈儿月度风格箱归类（大/中/小盘 × 成长/价值 + 港股/固收）；QDII 上游映射仅供参考。数据来源：韭圈儿";

const rows = computed(() => orderedStyles(box.value));
const hasData = computed(() => hasStyleData(box.value));
const drift = computed(() => styleDrift(box.value));
const driftLabel = computed(() => driftText(drift.value));
const dominantName = computed(() => drift.value.current);

/** 条形矩阵里暴露值的百分比宽度（0-100 即占比；null 时为 0，渲染「—」） */
function barWidth(value: number | null): string {
  if (value == null) return "0%";
  return `${Math.min(100, Math.max(0, value))}%`;
}

// ── 历史折线（echarts）：主题切换时重算 option（#976） ──
const themeTick = useThemeTick();
const chartOption = computed(() => {
  void themeTick.value; // 建立依赖，暗色切换时重读色值
  return buildStyleHistoryOption(history.value, (index: number) =>
    getCssVar(styleColorVar(index), "#b0a89c")
  );
});
const showHistory = computed(
  () => history.value?.points?.length && history.value.points.length > 1
);

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  try {
    const [boxRes, historyRes] = await Promise.all([
      getFundStyleLatest(props.symbol),
      getFundStyleHistory(props.symbol, 60)
    ]);
    box.value = boxRes.data;
    history.value = historyRes.data;
  } catch (e) {
    console.error("获取投资风格失败:", e);
    box.value = null;
    history.value = null;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <CardBlock class="style-section">
    <SectionHeader title="投资风格" :info="INFO_TEXT" />

    <p v-if="loading" class="style-section__hint">正在读取投资风格…</p>

    <!-- 无数据（该基金未纳入风格箱口径 / job 尚未同步） -->
    <p v-else-if="!hasData" class="style-section__hint">
      —
      <span class="style-section__hint-note"
        >（该基金暂无风格箱数据，可能未纳入韭圈儿风格口径）</span
      >
    </p>

    <template v-else>
      <!-- 条形矩阵：8 分类按固定序，主导风格高亮 + 「主导」徽标 -->
      <ul class="style-matrix">
        <li
          v-for="row in rows"
          :key="row.style_name"
          class="style-matrix__row"
          :class="{
            'style-matrix__row--dominant': row.style_name === dominantName
          }"
        >
          <span
            class="style-matrix__dot"
            :style="{ background: `var(${row.colorVar})` }"
          />
          <span class="style-matrix__name" :title="row.style_name">{{
            row.style_name
          }}</span>
          <span
            v-if="row.style_name === dominantName"
            class="style-matrix__badge"
            >主导</span
          >
          <span class="style-matrix__track">
            <span
              class="style-matrix__bar"
              :style="{
                width: barWidth(row.value),
                background: `var(${row.colorVar})`
              }"
            />
          </span>
          <span class="style-matrix__value">{{
            formatStyleValue(row.value)
          }}</span>
        </li>
      </ul>

      <!-- 漂移信号条：切换 / 维持 / 首次，分别措辞 -->
      <p v-if="driftLabel" class="style-section__drift">
        {{ driftLabel }}
        <span v-if="box?.stat_date" class="style-section__drift-date"
          >（截至 {{ box.stat_date }}）</span
        >
      </p>

      <!-- 历史走势：月度序列折线（≥2 点才画，单点无意义） -->
      <div v-if="showHistory" class="style-section__chart">
        <v-chart
          :option="chartOption as any"
          :autoresize="true"
          style="width: 100%; height: 280px"
        />
      </div>
    </template>
  </CardBlock>
</template>

<style lang="scss" scoped>
.style-section {
  &__hint {
    display: flex;
    align-items: baseline;
    margin: 0;
    font-size: var(--text-label);
    color: var(--text-tertiary);
  }

  &__hint-note {
    margin-left: 4px;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  /* 8 行条形矩阵：色点 + 名称 + 主导徽标 + 轨道 + 数值 */
  .style-matrix {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 0;
    margin: 4px 0 0;
    list-style: none;

    &__row {
      display: grid;
      grid-template-columns: 10px minmax(64px, auto) auto 1fr auto;
      gap: 10px;
      align-items: center;

      &--dominant {
        font-weight: 600;
      }
    }

    &__dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }

    &__name {
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: var(--text-label);
      color: var(--text-secondary);
      white-space: nowrap;
    }

    &__badge {
      padding: 0 6px;
      font-size: var(--text-label);
      line-height: 18px;
      color: var(--brand-700);
      background: var(--brand-100);
      border-radius: 9px;
    }

    &__track {
      height: 8px;
      overflow: hidden;
      background: var(--bg-soft);
      border-radius: var(--radius-pill);
    }

    &__bar {
      display: block;
      height: 100%;
      border-radius: var(--radius-pill);
      transition: width 0.3s ease;
    }

    &__value {
      min-width: 52px;
      font-size: var(--text-label);
      font-variant-numeric: tabular-nums;
      color: var(--text-primary);
      text-align: right;
    }
  }

  &__drift {
    margin: 12px 0 0;
    font-size: var(--text-label);
    color: var(--text-secondary);

    &-date {
      color: var(--text-tertiary);
    }
  }

  &__chart {
    margin-top: 12px;
  }
}
</style>
