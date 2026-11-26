<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  getAdvisorStyleCompare,
  type AdvisorComparisonResult,
  type AdvisorStyleCompareResult
} from "@/api/funds";
import { buildDirectionRows, mostDivergent } from "./advisorDirectionModel";
import AdvisorDirectionBars from "./AdvisorDirectionBars.vue";
import AdvisorOverlapChips from "./AdvisorOverlapChips.vue";

/**
 * 投顾组合 · 与我账户的对照（重设计 §05，宿主）。
 *
 * ## 为什么不再只给清单
 *
 * 旧版三集合里「我持有 · 组合里没有」是一份 109 只的清单——数量本身不说明问题。
 * 用户的原话是「最主要的是需要有一个比例或者方向的对比」。现在按风格暴露把两边
 * 折成五个方向的占比、在同一刻度上画成对条，差值 ≥5pp 才点色，提示条只点最不一致
 * 的两档；清单折叠在下面，要查具体哪只再展开。
 *
 * ## 两份数据、两条降级路径（故拆成两个子件）
 *
 * | 数据 | 口径 | 失效时 |
 * |---|---|---|
 * | `style-compare` | 风格箱 → 五方向 | 方向块整块降级（只画一侧没有对照意义） |
 * | `compare` | 基金代码级三集合 | 只影响清单与「已持有」列 |
 *
 * 子件：`AdvisorDirectionBars`（图 + 提示条 + 覆盖缺口）、
 * `AdvisorOverlapChips`（三集合并集与组合外持仓）。本文件只取数、判降级、算口径。
 *
 * ## 口径（两侧必须对称）
 *
 * - 组合按**披露权重**加权、我按**持仓市值**加权，两侧都只统计有风格箱的基金；
 * - 覆盖率必须显示：组合侧实测 91.5%（一只 8.37% 权重的基金没有箱体），
 *   若按 100% 呈现，那 8.37% 的缺失就被悄悄摊进了其他方向。
 *
 * ## 合规
 *
 * 只陈述客观数据，不写「它更强 / 建议替换」。
 */
const props = defineProps<{
  code: string;
  comparison: AdvisorComparisonResult | null;
}>();

const loading = ref(false);
const failed = ref(false);
const style = ref<AdvisorStyleCompareResult | null>(null);

watch(
  () => props.code,
  async code => {
    if (!code) return;
    loading.value = true;
    failed.value = false;
    try {
      const res = await getAdvisorStyleCompare(code);
      style.value = res.data;
    } catch {
      // 取不到方向对照只影响这一块，三集合清单照常展示
      style.value = null;
      failed.value = true;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true }
);

/**
 * 方向数据从哪里来：优先投顾侧（它决定了行数），我侧缺数据时整块走降级——
 * 只画一侧的条没有任何对照意义。
 */
const directions = computed(() => {
  const s = style.value;
  if (!s || s.mine.degraded) return [];
  return buildDirectionRows(s.advisor.directions, s.mine.directions);
});

const top2 = computed(() => mostDivergent(directions.value, 2));

/** 组合侧覆盖率 <100 时要说明缺口（缺箱体的基金权重） */
const advisorCoverage = computed(() => style.value?.advisor.coverage_pct);
const advisorMissing = computed(() => style.value?.advisor.missing ?? []);
const advisorAsOf = computed(() => style.value?.advisor.as_of_date ?? null);

const degradedHint = computed(() =>
  failed.value || style.value?.mine.degraded
    ? "你的持仓风格暂时取不到，方向对照稍后再看"
    : "该组合暂无风格暴露数据，无法做方向对照"
);
</script>

<template>
  <CardBlock class="advisor-compare">
    <SectionHeader
      title="与我账户的对照"
      info="按基金最近一期的风格暴露归类；组合按披露权重、我的持仓按市值加权。"
    />

    <p v-if="loading" class="advisor-compare__hint">正在读取方向对照…</p>

    <!-- 方向对照：两侧缺一侧就没有对照意义，整块降级而不是画半张图 -->
    <p v-else-if="!directions.length" class="advisor-compare__hint">
      {{ degradedHint }}
    </p>

    <AdvisorDirectionBars
      v-else
      :rows="directions"
      :top2="top2"
      :coverage-pct="advisorCoverage"
      :missing="advisorMissing"
      :as-of-date="advisorAsOf"
    />

    <!-- 三集合：具体差哪几只。这层与方向口径无关，方向取不到时照常展示 -->
    <AdvisorOverlapChips :comparison="comparison" />

    <p
      v-if="comparison?.advisor.degraded || comparison?.mine.degraded"
      class="advisor-compare__hint"
    >
      部分持仓暂时取不到，对比结果可能不完整
    </p>

    <p v-if="comparison?.caveats.length" class="advisor-compare__caveats">
      {{ comparison.caveats.join(" ") }}
    </p>
  </CardBlock>
</template>

<style scoped lang="scss">
.advisor-compare__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.advisor-compare__caveats {
  padding-top: var(--space-3);
  margin: var(--space-4) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
  border-top: 1px solid var(--border-light);
}
</style>
