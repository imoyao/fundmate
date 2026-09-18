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
/* ⚠️ 已知缺陷（#1571 实测发现，修复单独立项，勿在此 PR 顺手改）：
   下面两条 @media 目前是**死代码**——它们排在基础规则 `.metric-grid
   { --metric-basis: 200px }` **之前**，而媒体查询不改变特异性，同特异性下
   后写的规则胜出，故 `--metric-basis` 在 320~1920 全档实测恒为 200px，
   240px / 100% 两档从未生效。修好它们会改变 320~960 档的每行卡片数
   （属视觉变更，按 #1548 口径应单独成一个 PR）。
   本次只对「写死的 min-width 可能大于容器」做兜底，不触碰级联顺序。 */

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

/* 普通卡：等比拉伸填满，最小宽度 200px。
   min-width 用 min(..., 100%) 兜底：容器比 --metric-basis 还窄时（320 视口下
   网格仅 272px），写死的下限会把卡片撑出容器 → 文档横向溢出。容器够宽时
   min() 取前者，计算值与原先逐字相同（视觉零变化）。 */
:deep(.metric-card),
:deep(.gauge-card),
:deep(.explore-actions-card) {
  flex: 1 1 var(--metric-basis);
  min-width: min(var(--metric-basis), 100%);
}

/* featured 卡：占约 2 倍宽度。
   同理加 100% 上限。此处是 #1571 实测到的**真实溢出源**：320 视口下
   --metric-basis 计算值为 200px（原因见上方死代码说明），200 × 1.6 = 320px
   > 网格 272px，卡片右侧顶出视口 24px。 */
:deep(.metric-card--featured),
:deep(.gauge-card--featured) {
  flex: 2 1 calc(var(--metric-basis) * 2);
  min-width: min(calc(var(--metric-basis) * 1.6), 100%);
}
</style>
