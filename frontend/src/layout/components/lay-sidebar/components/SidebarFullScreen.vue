<script setup lang="ts">
import { ref, watch } from "vue";
import { useNav } from "@/layout/hooks/useNav";

const screenIcon = ref();
const { toggle, isFullscreen, Fullscreen, ExitFullscreen } = useNav();

isFullscreen.value = !!(
  document.fullscreenElement ||
  document.webkitFullscreenElement ||
  document.mozFullScreenElement ||
  document.msFullscreenElement
);

watch(
  isFullscreen,
  full => {
    screenIcon.value = full ? ExitFullscreen : Fullscreen;
  },
  {
    immediate: true
  }
);
</script>

<template>
  <!-- 全屏切换（#1842 规则二 A 类）：span @click → 真 button。
       此前键盘用户无法切换全屏；title 只在鼠标悬停时可见，不是可访问名称。 -->
  <button
    type="button"
    class="icon-plain-btn fullscreen-icon navbar-bg-hover"
    :title="isFullscreen ? '退出全屏' : '全屏'"
    :aria-label="isFullscreen ? '退出全屏' : '全屏'"
    @click="toggle"
  >
    <IconifyIconOffline :icon="screenIcon" />
  </button>
</template>
