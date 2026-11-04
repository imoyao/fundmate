<!--
  RoadCardHead · 未竟之蹊卡片的三行身份信息（#980 批 B6 从 `RoadCard.vue` 抽出）

  标题 → 代码（交易所 / 资产类别）→ 元信息（状态 / 关注天数 / 标记日期）。

  独立成组件而不是并进 `RoadCardMetrics`：这三行在**编辑态也显示**，
  而指标条只在浏览态显示。放在同一个组件里就得给它一个 `editing` prop
  去做 `v-if` 分段，反而把「什么态显示什么」这件事实藏进组件内部。
-->
<template>
  <h3 class="road-title" :title="title">{{ title }}</h3>
  <p class="road-code">
    {{ symbol }}
    <template v-if="venue"> · {{ venue }}</template>
    <template v-if="assetType"> · {{ assetType }}</template>
  </p>
  <p class="road-meta">
    <span>{{ stateLabel }}</span>
    <template v-if="favoriteDays != null">
      · 关注 {{ favoriteDays }} 天</template
    >
    <template v-if="favoriteAt"> · 标记于 {{ favoriteAt }}</template>
  </p>
</template>

<script setup lang="ts">
defineOptions({ name: "RoadCardHead" });

defineProps<{
  title: string;
  symbol: string;
  /** 交易所文案；空串省掉这一段 */
  venue: string;
  /** 资产类别中文标签；空串省掉这一段 */
  assetType: string;
  stateLabel: string;
  /** 关注天数；null = 日期缺失或非法，省掉这一段 */
  favoriteDays: number | null;
  /** 标记日期原文（后端字符串，不在前端重新格式化） */
  favoriteAt: string | null;
}>();
</script>

<style scoped>
.road-title {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-body);
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
  white-space: nowrap;
}

.road-code {
  margin-top: 2px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.road-meta {
  margin-top: 6px;
  font-size: var(--text-label);
  color: var(--text-secondary);
}
</style>
