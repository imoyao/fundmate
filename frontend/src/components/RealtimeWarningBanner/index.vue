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

    <!-- 关闭按钮：隐藏本横幅并持久化，刷新不再弹出；重新开启实时估值功能时横幅再次出现 -->
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

<script lang="ts">
// 横幅「已关闭」标记键。由外层 watchlist 页在实时估值功能「关→开」时清除，
// 使横幅重新出现；横幅自身只在挂载时读取该标记决定初始显隐。
export const REALTIME_BANNER_DISMISS_KEY = "realtime-warning-banner-dismissed";
</script>

<script setup lang="ts">
import { ref } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";

// 横幅显隐：实时估值功能开启（外层 v-if）且用户未关闭时才显示。
// 关闭动作持久化到 localStorage——关掉后刷新页面不再弹出（修复纯内存变量
// 刷新即重置导致反复弹出）。标记仅在「实时估值功能被重新开启」时由外层
// watch 清除，从而满足「关掉功能再开才重新提醒」的诉求。
const DISMISS_KEY = REALTIME_BANNER_DISMISS_KEY;

const visible = ref(
  typeof localStorage !== "undefined" &&
    localStorage.getItem(DISMISS_KEY) !== "1"
);

function dismiss() {
  visible.value = false;
  try {
    localStorage.setItem(DISMISS_KEY, "1");
  } catch {
    // 隐私模式 / localStorage 不可用时静默降级：仅本次会话隐藏
  }
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
