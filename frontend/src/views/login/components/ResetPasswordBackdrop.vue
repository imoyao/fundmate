<!--
  ResetPasswordBackdrop · 重置密码页的深海氛围背景（#980 批 B7 从 `reset-password.vue` 抽出）

  **纯 CSS 装饰，零数据、零交互**：四圈涟漪 + 三颗上浮气泡，`aria-hidden` 且
  `pointer-events: none`，不参与任何可访问性树与命中测试。

  为什么单独成组件：这一层全部是 `position: absolute` 的装饰元素 + 五个 keyframes，
  共一百余行，和页面编排毫无关系。它留在页面里时，改表单间距要滚过一整屏动画定义。

  ⚠️ 与登录页（`index.vue`）的这套装饰**长得像但不同**，本批刻意没有合并：
  - 登录页只有 4 圈涟漪、没有气泡，涟漪周期 11s，keyframes 叫 `login-bg-breathe`；
  - 本页 4 圈涟漪 + 3 颗气泡，周期 9s，keyframes 叫 `bg-breathe`。
  合并成一个组件必须给「要不要气泡 / 周期几秒 / keyframes 叫谁」开口子，
  而这三个参数各自都会改到已上线的登录页视觉。合并是另一件事，不在「只搬运」的范围内。

  注：`@keyframes` 在 scoped 块里会被 Vue 加上 scope 后缀，与登录页同名也不会互相覆盖。
-->
<template>
  <div
    class="login-bg-decor pointer-events-none fixed inset-0 z-0"
    aria-hidden="true"
  >
    <span class="login-ripple login-ripple--1" />
    <span class="login-ripple login-ripple--2" />
    <span class="login-ripple login-ripple--3" />
    <span class="login-ripple login-ripple--4" />
    <span class="login-bubble login-bubble--1" />
    <span class="login-bubble login-bubble--2" />
    <span class="login-bubble login-bubble--3" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: "ResetPasswordBackdrop" });
</script>

<style lang="scss" scoped>
@keyframes bg-breathe {
  0%,
  100% {
    filter: hue-rotate(0deg) saturate(1);
  }

  50% {
    filter: hue-rotate(-4deg) saturate(1.05);
  }
}

@keyframes login-ripple {
  0% {
    opacity: 0.3;
    transform: scale(1) rotate(0deg);
  }

  33% {
    opacity: 0.55;
    transform: scale(1.05) rotate(1deg);
  }

  66% {
    opacity: 0.7;
    transform: scale(1.09) rotate(-0.6deg);
  }

  100% {
    opacity: 0.3;
    transform: scale(1) rotate(0deg);
  }
}

@keyframes login-bubble-rise {
  0%,
  100% {
    opacity: var(--bubble-opacity-min, 0.1);
    transform: translateY(0);
  }

  50% {
    opacity: var(--bubble-opacity-max, 0.2);
    transform: translateY(-40px);
  }
}

/* ---------- 深海氛围背景 ---------- */
.login-bg-decor {
  background: transparent;
  animation: bg-breathe 10s ease-in-out infinite;
}

.login-ripple {
  position: absolute;
  border: 1px solid var(--brand-200);
  border-radius: 50%;
  box-shadow: 0 0 0 6px var(--brand-200);
  animation: login-ripple 9s cubic-bezier(0.45, 0, 0.55, 1) infinite;
}

.login-ripple--1 {
  right: -90px;
  bottom: -100px;
  width: 300px;
  height: 300px;
}

.login-ripple--2 {
  right: -170px;
  bottom: -200px;
  width: 460px;
  height: 460px;
  animation-duration: 13s;
  animation-delay: -2s;
}

.login-ripple--3 {
  right: -250px;
  bottom: -290px;
  width: 640px;
  height: 640px;
  animation-duration: 17s;
  animation-delay: -5s;
}

.login-ripple--4 {
  right: -330px;
  bottom: -390px;
  width: 840px;
  height: 840px;
  animation-duration: 21s;
  animation-delay: -9s;
}

/* 气泡上浮 */
.login-bubble {
  position: absolute;
  pointer-events: none;
  background: var(--brand-700);
  border-radius: 50%;
  animation: login-bubble-rise 8s ease-in-out infinite;
}

.login-bubble--1 {
  top: 20%;
  right: 15%;
  width: 8px;
  height: 8px;
  opacity: 0.15;
}

.login-bubble--2 {
  top: 35%;
  right: 22%;
  width: 5px;
  height: 5px;
  opacity: 0.1;
  animation-duration: 10s;
  animation-delay: 2s;
}

.login-bubble--3 {
  top: 50%;
  right: 12%;
  width: 6px;
  height: 6px;
  opacity: 0.12;
  animation-duration: 9s;
  animation-delay: 4s;
}

/* =====================================================================
   暗色模式独立视觉适配（与登录页同款，design.dark.md v1.5）
   ===================================================================== */

.dark .login-bg-decor {
  background: transparent;
}

.dark .login-ripple {
  border-color: color-mix(in srgb, var(--brand-700) 30%, transparent);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--brand-700) 10%, transparent);
}

.dark .login-bubble {
  --bubble-opacity-min: 0.15;
  --bubble-opacity-max: 0.25;

  background: color-mix(in srgb, var(--brand-700) 60%, transparent);
}

/* 动效偏好：减弱动态 */
@media (prefers-reduced-motion: reduce) {
  .login-ripple,
  .login-bg-decor,
  .login-bubble {
    animation: none;
  }
}
</style>
