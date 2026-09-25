<template>
  <!-- 左侧：品牌叙事区（桌面端展示；≤968px 隐藏，与旧插画区同策略） -->
  <aside
    class="login-brand relative hidden flex-col overflow-hidden px-10 py-14 min-[969px]:flex xl:px-16"
  >
    <!-- 背景装饰层：鹦鹉螺插画全幅半透明，文字浮于其上 -->
    <div class="login-brand-bg" v-html="nautilusSvg" />

    <div class="relative z-10 flex items-center gap-3">
      <BrandLogo :size="44" />
      <span class="login-wordmark text-xl font-semibold">
        多多贝
        <span class="login-wordmark-sub ml-2 text-sm font-normal"
          >投资账本</span
        >
      </span>
    </div>

    <div
      class="login-brand-body relative z-10 flex flex-1 flex-col justify-center gap-5"
    >
      <h1
        class="login-slogan max-w-[14ch] text-[clamp(2.2rem,3.4vw,3.1rem)] font-bold leading-[1.15] tracking-[-0.02em]"
      >
        看见你的<span class="coral">复利曲线</span>
      </h1>
      <p class="login-sub max-w-[30ch] text-base leading-relaxed">
        一个让复利曲线清晰可见的投资账本
      </p>
    </div>

    <p class="login-tagline relative z-10 text-sm">
      潮有涨落，壳有深浅。算得清，才无患。
    </p>
  </aside>
</template>

<script setup lang="ts">
import nautilusSvg from "@/assets/login/nautilus-light.svg?raw";
import BrandLogo from "@/components/BrandLogo/index.vue";

defineOptions({ name: "LoginBrandAside" });
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

@keyframes login-curve-bob {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }

  15% {
    transform: translateY(-4px) rotate(-2deg);
  }

  32% {
    transform: translateY(0) rotate(0deg);
  }

  46% {
    transform: translateY(-2px) rotate(1deg);
  }

  60% {
    transform: translateY(0) rotate(0deg);
  }
}

@keyframes nautilus-breathe {
  0%,
  100% {
    opacity: var(--nautilus-opacity-min, 0.08);
    transform: translate(-50%, -50%) scale(1) rotate(0deg);
  }

  50% {
    opacity: var(--nautilus-opacity-max, 0.12);
    transform: translate(-50%, -50%) scale(1.03) rotate(2deg);
  }
}

/* ---------- 品牌叙事面板 ---------- */
.login-brand {
  position: relative;
  overflow: hidden;

  /* 去掉独立渐变：与 .login-page 共享连续背景，弱化左右分界 */
  background: transparent;
}

.login-brand::after {
  position: absolute;
  inset: auto 0 0;
  height: 35%;
  pointer-events: none;

  /* 底部过渡晕染（调淡）：作为左右交界处的自然过渡 */
  content: "";
  background: linear-gradient(to top, var(--brand-100), transparent);
  opacity: 0.6;
}

.login-wordmark {
  color: var(--text-primary);
}

.login-wordmark-sub {
  color: var(--text-tertiary-ink);
}

.login-slogan {
  color: var(--text-primary);
}

.coral {
  color: var(--brand-700);
}

.coral-curve {
  display: inline-block;
  transform-origin: 50% 85%;
  animation: login-curve-bob 3.4s ease-in-out infinite;
}

.login-sub {
  color: var(--text-secondary);
}

.login-tagline {
  color: var(--text-tertiary-ink);
  letter-spacing: 0.04em;
}

/* ---------- 品牌视觉锚点（鹦鹉螺插画：全幅半透明背景装饰层） ---------- */
.login-brand-bg {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  width: 80%;
  max-width: 480px;
  height: auto;
  pointer-events: none;

  /* 呼吸脉动：scale + opacity 起伏 + 极慢微旋转（深海中的鹦鹉螺） */
  opacity: var(--nautilus-opacity-min, 0.08);
  transform: translate(-50%, -50%);
  animation: nautilus-breathe 8s cubic-bezier(0.4, 0, 0.6, 1) infinite;

  :deep(svg) {
    width: 100%;
    height: auto;
  }
}

.dark .login-brand {
  /* 与亮色一致：去掉独立渐变，共享 .login-page 连续背景 */
  background: transparent;
}

.dark .login-brand::after {
  height: 35%;
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--brand-700) 7%, transparent),
    transparent
  );
  opacity: 0.6;
}

/* 暗色下插画呼吸范围提亮：0.12 ~ 0.16（动画 opacity 用 CSS 变量控制） */
:global(.dark) .login-brand-bg {
  --nautilus-opacity-min: 0.12;
  --nautilus-opacity-max: 0.16;
}

/* 移动端：品牌区仅剩 logo+名称，插画进一步压淡（防御性，<969px 时 aside 已隐藏） */
@include bp.below("md") {
  .login-brand-bg {
    opacity: 0.04;
  }
}

/* 动效偏好：减弱动态 */
@media (prefers-reduced-motion: reduce) {
  .coral-curve,
  .login-brand-bg {
    animation: none;
  }
}
</style>
