<!--
  PageSkeleton · 页面骨架屏（强制复用，见 docs/design/components.md）
  - 模拟真实页面结构（概览指标卡 / 图表卡 / 表格行），作为内容占位容器，防布局偏移（CLS）。
  - 实现铁律（业界最佳实践）：
    1. 结构一致：形状/数量/宽度与真实内容布局高度一致，非装饰性条条；
    2. 轻量化：纯 CSS background 流光（GPU 加速），不占 JS 主线程，动画 1.8s 慢速；
    3. A11y：根节点 aria-hidden="true"，防止读屏软件朗读占位块；
    4. 阈值控制由使用方负责：请求 ≤200ms 返回时跳过骨架屏（见 detail.vue 示例）。
-->
<template>
  <div class="page-skeleton" aria-hidden="true">
    <!-- 概览指标卡 -->
    <div v-if="cards > 0" class="page-skeleton__cards">
      <div v-for="i in cards" :key="`card-${i}`" class="page-skeleton__card">
        <div class="page-skeleton__bar page-skeleton__bar--label" />
        <div class="page-skeleton__bar page-skeleton__bar--value" />
      </div>
    </div>

    <!-- 图表卡 -->
    <div v-if="chartCols > 0" class="page-skeleton__chart-row">
      <div
        v-for="i in chartCols"
        :key="`chart-${i}`"
        class="page-skeleton__card page-skeleton__card--chart"
      >
        <div class="page-skeleton__bar page-skeleton__bar--label" />
        <div class="page-skeleton__bar page-skeleton__bar--chart" />
      </div>
    </div>

    <!-- 表格卡 -->
    <div v-if="tableRows > 0" class="page-skeleton__card page-skeleton__table">
      <div class="page-skeleton__bar page-skeleton__bar--label" />
      <div
        v-for="i in tableRows"
        :key="`row-${i}`"
        class="page-skeleton__bar page-skeleton__bar--row"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 概览指标卡数量，默认 3 */
    cards?: number;
    /** 图表卡列数，默认 2 */
    chartCols?: number;
    /** 表格行数（占位行），默认 6 */
    tableRows?: number;
  }>(),
  { cards: 3, chartCols: 2, tableRows: 6 }
);
</script>

<style lang="scss" scoped>
.page-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-3) 0;

  /* 卡 / 图表 / 表 用同一 token 卡片语言（与 CardBlock / MetricCard 一致） */
  &__card {
    min-height: 104px;
    padding: var(--space-standard);
    background: var(--bg-card);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-raised);
  }

  &__cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-compact);

    @media (width <= 640px) {
      grid-template-columns: 1fr;
    }
  }

  &__chart-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-compact);

    @media (width <= 640px) {
      grid-template-columns: 1fr;
    }
  }

  &__card--chart {
    min-height: 260px;
  }

  &__table {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  /* 占位条：纯 CSS 流光（background-size 动画，GPU 合成，不占主线程），1.8s 慢速 */
  &__bar {
    height: 14px;
    background-color: var(--bg-soft);
    background-image: linear-gradient(
      90deg,
      var(--bg-soft) 25%,
      var(--bg-hover) 37%,
      var(--bg-soft) 63%
    );
    background-size: 400% 100%;
    border-radius: var(--radius-sm);
    animation: page-skeleton-wave 1.8s ease-in-out infinite;
  }

  &__bar--label {
    width: 40%;
    height: 18px;
  }

  &__bar--value {
    width: 55%;
    height: 24px;
    margin-top: var(--space-3);
  }

  &__bar--chart {
    width: 100%;
    height: 160px;
    margin-top: var(--space-3);
  }

  &__bar--row {
    width: 100%;
    height: 32px;
  }
}

@keyframes page-skeleton-wave {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}
</style>
