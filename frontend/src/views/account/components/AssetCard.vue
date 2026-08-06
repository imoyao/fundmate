<template>
  <div
    class="bg-white dark:bg-gray-800 rounded-lg shadow p-4 flex items-center justify-between"
  >
    <div>
      <p class="text-sm text-gray-500 dark:text-gray-400">{{ type }}</p>
      <p class="text-xl font-bold text-gray-900 dark:text-white">{{ value }}</p>
    </div>
    <div
      :class="[
        change >= 0 ? 'text-green-500' : 'text-red-500',
        'text-sm font-semibold'
      ]"
    >
      {{ change >= 0 ? "+" : "" }}{{ change }}%
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  type: {
    type: String,
    required: true
  },
  value: {
    type: String,
    required: true
  },
  change: {
    type: Number,
    required: true
  }
});
</script>

<style scoped>
/* 可以添加一些组件特有的样式 */
</style>
