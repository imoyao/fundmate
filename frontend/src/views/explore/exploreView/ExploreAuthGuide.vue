<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";

/**
 * 已登录引导区（2026-10 拆分自 views/explore/index.vue）。
 *
 * 探市只做展示与观察，管理能力（分组、标签、AI 批量导入）收敛到登录后的自选页。
 * 这条提示可关闭且**关闭后永久生效**（localStorage，见页面的 AUTH_GUIDE_DISMISS_KEY），
 * 持久化本身留在页面——组件只负责把「关闭」这件事抛上去。
 */
const emit = defineEmits<{
  (e: "watchlist"): void;
  (e: "dismiss"): void;
}>();
</script>

<template>
  <section class="auth-guide">
    <div class="auth-guide__inner">
      <div class="auth-guide__text">
        <div class="auth-guide__title">已登录，可前往自选页管理资产</div>
        <div class="auth-guide__desc">
          探市页仅用于浏览市场数据；分组、标签、AI
          批量导入等功能已迁移至自选页统一管理。
        </div>
      </div>
      <div class="auth-guide__actions">
        <el-button type="primary" @click="emit('watchlist')">
          前往自选页
          <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
        </el-button>
        <button
          type="button"
          class="auth-guide__close"
          title="不再提示"
          aria-label="不再提示"
          @click="emit('dismiss')"
        >
          <IconifyIconOffline icon="ep:close" />
        </button>
      </div>
    </div>
  </section>
</template>

<style lang="scss" scoped>
/* ============================================================
   已登录引导区
   ============================================================ */
.auth-guide {
  max-width: var(--layout-content-width);
  padding: 0 24px 16px;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 20px;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px;
    background: var(--bg-card);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-raised);
  }

  &__title {
    font-size: var(--text-body);
    font-weight: 600;
    color: var(--text-primary);
  }

  &__desc {
    max-width: 860px;
    margin-top: 4px;
    font-size: var(--text-label);
    line-height: 1.6;
    color: var(--text-secondary);
  }

  &__actions {
    display: flex;
    flex-shrink: 0;
    gap: 8px;
    align-items: center;
  }

  &__close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    font-size: var(--text-body);

    /* audit-text-contrast: exempt 非文本图形（图标字形），按 WCAG 1.4.11 需 3:1，本令牌在页底 / 卡片底实测 3.57~3.69:1，达标；
       若改用 -ink 会与相邻正文同权，反而压平层级。登记见 docs/spec/tech-debt.md（#1586） */
    color: var(--text-tertiary);
    cursor: pointer;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    transition:
      color 0.15s ease,
      background 0.15s ease;

    &:hover {
      color: var(--text-primary);
      background: var(--bg-soft);
    }
  }
}
</style>
