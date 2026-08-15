<template>
  <div
    v-if="visible"
    class="realtime-warning-banner"
    :style="{
      backgroundColor: 'var(--color-warning-20)',
      color: 'var(--text-primary)',
      border: '1px solid var(--color-warning)'
    }"
  >
    <!-- 文本区：图标 + 提示文字 左对齐 -->
    <div class="realtime-warning-banner__text">
      <IconifyIconOffline
        icon="ep:warning-filled"
        class="mr-2 text-sm shrink-0"
        :style="{ color: 'var(--color-warning)' }"
      />
      <span>实时估值基于历史季报计算，不代表最终净值，仅供参考。</span>
    </div>

    <!-- 关闭按钮：仅隐藏本横幅，不影响实时估值功能（关闭态仅当前会话有效） -->
    <el-button
      class="realtime-warning-banner__close"
      size="small"
      @click="dismiss"
    >
      <IconifyIconOffline icon="ep:close" class="mr-1" />
      关闭
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";

// 横幅自身的显示状态：关闭只隐藏横幅，不影响实时估值功能。
// 不做 localStorage 持久化——横幅的显隐由外层实时估值开关决定：
// 用户关闭实时估值时外层 v-if 会整体卸载本组件；再次开启时本组件重新挂载，
// visible 重置为 true，横幅随之重新出现（即「关掉后又开估值就再提醒」的循环）。
// 关闭动作仅隐藏当前这一次，刷新页面（功能仍开启）横幅按预期重新出现。
const visible = ref(true);

function dismiss() {
  visible.value = false;
}
</script>

<style scoped>
.realtime-warning-banner {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  margin-bottom: 16px;
  font-size: 13px;
  border-radius: 8px;
}

/* 文本区左对齐：图标 + 文案靠左排布 */
.realtime-warning-banner__text {
  display: flex;
  flex: 1;
  align-items: center;
  min-width: 0;
  text-align: left;
}

/* 关闭按钮：带边框的明确按钮，点击区域清晰 */
.realtime-warning-banner__close {
  flex-shrink: 0;
  color: var(--text-secondary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  transition:
    color 150ms ease,
    border-color 150ms ease,
    background-color 150ms ease;
}

.realtime-warning-banner__close:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
  border-color: var(--border-strong);
}
</style>
