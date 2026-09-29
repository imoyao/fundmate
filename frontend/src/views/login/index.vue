<template>
  <div
    class="login-page relative min-h-screen w-full select-none overflow-x-hidden"
  >
    <!-- 深海氛围背景装饰（纯 CSS 实现，替代原 bg.png 波浪图；不引入图片资源） -->
    <div
      class="login-bg-decor pointer-events-none fixed inset-0 z-0"
      aria-hidden="true"
    >
      <span class="login-ripple login-ripple--1" />
      <span class="login-ripple login-ripple--2" />
      <span class="login-ripple login-ripple--3" />
      <span class="login-ripple login-ripple--4" />
    </div>

    <!-- 亮暗切换 -->
    <div class="flex-c absolute right-5 top-3 z-30">
      <el-switch
        v-model="dataTheme"
        inline-prompt
        :active-icon="dayIcon"
        :inactive-icon="darkIcon"
        @change="dataThemeChange"
      />
    </div>

    <div
      class="login-container relative z-10 grid min-h-screen w-full grid-cols-1 min-[969px]:grid-cols-[1.12fr_0.88fr]"
    >
      <LoginBrandAside />
      <LoginFormPanel :page="page" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLayout } from "@/layout/hooks/useLayout";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";
import dayIcon from "@/assets/svg/day.svg?component";
import darkIcon from "@/assets/svg/dark.svg?component";
import LoginBrandAside from "./components/LoginBrandAside.vue";
import LoginFormPanel from "./components/LoginFormPanel.vue";
import { useLogin } from "./composables/useLogin";

defineOptions({ name: "Login" });

// #980 P1-C 结构拆分：登录/注册状态与动作收敛在 composables/useLogin.ts，
// 子组件经 page prop 注入同一实例；index 只保留页面壳、背景装饰与亮暗切换。
// useLogin() 先于亮暗初始化调用，保持原脚本「router/状态先行」的执行顺序。
const page = useLogin();

const { initStorage } = useLayout();
initStorage();

const { dataTheme, overallStyle, dataThemeChange } = useDataThemeChange();
dataThemeChange(overallStyle.value);
</script>

<style lang="scss" scoped>
/* =====================================================================
   登录 / 注册页 · 品牌深海鹦鹉螺主题
   - 布局由 template 内 Tailwind 类控制（栅格、宽度、间距、对齐）
   - 本块只负责视觉表现与微调；色值一律取自 design.md 既有令牌
     （--brand-* / --bg-* / --text-* / --border-* / --radius-* / --shadow-* 等）
   ===================================================================== */

/* ============ 响应式 ============
   ⚠️ 以下四块原先都排在各自的基础声明**之前**——媒体查询不改变特异性，覆盖被后面
   同选择器的声明压掉、**从未生效**（2026-09-18 修复，见 #1576 同类台账）。 */

/* 背景角度注册为可插值属性（Chrome/Safari 111+；不支持时渐变按 135deg 静态显示，安全降级） */
@property --bg-angle {
  syntax: "<angle>";
  initial-value: 135deg;
  inherits: false;
}

@keyframes login-bg-breathe {
  0%,
  100% {
    --bg-angle: 135deg;
  }

  50% {
    --bg-angle: 145deg;
  }
}

@keyframes login-ripple {
  /* 有机呼吸环：不等比缩放 + 微旋转，像水面涟漪自然扩散而非死板同心缩放 */
  0% {
    opacity: 0.28;
    transform: scale(1) rotate(0deg);
  }

  33% {
    opacity: 0.5;
    transform: scale(1.03) rotate(0.5deg);
  }

  66% {
    opacity: 0.65;
    transform: scale(1.06) rotate(-0.3deg);
  }

  100% {
    opacity: 0.28;
    transform: scale(1) rotate(0deg);
  }
}

.login-page {
  font-family: var(--font-sans);
  color: var(--text-primary);

  /* 统一连续背景：左侧暖奶油 → 右侧浅灰水平渐变，弱化左右分界 */
  background: linear-gradient(
    var(--bg-angle, 135deg),
    var(--bg-warm) 0%,
    var(--bg-page) 60%
  );

  /* 背景"呼吸"：角度缓慢摆动，让色彩流动起来 */
  animation: login-bg-breathe 12s ease-in-out infinite;
}

/* ---------- 深海氛围背景（CSS 装饰，替代原 bg.png 波浪图） ---------- */
.login-bg-decor {
  /* 统一背景后改透明：页面渐变由 .login-page 提供，本层只承载涟漪装饰 */
  background: transparent;
}

.login-ripple {
  position: absolute;
  border: 1px solid var(--brand-200);
  border-radius: 50%;

  /* 柔和扩散环：细边框 + 外扩光晕，替代单一硬线 */
  box-shadow: 0 0 0 6px var(--brand-200);

  /* 每环独立周期 + 负延迟错相，形成"深海呼吸"的错落感而非同步跳动 */
  animation: login-ripple 11s cubic-bezier(0.45, 0, 0.55, 1) infinite;
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
  animation-duration: 15s;
  animation-delay: -3s;
}

.login-ripple--3 {
  right: -250px;
  bottom: -290px;
  width: 640px;
  height: 640px;
  animation-duration: 19s;
  animation-delay: -7s;
}

.login-ripple--4 {
  right: -330px;
  bottom: -390px;
  width: 840px;
  height: 840px;
  animation-duration: 24s;
  animation-delay: -12s;
}

/* =====================================================================
   暗色模式独立视觉适配（design.dark.md v1.5）
   - 亮色渐变里的 --brand-100/--brand-200 在暗色下是深棕（#2d1612/#3d1c17），
     直接沿用会糊成一团；暗色下改用"深灰底 + 品牌色低透明度光晕"，
     品牌色饱和度已由 dark.scss 降 20%（--brand-700 → #d45a44）。
   - 低透明度光晕用 color-mix(in srgb, var(--brand-700) x%, transparent)
     实现（等价于 rgba(品牌主色-rgb, x) 手法，项目无 -rgb 变量；
     需 Chrome 111+，与 design.dark.md 接受的 hsl(from) 现代语法同级）。
   - 发光仅用于静止/呼吸装饰，遵守 design.dark.md「禁止动画循环中发光」
     性能红线——涟漪/光环用低透明度边框与扩散环表达，不用 box-shadow 辉光。
   ===================================================================== */

.dark .login-bg-decor {
  background: transparent;
}

.dark .login-ripple {
  border-color: color-mix(in srgb, var(--brand-700) 30%, transparent);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--brand-700) 10%, transparent);
}

/* 动效偏好：减弱动态 */
@media (prefers-reduced-motion: reduce) {
  .login-ripple,
  .login-page {
    animation: none;
  }
}
</style>
