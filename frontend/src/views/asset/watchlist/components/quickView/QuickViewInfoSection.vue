<script setup lang="ts">
import { formatDate } from "@/utils/date";
import type { WatchlistItem } from "@/api/watchlist";

defineProps<{
  item: WatchlistItem;
  groupText: string;
  tagText: string;
}>();
</script>

<template>
  <section class="wqv-sec">
    <h4 class="wqv-sec__title">信息</h4>
    <dl class="wqv-list">
      <div class="wqv-row">
        <dt class="wqv-label">添加自选日</dt>
        <dd class="wqv-value">
          {{ item.created_at ? formatDate(item.created_at) : "—" }}
        </dd>
      </div>
      <div class="wqv-row">
        <dt class="wqv-label">所属分组</dt>
        <dd class="wqv-value">{{ groupText }}</dd>
      </div>
      <div class="wqv-row">
        <dt class="wqv-label">标签</dt>
        <dd class="wqv-value">{{ tagText }}</dd>
      </div>
    </dl>
  </section>
</template>

<style scoped lang="scss">
@use "./wqv-base";
</style>
