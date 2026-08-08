<!--
  Superellipse · 超椭圆（Squircle）容器组件

  用 SVG mask（`mask-image` 的 data-URI SVG）把内容裁剪为超椭圆轮廓。
  相比纯 CSS `border-radius`：超椭圆在「直线→曲线」过渡点是连续曲率，
  视觉上比圆形圆弧更柔和，是品牌 n=3 超椭圆在 UI 上的统一载体
  （后续 logo、头像、卡片均复用，勿在各处手写 polyline 或 border-radius 圆角）。

  原理参考（实现层调研，均弃用）：
   - wopian/smooth-corners 的 CSS Houdini Paint worklet：浏览器支持不足，弃。
   - racra/smooth-corner-rect 核心指 Android 的 Compose，非 Web，弃。
   统一采用「SVG <polygon> 黑底超椭圆 → `mask-image: url("data:image/svg+xml,...")`」：
   全浏览器（含旧 Webkit，带 -webkit- 前缀）、像素级、可响应尺寸、无 DOM 剪裁 id 冲突。

   props:
     - power:  超椭圆指数 n（默认 3）。越大越接近直角方形；2 即圆。
     - points: 采样点数（默认 128，越多越平滑、字符串越长）。
   slot: 被裁剪成超椭圆的内容（不限定单元素）。
-->
<template>
  <div class="superellipse" :style="maskStyle">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    power?: number;
    points?: number;
  }>(),
  { power: 3, points: 128 }
);

/** 在 0~1 单位方形内生成 superellipse 闭合多边形的坐标串 */
function buildPolygon(power: number): string {
  const { points } = props;
  const pts: string[] = [];
  for (let i = 0; i < points; i++) {
    const t = (i / points) * Math.PI * 2;
    const ct = Math.cos(t);
    const st = Math.sin(t);
    // 超椭圆参数方程：x = copysign(|cosθ|^(2/n), cosθ)
    const x = Math.sign(ct) * Math.pow(Math.abs(ct), 2 / power);
    const y = Math.sign(st) * Math.pow(Math.abs(st), 2 / power);
    pts.push(
      `${((x * 0.5 + 0.5) * 100).toFixed(2)},${((y * 0.5 + 0.5) * 100).toFixed(2)}`
    );
  }
  return pts.join(" ");
}

const maskStyle = computed(() => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><polygon points="${buildPolygon(props.power)}"/></svg>`;
  const url = `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
  return {
    WebkitMaskImage: url,
    maskImage: url,
    WebkitMaskSize: "100%",
    maskSize: "100%",
    WebkitMaskRepeat: "no-repeat",
    maskRepeat: "no-repeat"
  };
});
</script>

<style scoped>
.superellipse {
  display: block;
}
</style>
