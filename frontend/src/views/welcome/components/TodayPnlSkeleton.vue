<!--
  TodayPnlSkeleton · 「最新收益」上半部（hero + 投资类资产 + 两列分项）的占位。

  为什么只占上半部：家庭口径那一层走 `/api/summary/`（实测约 60ms），
  而当日收益走 `/api/summary/today-pnl/`（热态 280~360ms、冷启动 1.5s，
  热点在共享的 pnl_calendar 引擎里）。以前整张卡被慢接口统一挡住，
  连毫秒级就到的数据也陪着空白——现在家庭三项立即显示，慢的部分才占位。

  200ms 阈值由 `useTodayPnl` 用 `useSkeletonThreshold` 统一控制：
  快请求连骨架都不渲染（避免闪屏），本组件在未点亮时只保留等高留白，
  保证骨架出现/消失都不引起布局跳动（CLS）。

  流光不自己写渐变：统一 `@include sk.wave-bar`（_skeleton.scss 单一来源，
  含 prefers-reduced-motion 降级与亮/暗双主题扫光带）。
-->
<template>
  <div class="today-skeleton" aria-hidden="true">
    <div v-if="!active" class="today-skeleton__reserve" />

    <template v-else>
      <div class="today-skeleton__head">
        <div class="today-skeleton__stack">
          <span class="bar bar--label" />
          <span class="bar bar--hero" />
          <span class="bar bar--sub" />
        </div>
        <div class="today-skeleton__stack today-skeleton__stack--right">
          <span class="bar bar--label bar--label-short" />
          <span class="bar bar--invested" />
          <span class="bar bar--ratio" />
        </div>
      </div>

      <span class="today-skeleton__rule" />

      <div class="today-skeleton__cols">
        <div v-for="i in 2" :key="i" class="today-skeleton__col">
          <span class="bar bar--label bar--label-short" />
          <div class="today-skeleton__value">
            <span class="bar bar--value" />
            <span class="bar bar--rate" />
          </div>
          <span class="bar bar--foot" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: "TodayPnlSkeleton" });

defineProps<{
  /** false = 200ms 阈值内，只保留等高留白、不渲染占位条 */
  active: boolean;
}>();
</script>

<style lang="scss" scoped>
@use "@/style/skeleton" as sk;

.today-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-standard);
}

.today-skeleton__reserve {
  min-height: 190px;
}

.today-skeleton__head {
  display: flex;
  gap: var(--space-5, 24px);
  align-items: flex-start;
  justify-content: space-between;
}

.today-skeleton__stack {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.today-skeleton__stack--right {
  flex: none;
  align-items: flex-end;
}

.today-skeleton__rule {
  height: 1px;
  background-color: var(--border-light);
}

.today-skeleton__cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.today-skeleton__col {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 0 var(--space-compact);
}

.today-skeleton__col:first-child {
  padding-left: 0;
}

.today-skeleton__col + .today-skeleton__col {
  border-left: 1px solid var(--border-subtle);
}

.today-skeleton__value {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.bar {
  display: block;

  @include sk.wave-bar;
}

/* 高度对齐真实字阶：label 12 / hero 57(视觉 44) / lg 24 / sm 14 */
.bar--label {
  width: 96px;
  height: 12px;
}

.bar--label-short {
  width: 72px;
}

.bar--hero {
  width: min(240px, 80%);
  height: 44px;
}

.bar--sub {
  width: min(190px, 70%);
  height: 12px;
}

.bar--invested {
  width: 150px;
  height: 24px;
}

.bar--ratio {
  width: 110px;
  height: 12px;
}

.bar--value {
  width: min(150px, 70%);
  height: 24px;
}

.bar--rate {
  width: 64px;
  height: 18px;
}

.bar--foot {
  width: min(170px, 80%);
  height: 14px;
}
</style>
