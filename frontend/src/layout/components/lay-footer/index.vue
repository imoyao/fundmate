<!--
  AppFooter · 全站统一页脚（布局级）
  简洁克制：品牌韵脚收束（brand-v1.7 §2）+ 合规免责 + 版权（含开源致谢入口，指向
  docs 站 /acknowledgements，承担 MiSans/Inter 等第三方署名义务）
  通过 v-if="show" 控制，避免登录/错误页误挂
-->
<template>
  <footer v-if="show" class="app-footer">
    <div class="app-footer__inner">
      <p class="app-footer__brand">
        多多贝，贝倍多——复利生长，越理越多。
      </p>
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
@media (width <= 720px) {
  .app-footer__inner {
    align-items: flex-start;
    text-align: left;
  }
}

.app-footer {
  margin-top: var(--space-standard);
  color: var(--text-tertiary);
  background: var(--bg-page);
  border-top: 1px solid var(--border-light);

  &__inner {
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: center;
    max-width: 1400px;
    padding: 24px var(--space-12);
    margin: 0 auto;
    text-align: center;
  }

  /* 品牌韵脚收束（brand-v1.7 §2）：页脚品牌记忆点，克制不喧宾夺主 */
  &__brand {
    margin: 0;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.02em;
    color: var(--text-secondary);
  }

  &__disclaimer {
    margin: 0;
    font-size: 12px;
    line-height: 1.6;
  }

  &__copyright {
    margin: 0;
    font-size: 12px;
    color: var(--text-tertiary);
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

/* 背景同色收尾：与页面底色一致，避免色块割裂（design.md） */
</style>
