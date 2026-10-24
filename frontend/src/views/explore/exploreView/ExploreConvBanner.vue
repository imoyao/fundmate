<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";

/**
 * 匿名用户转化区（#822 todo1 / #1546 T2.2，2026-10 拆分自 views/explore/index.vue）。
 *
 * 位置在观察列表**之后**：访客先看目的内容，再看注册转化。
 * 组件只负责「长什么样」，点了往哪跳由页面决定。
 */
const emit = defineEmits<{ (e: "login"): void }>();
</script>

<template>
  <section class="conv-banner">
    <div class="conv-banner__inner">
      <div class="conv-banner__text">
        <div class="conv-banner__title">免费注册，解锁完整投资账本</div>
        <div class="conv-banner__desc">
          注册后观察列表跨设备同步，并可在自选页管理分组、标签与 AI
          批量导入——当前为本地临时观察，清除浏览器数据会丢失。
        </div>
      </div>
      <el-button type="primary" @click="emit('login')">
        立即注册 / 登录
        <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
      </el-button>
    </div>
  </section>
</template>

<style lang="scss" scoped>
/* ============================================================
   匿名用户注册转化区（#822 todo1）
   ============================================================ */
.conv-banner {
  max-width: var(--layout-content-width);
  padding: 0 24px 16px;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 20px;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px;
    background: linear-gradient(135deg, var(--brand-100), var(--bg-card));
    border: 1px solid var(--brand-400);
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
}
</style>
