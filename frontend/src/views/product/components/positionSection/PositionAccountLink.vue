<script setup lang="ts">
/**
 * 账户名（#980 拆分产物）。
 *
 * 单账户网格与多账户表格都用它，所以单独成组件：`.product-position__account`
 * 那套餐链接样式只写一遍。若两边各写一份，scoped 会把同一份声明编译成两份，
 * 样式单一来源当场失效。
 */
defineProps<{
  name: string;
  /** 未归档持仓为 null：**没有落点**，渲染成只读文本而不是坏链 */
  ledgerId: number | null;
}>();
</script>

<template>
  <router-link
    v-if="ledgerId"
    class="product-position__account"
    :to="`/asset/ledgers/${ledgerId}`"
  >
    {{ name }}
  </router-link>
  <span
    v-else
    class="product-position__account product-position__account--plain"
  >
    {{ name }}
  </span>
</template>

<style lang="scss" scoped>
/* 账户名：可点击时给链接态，未归档持仓只读——那里没有落点，链过去是坏的 */
.product-position__account {
  font-weight: 500;
  color: var(--text-primary);
  text-decoration: none;
  border-bottom: 1px solid transparent;
}

.product-position__account:not(.product-position__account--plain):hover {
  color: var(--color-primary-ink);
  border-bottom-color: currentColor;
}

.product-position__account--plain {
  color: var(--text-primary);
  cursor: default;
}
</style>
