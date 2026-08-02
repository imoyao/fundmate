<!--
  AppFooter · 全站统一页脚（布局级）
  简单提醒条：不采用三栏式，仅保留免责声明与版权，简洁克制（design.md 文案基调）
  通过 v-if="show" 控制，避免登录/错误页误挂
-->
<template>
  <footer v-if="show" class="app-footer">
    <div class="app-footer__inner">
      <p class="app-footer__disclaimer">
        市场有风险，投资需谨慎。本平台内容仅供参考，不构成任何投资建议。
      </p>
      <p class="app-footer__copyright">© 2026 多倍贝 · 让投资更从容</p>
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
/* 背景同色收尾：与页面底色一致，避免色块割裂（design.md） */
.app-footer {
  margin-top: var(--space-standard);
  background: var(--bg-page);
  border-top: 1px solid var(--border-light);
  color: var(--text-tertiary);

  &__inner {
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px var(--space-12);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    text-align: center;
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
}

@media (max-width: 720px) {
  .app-footer__inner {
    align-items: flex-start;
    text-align: left;
  }
}
</style>
