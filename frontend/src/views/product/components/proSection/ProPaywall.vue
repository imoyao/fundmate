<script setup lang="ts">
/**
 * Pro 付费墙遮罩（#980 拆分）。
 *
 * 只遮内容区不遮标题，且不阻断详情页其他区块——「克制不打扰」（#994 付费墙交互）。
 * `position: absolute` 相对父级 `.pro-section__body`（`position: relative` 在父页）。
 *
 * 关于毛玻璃（#2319）：这里**刻意不用 backdrop-filter**。design.md 的红线是
 * 「Glass 毛玻璃仅限全局浮窗」，全站唯一合法用法在 style/index.scss 的全局浮窗层；
 * 付费墙是贴住卡片内容区的绝对定位遮罩，不是浮窗，用毛玻璃即违规。原 blur(2px)
 * 叠在 86% 实底之上肉眼几乎不可感知——既没拿到质感，又留下一个每次严格审计都会
 * 命中的违规点。去掉后把不透明度提到 92% 补偿失去的模糊分离感。
 */
</script>

<template>
  <div class="pro-paywall">
    <p class="pro-paywall__title">解锁高级风险指标与交易行为分析</p>
    <p class="pro-paywall__desc">
      升级至 Pro 版，持续获得归因、风险与配置洞察。
    </p>
    <button
      class="pro-paywall__cta"
      type="button"
      disabled
      title="升级通道随付费体系建设后开放"
    >
      升级 Pro
    </button>
  </div>
</template>

<style scoped>
/* 付费墙遮罩：贴住内容区（不遮 SectionHeader），高不透明度实底
   （#2319）去掉 backdrop-filter，理由见上。 */
.pro-paywall {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg-card) 92%, transparent);
  border-radius: var(--radius-md);
}

.pro-paywall__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.pro-paywall__desc {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.pro-paywall__cta {
  padding: var(--space-1) var(--space-4);
  font-size: var(--text-label);
  color: var(--text-inverse);
  cursor: not-allowed;

  /* #1600 实底阶梯：--brand-700 白字 3.86:1 不达 AA，实底一律走 --brand-solid（800） */
  background: var(--brand-solid);
  border: none;
  border-radius: var(--radius-sm);
  opacity: 0.6;
}
</style>
