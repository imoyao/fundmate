<!--
  WatchlistTableSkeleton · 自选表格骨架屏（分组切换/首屏加载时的专业占位）

  设计（2026-09-05，issue #1281 关联）：
  - 覆盖层方案：el-table 始终渲染（表头保留吸顶与列拖拽 DOM），本组件以绝对定位
    覆盖在「表头之下、表格剩余区域」，遮住 loading 期间的旧行/空态闪动，绘制与
    真实行等高的灰色骨架行——切换分组时看到的是「表头 + 行级骨架」而非空分组。
  - 列占位分布对齐真实表格列观感：产品列最宽（名称/代码 双行），中间为若干数值
    列，右侧操作列窄；不追求逐列精确，重在「行结构 + 呼吸节奏」不被打破。
  - 实现铁律（沿用 PageSkeleton）：纯 CSS 流光（GPU 合成），aria-hidden 屏蔽读屏；
    不挂 JS、不参与数据流，loading 结束由父组件 v-if 卸载。
  - 行高与真实行一致（52px，见 index.vue 行高覆盖说明），12 行铺满首屏视觉。
-->
<template>
  <div class="watchlist-table-skeleton" aria-hidden="true">
    <div v-for="row in 12" :key="row" class="wts-row">
      <div class="wts-row__cell wts-row__cell--product">
        <span class="wts-bar wts-bar--name" />
        <span class="wts-bar wts-bar--code" />
      </div>
      <div class="wts-row__cell wts-row__cell--num">
        <span class="wts-bar" />
      </div>
      <div class="wts-row__cell wts-row__cell--num">
        <span class="wts-bar" />
      </div>
      <div class="wts-row__cell wts-row__cell--num">
        <span class="wts-bar" />
      </div>
      <div class="wts-row__cell wts-row__cell--num">
        <span class="wts-bar" />
      </div>
      <div class="wts-row__cell wts-row__cell--num">
        <span class="wts-bar" />
      </div>
      <div class="wts-row__cell wts-row__cell--action">
        <span class="wts-bar wts-bar--dot" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 纯展示占位组件，无 props / 状态
</script>

<style scoped>
/* 覆盖层：绝对定位于 .watchlist-table-wrap（需在 index.vue 给该容器 position:relative），
   top 从表头底（约 30px，与真实表头高一致）开始，遮住表体/空态区而不盖表头。
   loading 结束卸载后表格原有 DOM 无缝露出。 */
.watchlist-table-skeleton {
  position: absolute;
  /* top 跟随真实表头高度：由父容器 .watchlist-table-wrap 的 --watchlist-header-h 提供（#1324 review），
     表头高度调整时覆盖层自动对齐，不再硬编码压住/露出。 */
  top: var(--watchlist-header-h, 30px);
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--bg-card);
}

/* 骨架行：flex:1 均分撑满覆盖层（12 行铺满可视区、无底部空白），
   min-height 兜底让行不塌成细条；真实行高 52px 只是自然分配结果，
   容器越高每行越接近真实行高，容器矮时均分略压但保持完整覆盖。
   左右留白与单元格一致（产品列 16px/其余 12px）。 */
.wts-row {
  display: flex;
  flex: 1 1 auto;
  min-height: 44px;
  /* 高屏下 flex 均分不会把行无限拉长，维持与真实行 ~52px 一致的骨架密度（#1324 review） */
  max-height: 52px;
  align-items: center;
  border-bottom: 1px solid var(--border-light);
}

/* 列占位：产品列最宽（左侧留白较大，视觉对齐首列），数值列等分，末列操作区最窄 */
.wts-row__cell {
  display: flex;
  flex-shrink: 0;
}

.wts-row__cell--product {
  flex-direction: column;
  gap: 6px;
  justify-content: center;
  width: 232px;
  min-width: 232px;
  padding-left: 16px;
}

.wts-row__cell--num {
  flex: 1;
  min-width: 0;
  justify-content: flex-end;
  padding-right: 12px;
}

.wts-row__cell--action {
  width: 120px;
  justify-content: center;
  padding-right: 12px;
}

/* 灰条：PageSkeleton 同款流光动画，1.8s 慢速、GPU 合成不占主线程 */
.wts-bar {
  display: block;
  height: 12px;
  background-color: var(--bg-soft);
  background-image: linear-gradient(
    90deg,
    var(--bg-soft) 25%,
    var(--bg-hover) 37%,
    var(--bg-soft) 63%
  );
  background-size: 400% 100%;
  border-radius: var(--radius-sm);
  animation: wts-wave 1.8s ease-in-out infinite;
}

.wts-row__cell--product .wts-bar {
  width: 60%;
}

.wts-row__cell--product .wts-bar--name {
  width: 70%;
  height: 14px;
}

.wts-row__cell--product .wts-bar--code {
  width: 42%;
  height: 10px;
}

.wts-row__cell--num .wts-bar {
  width: 60%;
  max-width: 96px;
}

.wts-row__cell--action .wts-bar--dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
}

@keyframes wts-wave {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}

/* 尊重系统「减少动效」偏好：无动画需求，骨架本就是静态占位（design.md Motion） */
@media (prefers-reduced-motion: reduce) {
  .wts-bar {
    animation: none;
  }
}
</style>
