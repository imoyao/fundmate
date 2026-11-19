<script setup lang="ts">
// 交易流水 · 空态（设计 §十二-1 / design.md「空状态与加载态」）。
//
// 严禁干瘪的「暂无数据」：用珊瑚红单色细线鹦鹉螺插画作为视觉锚点，
// 文案直接说明「为什么会空」与「下一步做什么」。插画复用仓库既有资产
// assets/login/nautilus-light.svg（单色 #E34F38 线稿），不新增依赖、不引入 emoji。
//
// 表格视图与时间线视图共用：两处空态的文案一致，抽成一个组件避免漂移。
import nautilus from "@/assets/login/nautilus-light.svg";

defineOptions({ name: "TransactionEmptyState" });
</script>

<template>
  <div class="txn-empty">
    <img class="txn-empty__art" :src="nautilus" alt="" aria-hidden="true" />
    <p class="txn-empty__title">没有符合条件的流水</p>
    <p class="txn-empty__hint">
      当前筛选下没有任何记录。放宽时间范围，或清空筛选重新看。
    </p>
  </div>
</template>

<style scoped>
/* 品牌呼吸动效（design.md：6-8s scale 呼吸，与 RoadEmptyState 同款节奏） */
@keyframes txn-empty-breathe {
  0%,
  100% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.03);
  }
}

.txn-empty {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  padding: var(--space-section) 24px;
  text-align: center;
}

.txn-empty__art {
  width: 168px;
  height: auto;
  margin-bottom: 8px;
  opacity: 0.9;
  animation: txn-empty-breathe 7s ease-in-out infinite;
}

.txn-empty__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.txn-empty__hint {
  max-width: 420px;
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}

/* 尊重系统的「减弱动态效果」：呼吸动画压掉（顶层 @media 保证声明不被基础规则覆盖） */
@media (prefers-reduced-motion: reduce) {
  .txn-empty__art {
    animation: none;
  }
}
</style>
