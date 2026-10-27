<!--
  StatusBanner · 系统状态页顶部整体横幅（#980 批 B9 从 `views/status/index.vue` 抽出）

  与骨架屏是同一个 `v-if / v-else` 对：`banner` 为 null（还没拿到数据、也没报错）时
  出骨架屏，否则出横幅。把两者放在同一个组件里，是为了避免父级只搬横幅、把
  `v-else` 落在页面上——那样「加载中」会变成一片空白而不是骨架屏。
-->
<template>
  <section
    v-if="banner"
    class="status-banner"
    :class="`status-banner--${banner.tone}`"
  >
    <IconifyIconOffline :icon="banner.icon" class="status-banner__icon" />
    <div class="status-banner__text">
      <p class="status-banner__title">{{ banner.title }}</p>
      <p v-if="banner.desc" class="status-banner__desc">
        {{ banner.desc }}
      </p>
      <p class="status-banner__meta">
        <template v-if="updatedAt">检查于 {{ updatedAt }}</template>
      </p>
    </div>
    <el-button
      v-if="errorMessage"
      :loading="loading"
      size="small"
      @click="emit('retry')"
    >
      重试
    </el-button>
  </section>
  <el-skeleton v-else :rows="2" animated />
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
import type { BannerModel } from "./statusModel";

defineOptions({ name: "StatusBanner" });

defineProps<{
  /** null = 既没数据也没报错（首屏取数中）→ 骨架屏 */
  banner: BannerModel | null;
  loading: boolean;
  errorMessage: string;
  /** 最近一次检查时刻（HH:mm:ss），空串时不渲染这一行 */
  updatedAt: string;
}>();

const emit = defineEmits<{ retry: [] }>();
</script>

<style lang="scss" scoped>
.status-banner {
  display: flex;
  gap: var(--space-compact);
  align-items: center;
  padding: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left-width: 4px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);

  /* 点色直接用语义色（图形，非文字）；文字另用 *-ink 档保证对比度 */
  &--ok {
    border-left-color: var(--color-success);
  }

  &--warn {
    border-left-color: var(--color-warning);
  }

  &--error {
    border-left-color: var(--color-danger);
  }

  &__icon {
    flex: 0 0 auto;
    font-size: var(--text-display);
  }

  &--ok &__icon {
    color: var(--color-success);
  }

  &--warn &__icon {
    color: var(--color-warning-ink);
  }

  &--error &__icon {
    color: var(--color-danger);
  }

  &__text {
    flex: 1 1 auto;
    min-width: 0;
  }

  &__title {
    margin: 0;
    font-size: var(--text-num-strong);
    font-weight: 600;
    line-height: 1.4;
    color: var(--text-primary);
  }

  &__desc {
    margin: 4px 0 0;
    font-size: var(--text-small);
    line-height: 1.5;
    color: var(--text-secondary);
  }

  &__meta {
    margin: 4px 0 0;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }
}
</style>
