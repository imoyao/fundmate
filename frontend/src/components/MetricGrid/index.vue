<!--
  MetricGrid · 指标卡容器（组件级设计约束，详见 frontend/design.md）
  - auto-fit 栅格等宽分列：末行条目不足时留空列，不再把剩余卡拉成 2 倍宽（#3272）
  - featured 卡跨 2 列，普通卡各占 1 列
  - 窄屏自动减列，手机档每行一张

  历史说明：本组件曾声明 `columns` prop，但 template 与 style 从未读取它——列数语义、
  最小卡宽、响应式断点全部写死在下方样式里。docs/design/components.md 一度把它写成
  「每层 MetricGrid 必须 :columns="12"」（#1506），属纸面约定。2026-09-16 删除该 prop，
  彻底消除「传了却什么都不发生」的假 API；需要列级控制请直接用 `--metric-basis` 或外层栅格。
-->
<template>
  <div class="metric-grid">
    <slot />
  </div>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* ⚠️ 顺序即语义：下面两条响应式块**必须留在基础声明 `--metric-basis` 之后**。
   媒体查询不改变特异性，同特异性下后写的规则胜出——2026-09-18（#1576）之前，
   这两块排在基础规则 `.metric-grid { --metric-basis: 200px }` **之前**，于是
   `--metric-basis` 在 320~1920 全档实测恒为 200px，`240px` / `100%` 两档从未生效。
   断点值一律走 `_breakpoints.scss` 单一来源（`scripts/guard_breakpoints.py`
   拦截裸值），且 mixin 编译产物就是 @media —— `stylelint --fix` 若把它挪到
   声明之前，会再次把覆盖改死，见 `stylelint.config.js` 的 `order/order` 注解。 */

.metric-grid {
  --metric-basis: 200px;

  /* #3272：原 flex + flex-grow 把末行余量全摊给当前行，2 张卡会被拉成 3 张卡
     那么宽。改 grid 后每列等宽，末行不足时右侧留空列；min() 兜底保证容器
     比 basis 还窄时只有一列，不横向溢出。 */
  display: grid;
  grid-template-columns: repeat(
    auto-fit,
    minmax(min(var(--metric-basis), 100%), 1fr)
  );
  gap: var(--space-compact);
  align-items: stretch;

  /* 供下方 @container 判断「容器是否放得下 2 列」，见 featured 卡注释。 */
  container-name: metric-grid;
  container-type: inline-size;

  /* 窄屏提高最小卡宽（原写 960px，2026-09-18 起对齐 Tailwind `lg` = 1024px：
     本仓断点已收口为 Tailwind v4 同阈值，#1571 决策） */
  @include bp.below("lg") {
    --metric-basis: 240px;
  }

  /* 手机档：单卡占满一行（原写 560px，对齐 Tailwind `sm` = 640px） */
  @include bp.below("sm") {
    --metric-basis: 100%;
  }
}

/* 普通卡宽度由栅格轨道决定，不再需要子项 flex/min-width 兜底。
   featured 跨 2 列；只有一列可跨时必须收回 span 1——否则 auto-fit 会
   为这个 span 硬挤出第 2 列，把普通卡压成 0 宽（实测 400px 容器下
   得到 392px + 0px 两列）。两条回退各管一半：
   - 手机档视口：--metric-basis 为 100%，本来只有一列；
   - 容器查询：宽视口里的窄容器（如侧栏 / 弹窗），仅看视口判不出来。
     496px = 2 × 240px（lg 以下最大 basis）+ 16px（--space-compact），
     容器比它窄就必然放不下两列。 */
:deep(.metric-card--featured),
:deep(.gauge-card--featured) {
  grid-column: span 2;

  @include bp.below("sm") {
    grid-column: span 1;
  }
}

@container metric-grid (max-width: 496px) {
  :deep(.metric-card--featured),
  :deep(.gauge-card--featured) {
    grid-column: span 1;
  }
}
</style>
