<template>
  <!-- 一次性告知横幅：实时估值免责说明；关闭持久化到 localStorage，刷新不再弹出。
       #2716 起壳由 SoftBanner（warning + dense）承担，持久 dismiss 语义留在本组件 -->
  <SoftBanner
    v-if="visible"
    class="realtime-warning-banner"
    variant="warning"
    icon="ep:warning-filled"
    dense
    dismissible
    @close="dismiss"
  >
    <span>实时估值基于历史季报计算，不代表最终净值，仅供参考。</span>
  </SoftBanner>
</template>

<script setup lang="ts">
import { ref } from "vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import { REALTIME_BANNER_DISMISS_KEY } from "./constants";

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
