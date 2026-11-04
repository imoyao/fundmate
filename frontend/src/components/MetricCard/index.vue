<!--
  MetricCard · 指标卡（组件级设计约束，详见 frontend/design.md）
  - 统一「标题 / 大数字+小单位+等级标签 / 副文案」结构
  - 数字大、单位小的层级由组件保证，调用方只传数据
  props:
    - title: 指标名（如「股债性价比」）
    - value: 主数字（number | string | null）
    - unit:  单位/符号（如 "%"、"亿"、"°"），默认小字，与大数字同行
    - level: 等级文案，传给 TemperatureLevelBadge（如 "偏低"/"正常"）
    - caption: 副文案（如更新时间、说明）
    - featured: 放大主数字（用于核心指标）
    - valueColor: 主数字颜色覆盖（可选，默认 --text-primary；见 props JSDoc 的取舍说明）
    - loading/empty 状态由调用方控制，这里只负责空值展示 "--"
-->
<template>
  <div class="metric-card" :class="{ 'metric-card--featured': featured }">
    <div class="metric-card__title-row">
      <span class="metric-card__title">{{ title }}</span>
      <TemperatureLevelBadge
        v-if="level"
        :level="level"
        :size="featured ? 'md' : 'sm'"
        class="metric-card__badge"
      />
    </div>

    <div class="metric-card__body">
      <span
        class="metric-card__value"
        :style="valueColor ? { color: valueColor } : undefined"
        >{{ displayValue }}</span
      >
      <span v-if="unit" class="metric-card__unit">{{ unit }}</span>
    </div>

    <div v-if="caption" class="metric-card__caption">{{ caption }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";

const props = withDefaults(
  defineProps<{
    title?: string;
    value?: number | string | null;
    unit?: string;
    level?: string;
    caption?: string;
    featured?: boolean;
    /**
     * 主数字颜色，默认 `--text-primary`（中性暖黑）。
     *
     * ⚠️ 不改默认值是刻意的：MetricCard 是跨页共用组件，直接把默认色换成品牌色
     * 会一次性改写全部调用方的观感，属于「改一个组件、动整站」的连坐式变更。
     * 需要品牌色（如智能分析页的主数字）的调用方显式传 `var(--brand-ink)` 即可——
     * 该令牌是**文字级**品牌色（白底 5.86:1，达 WCAG AA），而 `--brand-700`
     * 作文字仅 3.73:1，不要用后者。
     */
    valueColor?: string;
  }>(),
  {
    title: "",
    value: null,
    unit: "",
    level: "",
    caption: "",
    featured: false,
    valueColor: ""
  }
);

const displayValue = computed(() => {
  const v = props.value;
  return v !== null && v !== undefined && v !== "" ? v : "--";
});
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 112px;
  padding: 20px;

  /* 自响应字号的前提（2026-11-02）：卡片宽度由 MetricGrid 的 flex 决定，
     但**数字该多大**取决于卡片自己能分到多少宽，容器查询正好表达这件事。
     没有它时，180px 的卡放 `¥747,676`（30px 等宽数字约 150px）必然撑破内容区。 */
  container-type: inline-size;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease;

  &:hover {
    box-shadow: var(--shadow-float);
    transform: translateY(-3px);
  }

  /* 标题行：标题 + 等级标签 横排 */
  &__title-row {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }

  &__title {
    font-size: var(--text-label);
    font-weight: 500;
    line-height: 1.4;
    color: var(--text-secondary);
  }

  /* 数字与单位必须**同排**：原来允许换行，卡一窄就把 `%` 甩到下一行，
     金额更惨 —— `+¥477,707` 会在「+」后面断开，变成「+」独占一行。
     这一类断行不是数据问题，是 flex 容器允许折行给的假许可。 */
  &__body {
    display: flex;
    flex-wrap: nowrap;
    gap: 6px;
    align-items: baseline;
    margin-top: auto;
  }

  &__value {
    font-family: var(--font-mono);

    /* 14cqi ≈ 卡宽的 14%：188px 的卡得 26px（9 位金额刚好放得下），
       宽卡到 32px 封顶、featured 另有 40px 上限，窄屏不再需要单独缩字号。 */
    font-size: clamp(1.125rem, 14cqi, var(--text-display));
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
    color: var(--text-primary);
    letter-spacing: -0.5px;

    /* 金额之间没有空格，浏览器却会在「+ / ¥ / 数字」这类前缀符号后给出断点
       （UAX #14 的 PR/IL 类），必须显式禁止——否则「+¥477,707」被拆成两行。 */
    white-space: nowrap;
  }

  &__unit {
    flex-shrink: 0;
    font-size: var(--text-num-strong);
    font-weight: 500;
    color: var(--text-tertiary-ink);
  }

  &__badge {
    flex-shrink: 0;
  }

  &__caption {
    font-size: var(--text-label);

    /* 1.4 → 1.55：两行副文案贴太紧时像一段被压扁的注释，行距是「呼吸感」的主要来源 */
    line-height: 1.55;
    color: var(--text-tertiary-ink);
    word-break: keep-all;

    /* balance：让两行长度接近，避免「当前市值 − 净投入（含已实 / 现）」这种
       把词拆开的断法。
       keep-all：中文默认**任意两字之间**都能断行，于是「净投 / 入」这种把一个词
       劈成两半的断法随时会出现；keep-all 只在空格/标点处断（本仓副文案基本都带
       `−`、`×` 两侧的空格，天然给了断点）。
       anywhere 兜底：万一某条文案没有可用断点（长串无空格），退化为硬断，
       宁可断词也不横向溢出卡片。 */
    text-wrap: balance;
    overflow-wrap: anywhere;
  }

  /* featured：核心指标放大 */
  &--featured {
    min-height: 136px;
    padding: 22px 24px;

    .metric-card__value {
      font-size: clamp(1.75rem, 13cqi, var(--text-display-lg));
    }

    .metric-card__unit {
      font-size: var(--text-num-strong);
    }
  }
}

/* ============================================================
   MetricCard 样式 · 单一来源：frontend/design.md
   卡片：--bg-card / --radius-lg / --shadow-raised / --border-light
   结构：标题行(标题 + 等级标签) → 大数字 + 小单位 → 副文案
   数字：30px(默认) / 40px(featured)，单位 18px
   ============================================================ */

/* ⚠️ 原「@media (width <= 480px) 缩小数字字号」整块已删（2026-11-02）：
   它是按**视口**给卡片内数字定字号，而卡片宽度由 MetricGrid 的 flex 决定——
   窄视口下卡片常常变成单列**更宽**，此时把数字压到 24px 与直觉相反（这正是
   #1576 当年给这块补注释却仍别扭的原因）。现由 `.metric-card__value` 上的
   容器查询 clamp(...cqi...) 负责：跟着**卡片自身宽度**缩放，比视口阈值准。 */
</style>
