<!--
  BoardActionIcon · 「家庭资产看板」标题栏右侧两个按钮的图标。

  为什么要自带 SVG：离线图标集只注册了 `@iconify-json/ep`（见 ReIcon/offlineIcon.ts），
  而 `ep:view` / `ep:hide` 是**填充式**大色块（眼睛带实心瞳孔，隐藏态还压一条斜杠），
  旁边的 `ep:full-screen` 却是细线四角——同为 18px 圆钮，视觉重量差一大截，
  看起来像两套图标拼在一起。故这里给两个按钮统一成同一套线性图标：
  24×24 网格、stroke=currentColor、1.7 描边、圆角端点，只靠 prop 切语义。

  不引入新依赖：Lucide 风格的路径直接内联，离线可用、不受图标集注册范围限制，
  也不会把整个 Remix / Lucide 图标包打进主 bundle。
-->
<template>
  <svg
    class="board-action-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-if="name === 'eye'">
      <path
        d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"
      />
      <circle cx="12" cy="12" r="3" />
    </template>

    <template v-else-if="name === 'eye-off'">
      <path
        d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"
      />
      <path d="M14.084 14.158a3 3 0 0 1-4.242-4.242" />
      <path
        d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"
      />
      <path d="m2 2 20 20" />
    </template>

    <template v-else>
      <path d="M8 3H5a2 2 0 0 0-2 2v3" />
      <path d="M21 8V5a2 2 0 0 0-2-2h-3" />
      <path d="M3 16v3a2 2 0 0 0 2 2h3" />
      <path d="M16 21h3a2 2 0 0 0 2-2v-3" />
    </template>
  </svg>
</template>

<script setup lang="ts">
defineOptions({ name: "BoardActionIcon" });

defineProps<{
  /** eye = 金额可见 / eye-off = 已隐藏 / maximize = 查看资产详情 */
  name: "eye" | "eye-off" | "maximize";
}>();
</script>

<style lang="scss" scoped>
.board-action-icon {
  display: block;
  width: 18px;
  height: 18px;

  /* 与旁边按钮同尺寸；不写死 color，继承按钮的 --text-tertiary-ink */
}
</style>
