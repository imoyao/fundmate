<!--
  ResetPasswordBrandAside · 重置密码页左侧品牌叙事区（#980 批 B7 从 `reset-password.vue` 抽出）

  桌面端展示（`min-[969px]:flex`），≤968px 整个 aside 隐藏 —— 这段布局与断点
  跟随组件一起搬走，父页面只留两列 grid。

  ⚠️ 与登录页 `LoginBrandAside.vue` 的**差异清单**（本批刻意没有合并成一个组件）：
  | 项 | 登录页 | 本页 |
  | 标题高亮 | 「看见你的**复利曲线**」 | 「**重置密码**」 |
  | 副标题 | 一个让复利曲线清晰可见的投资账本 | 通过邮件链接安全地设置新密码 |
  | 高亮动画 | `.coral-curve`，`login-curve-bob`（含旋转） | `.coral`，`coral-bob`（只上下浮动） |
  | 鹦鹉螺透明度 | 0.08~0.12（暗色 0.12~0.16） | 0.12~0.18（暗色 0.16~0.22） |
  | 鹦鹉螺呼吸 | 8s，scale 1.03 / rotate 2deg | 7s，scale 1.06 / rotate 3deg |
  | 气泡装饰 | 无（在页面背景层） | 有 |

  合并需要给「高亮动画 / 透明度档位 / 呼吸时长」各开一个 prop，五个参数里有三个
  会改到已上线的登录页视觉。合并是另一件事，不在「只搬运不重做视觉」的范围内。
-->
<template>
  <aside
    class="login-brand relative hidden flex-col overflow-hidden px-10 py-14 min-[969px]:flex xl:px-16"
  >
    <!-- 品牌视觉锚点：鹦鹉螺插画全幅半透明，文字浮于其上 -->
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
        <span class="coral">重置密码</span>
      </h1>
      <p class="login-sub max-w-[30ch] text-base leading-relaxed">
        通过邮件链接安全地设置新密码
      </p>
    </div>

    <p class="login-tagline relative z-10 text-sm">
      潮有涨落，壳有深浅。算得清，才无患。
    </p>
  </aside>
</template>

<script setup lang="ts">
import BrandLogo from "@/components/BrandLogo/index.vue";
import nautilusSvg from "@/assets/login/nautilus-light.svg?raw";

defineOptions({ name: "ResetPasswordBrandAside" });
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

@keyframes coral-bob {
  0%,
  100% {
    transform: translateY(0);
  }

  30% {
    transform: translateY(-3px);
  }

  60% {
    transform: translateY(0);
  }
}

@keyframes nautilus-breathe {
  0%,
  100% {
    opacity: var(--nautilus-opacity-min, 0.12);
    transform: translate(-50%, -50%) scale(1) rotate(0deg);
  }

  50% {
    opacity: var(--nautilus-opacity-max, 0.18);
    transform: translate(-50%, -50%) scale(1.06) rotate(3deg);
  }
}

/* ---------- 品牌叙事面板 ---------- */
.login-brand {
  position: relative;
  overflow: hidden;
  background: transparent;
}

.login-brand::after {
  position: absolute;
  inset: auto 0 0;
  height: 35%;
  pointer-events: none;
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
  display: inline-block;
  color: var(--brand-700);
  animation: coral-bob 3.4s ease-in-out infinite;
}

.login-sub {
  color: var(--text-secondary);
}

.login-tagline {
  color: var(--text-tertiary-ink);
  letter-spacing: 0.04em;
}

/* ---------- 品牌视觉锚点（鹦鹉螺插画） ---------- */
.login-brand-bg {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  width: 80%;
  max-width: 480px;
  height: auto;
  pointer-events: none;
  opacity: var(--nautilus-opacity-min, 0.12);
  transform: translate(-50%, -50%);
  animation: nautilus-breathe 7s cubic-bezier(0.4, 0, 0.6, 1) infinite;

  :deep(svg) {
    width: 100%;
    height: auto;
  }
}

.dark .login-brand {
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

:global(.dark) .login-brand-bg {
  --nautilus-opacity-min: 0.16;
  --nautilus-opacity-max: 0.22;
}

/* 移动端：品牌区压淡（<969px 时 aside 已隐藏） */
@include bp.below("md") {
  .login-brand-bg {
    opacity: 0.04;
  }
}

/* 动效偏好：减弱动态 */
@media (prefers-reduced-motion: reduce) {
  .login-brand-bg,
  .coral {
    animation: none;
  }
}
</style>
