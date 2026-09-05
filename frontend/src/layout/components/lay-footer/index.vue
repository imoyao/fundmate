<!--
  AppFooter · 全站统一页脚（布局级）
  极简版（#1281 第五轮，2026-09-05）：与左侧边栏折叠区 left-collapse 同高（40px），
  收敛为「合规 + 版权 + 开源致谢」一行品牌记忆点，去掉单独的品牌韵脚行（该韵脚已上移至
  navbar 品牌区）。同时把所有页面（含 watchlist）的页脚高度统一，避免之前 self-page
  内自定义页脚导致的跨页面不一致。
  通过 v-if="show" 控制，避免登录/错误页误挂。
-->
<template>
  <footer v-if="show" class="app-footer">
    <div class="app-footer__inner">
      <p class="app-footer__disclaimer">
        市场有风险，投资需谨慎。本平台内容仅供参考，不构成任何投资建议。
      </p>
      <p class="app-footer__copyright">
        © 2026 多多贝 ·
        <a
          href="https://docs.duoduobei.com/acknowledgements/"
          target="_blank"
          rel="noopener noreferrer"
          class="app-footer__link"
          >开源致谢</a
        >
      </p>
    </div>
  </footer>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    show?: boolean;
  }>(),
  { show: true }
);
</script>

<style lang="scss" scoped>
.app-footer {
  /* 高度与左侧边栏折叠区（left-collapse 40px）同高——底部视觉一条水平线；
     用 min-height 而非固定 height 防止内部内容（长链接/换行）溢出 */
  min-height: 40px;
  color: var(--text-tertiary);
  background: var(--bg-page);
  border-top: 1px solid var(--border-light);

  &__inner {
    display: flex;
    flex-flow: row wrap;
    gap: 4px 16px;
    align-items: center;
    justify-content: center;
    max-width: 1400px;
    min-height: 40px;
    padding: 0 var(--space-12);
    margin: 0 auto;
    text-align: center;
  }

  &__disclaimer,
  &__copyright {
    margin: 0;
    font-size: 12px;
    line-height: 1;
    color: var(--text-tertiary);
    white-space: nowrap;
  }

  &__link {
    color: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;

    &:hover {
      color: var(--text-primary);
    }
  }
}

/* 窄屏：两段回到垂直排版，避免被挤换行错位 */
@media (width <= 720px) {
  .app-footer__inner {
    flex-direction: column;
    gap: 4px;
    padding: 8px var(--space-12);
  }
}
</style>
