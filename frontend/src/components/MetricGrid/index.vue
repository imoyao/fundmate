<!--
  MetricGrid · 指标卡容器（组件级设计约束，详见 frontend/design.md）
  - 用 flex 均匀填充：无论放几个卡片都均衡铺满整行，不出现"挤在左边"
  - featured 卡占更大比例（约 2 倍），普通卡等比拉伸
  - 窄屏自动换行

  历史说明：本组件曾声明 `columns` prop，但 template 与 style 从未读取它——列数语义、
  最小卡宽、响应式断点全部写死在下方样式里。docs/design/components.md 一度把它写成
  「每层 MetricGrid 必须 :columns="12"」（#1506），属纸面约定。2026-09-16 删除该 prop，
  彻底消除「传了却什么都不发生」的假 API；需要列级控制请直接用 flex basis 或外层栅格。
-->
<template>
  <div class="metric-grid">
    <slot />
  </div>
</template>

<style lang="scss" scoped>
/* 响应式：窄屏提高最小宽度占比 */
@media (width <= 960px) {
  .metric-grid {
    --metric-basis: 240px;
  }
}

@media (width <= 560px) {
  .metric-grid {
    --metric-basis: 100%;
  }

  :deep(.metric-card),
  :deep(.gauge-card),
  :deep(.explore-actions-card),
  :deep(.metric-card--featured),
  :deep(.gauge-card--featured) {
    flex: 1 1 100%;
    min-width: 100%;
  }
}

.metric-grid {
  --metric-basis: 200px;

  display: flex;
  flex-wrap: wrap;
  gap: var(--space-compact);
  align-items: stretch;
}

/* 普通卡：等比拉伸填满，最小宽度 200px */
:deep(.metric-card),
:deep(.gauge-card),
:deep(.explore-actions-card) {
  flex: 1 1 var(--metric-basis);
  min-width: var(--metric-basis);
}

/* featured 卡：占约 2 倍宽度 */
:deep(.metric-card--featured),
:deep(.gauge-card--featured) {
  flex: 2 1 calc(var(--metric-basis) * 2);
  min-width: calc(var(--metric-basis) * 1.6);
}
</style>
