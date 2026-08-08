<!--
  BrandLogo · 多倍贝品牌 Logo（超椭圆主形态）

  全站统一品牌图形组件：应用站头部/侧边栏、探市/温度计 Header、登录注册页共用，
  避免各场景各自引用不同素材导致的风格漂移。

  图形来源 logo-delivery/01-master-superellipse/logo.svg（权威母本），
  以 `?raw` 内联渲染，前端不再依赖 public 下的 logo 图片文件。

  防坑（logo-delivery/LOGO_DELIVERY.md 第九章）：
    - 外层 SVG 自带 viewBox=0 0 512 512，此处仅覆盖显示尺寸，不裁剪；
    - 内联 SVG 含 clipPath 的 id，多实例时必须 id 隔离（本组件按实例加前缀）；
    - 不使用 <symbol>+<use> 复用（chromium/rsvg 下空白）。

  props:
    - size: 图标边长（px，默认 32）
-->
<template>
  <span class="brand-logo" :style="{ width: `${size}px`, height: `${size}px` }">
    <span class="brand-logo__svg" v-html="logoHtml" />
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import logoRaw from "@/assets/brand/logo.svg?raw";

withDefaults(
  defineProps<{
    size?: number;
  }>(),
  { size: 32 }
);

// 按实例生成唯一前缀，隔离内联 SVG 的 clipPath id（多实例防 url(#id) 串扰）
let uidSeq = 0;
const uid = `bl${++uidSeq}`;

const logoHtml = computed(() =>
  logoRaw.replaceAll("shapeclip", `${uid}_shapeclip`)
);
</script>

<style lang="scss" scoped>
.brand-logo {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  line-height: 0;

  &__svg {
    display: block;
    width: 100%;
    height: 100%;

    :deep(svg) {
      display: block;
      width: 100%;
      height: 100%;
    }
  }
}
</style>
