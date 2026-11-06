<!--
  CloudUploadIcon · 上传拖拽区的主图标（云 + 向上箭头）。

  为什么内联而不用图标集（#2937）：
  离线图标集只注册了 `@iconify-json/ep`（见 `components/ReIcon/src/offlineIcon.ts`），
  而 `ep` 里没有「云 + 上传箭头」这个造型——最接近的 `ep:upload` / `ep:upload-filled`
  是「箭头 + 底座横条」与「实心云」，换上去等于把导入流程第一屏的主图标换了个样子。
  `@iconify-json/lucide` 未安装，装一整套只为一个图标与仓内取向冲突
  （`views/welcome/components/BoardActionIcon.vue:4-11` 已写明这条判据）。

  故按 BoardActionIcon 的范式内联 Lucide 路径：24×24 网格、stroke=currentColor、
  stroke-width 2、圆角端点与连接。尺寸走 `1em`，沿用调用方 `.upload-icon` 的
  `font-size`（`var(--text-hero)`）与 `color`，与替换前的 Iconify 图标同尺寸同色，
  版面不跳动；`display: inline-block` 与 Iconify 的 svg 一致，基线对齐不变。
-->
<template>
  <svg
    class="cloud-upload-icon"
    viewBox="0 0 24 24"
    width="1em"
    height="1em"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path d="M12 13v8" />
    <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
    <path d="m8 17 4-4 4 4" />
  </svg>
</template>

<script setup lang="ts">
defineOptions({ name: "CloudUploadIcon" });
</script>

<style scoped>
.cloud-upload-icon {
  display: inline-block;
}
</style>
