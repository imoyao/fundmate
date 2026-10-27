<script setup lang="ts">
/**
 * 计数行（#980 拆分）。
 *
 * 总数与表同屏、不藏脚注：首版的静默截断让用户以为「这就是全部」（#2160）。
 * 有更多时才提示「最近 10 条」，否则「共 N 条」本身就是完整信息。
 */
defineProps<{
  total: number;
  previewSize: number;
  /** 总量超过折叠态才提示「当前显示最近 N 条」 */
  needToggle: boolean;
  expanded: boolean;
}>();
</script>

<template>
  <p class="transaction-section__count">
    共 {{ total }} 条
    <span v-if="needToggle && !expanded">
      （当前显示最近 {{ previewSize }} 条）
    </span>
  </p>
</template>

<style lang="scss" scoped>
@use "./transaction-base";
</style>
