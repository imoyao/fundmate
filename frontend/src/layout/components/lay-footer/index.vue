<!--
  AppFooter · 全站统一页脚（布局级）
  极简版（#1281 第五轮，2026-09-05）：与左侧边栏折叠区 left-collapse 同高（40px）。
  法律底栏（免责 / 版权 / 系统状态 / 开源致谢）统一下沉到 SiteLegalBar（footer 去耦），
  本组件只负责布局容器，避免与页面级 PageFooter 重复维护同一份文案。
  通过 v-if="show" 控制，避免登录/错误页误挂。
-->
<template>
  <footer v-if="show" class="app-footer">
    <div class="app-footer__inner">
      <SiteLegalBar :acknowledgement-href="ACK_URL" />
    </div>
  </footer>
</template>

<script setup lang="ts">
import SiteLegalBar from "@/components/SiteLegalBar/index.vue";

// 全站「开源致谢」外链（单一来源，经 SiteLegalBar 渲染）
const ACK_URL = "https://docs.duoduobei.com/acknowledgements/";

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
  color: var(--text-tertiary-ink);
  background: var(--bg-page);
  border-top: 1px solid var(--border-light);

  &__inner {
    display: flex;
    align-items: center;
    justify-content: center;
    max-width: var(--layout-shell-width);
    min-height: 40px;
    padding: 0 var(--space-12);
    margin: 0 auto;
  }
}
</style>
