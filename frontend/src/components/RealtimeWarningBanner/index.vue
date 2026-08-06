<template>
  <div
    class="realtime-warning-banner"
    :style="{
      backgroundColor: 'var(--color-warning-20)',
      color: 'var(--text-primary)',
      border: '1px solid var(--color-warning)'
    }"
  >
    <IconifyIconOffline
      icon="ep:warning-filled"
      class="mr-2 text-sm"
      :style="{ color: 'var(--color-warning)' }"
    />
    <span>实时估值基于历史季报计算，不代表最终净值，仅供参考。</span>

    <!-- ✅ 点击关闭时，触发外层传进来的 toggle 方法彻底关掉整个功能 -->
    <el-button
      text
      size="small"
      :style="{ color: 'var(--text-secondary)' }"
      @click="handleClose"
    >
      关闭
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";

// 接收父组件传递的 toggle 函数
const props = defineProps<{
  onToggle?: () => void;
}>();

const handleClose = () => {
  // 调用父组件的 toggle，彻底关闭实时估值
  if (props.onToggle) {
    props.onToggle();
  }
};
</script>

<style scoped>
.realtime-warning-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  margin-bottom: 16px;
  font-size: 13px;
  border-radius: 8px;
}
</style>
